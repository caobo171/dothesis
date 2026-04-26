import { Router } from 'express';
import passport from 'passport';
import { Code, CreditCosts } from '@/Constants';
import { HumanizeJobModel } from '@/models/HumanizeJob';
import { HumanizerService } from '@/services/humanizer.service';
import { CreditService } from '@/services/credit.service';
import { DocumentService } from '@/services/document.service';

export default (router: Router) => {
  // SSE streaming humanize
  router.post(
    '/humanize/run',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const { text, tone = 'academic', strength = 50, lengthMode = 'match' } = req.body;

      if (!text || text.trim().length === 0) {
        return res.json({ code: Code.InvalidInput, message: 'Text is required' });
      }

      const wordCount = DocumentService.countWords(text);
      const creditCost = HumanizerService.calculateCredits(wordCount);

      if (!(await CreditService.hasEnough(user._id.toString(), creditCost))) {
        return res.json({ code: Code.InsufficientCredits, message: 'Insufficient credits' });
      }

      // Create job record
      const job = await HumanizeJobModel.create({
        owner: user._id.toString(),
        inputText: text,
        tone,
        strength,
        lengthMode,
        status: 'processing',
      });

      // Set up SSE
      res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
        'X-Accel-Buffering': 'no',
      });

      try {
        // Get input AI score
        const aiScoreIn = await HumanizerService.checkAiScore(text);
        res.write(`data: ${JSON.stringify({ type: 'ai_score_in', score: aiScoreIn })}\n\n`);

        // Stream the humanized output
        let fullOutput = '';
        await HumanizerService.humanizeStream(
          text,
          tone,
          strength,
          lengthMode,
          (chunk: string) => {
            fullOutput += chunk;
            res.write(`data: ${JSON.stringify({ type: 'chunk', content: chunk })}\n\n`);
          }
        );

        // Parse the full JSON response
        let rewrittenText = fullOutput;
        let changes: any[] = [];
        try {
          const parsed = JSON.parse(fullOutput);
          rewrittenText = parsed.rewrittenText || fullOutput;
          changes = parsed.changes || [];
        } catch {
          // If streaming didn't produce valid JSON, use raw text
        }

        // Get output AI score
        const aiScoreOut = await HumanizerService.checkAiScore(rewrittenText);

        // Deduct credits
        await CreditService.deduct(
          user._id.toString(),
          creditCost,
          'humanize',
          job._id.toString(),
          `Humanize ${wordCount} words`
        );

        // Update job
        job.outputText = rewrittenText;
        job.outputHtml = rewrittenText; // Frontend builds diff from changes
        job.aiScoreIn = aiScoreIn;
        job.aiScoreOut = aiScoreOut;
        job.changesCount = changes.length;
        job.creditsUsed = creditCost;
        job.status = 'completed';
        await job.save();

        // Send final result
        res.write(
          `data: ${JSON.stringify({
            type: 'done',
            jobId: job._id,
            rewrittenText,
            changes,
            aiScoreIn,
            aiScoreOut,
            changesCount: changes.length,
            creditsUsed: creditCost,
          })}\n\n`
        );
      } catch (err: any) {
        // Refund on failure
        job.status = 'failed';
        await job.save();
        res.write(`data: ${JSON.stringify({ type: 'error', message: err.message })}\n\n`);
      }

      res.end();
    }
  );

  // Check AI score (standalone)
  router.post(
    '/humanize/check-score',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const { text } = req.body;
      if (!text) return res.json({ code: Code.InvalidInput, message: 'Text required' });

      const hasCreds = await CreditService.hasEnough(user._id.toString(), CreditCosts.AI_SCORE_CHECK);
      if (!hasCreds) {
        return res.json({ code: Code.InsufficientCredits, message: 'Insufficient credits' });
      }

      const score = await HumanizerService.checkAiScore(text);
      await CreditService.deduct(
        user._id.toString(),
        CreditCosts.AI_SCORE_CHECK,
        'ai_score',
        '',
        'AI detection score check'
      );

      return res.json({ code: Code.Success, data: { score } });
    }
  );

  // History
  router.post(
    '/humanize/history',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const jobs = await HumanizeJobModel.find({ owner: user._id.toString() })
        .sort({ createdAt: -1 })
        .select('-inputText -outputHtml -outputText')
        .limit(50);
      return res.json({ code: Code.Success, data: jobs });
    }
  );

  // Get single job
  router.post(
    '/humanize/get',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { id } = req.body;
      const job = await HumanizeJobModel.findById(id);
      if (!job) return res.json({ code: Code.NotFound, message: 'Job not found' });
      return res.json({ code: Code.Success, data: job });
    }
  );
};
