import { Router } from 'express';
import passport from 'passport';
import { Code, CreditCosts } from '@/Constants';
import { HumanizeJobModel } from '@/models/HumanizeJob';
import { HumanizerService } from '@/services/humanizer/humanizer.service';
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
        // Decision: Switched from single-pass humanizeStream to multi-agent pipeline.
        // Pipeline runs Gemini preprocess -> GPT critic -> GPT humanizer in a loop.
        // onStage callback sends progress events to the client via SSE.
        const result = await HumanizerService.humanizePipeline(
          text,
          tone,
          strength,
          lengthMode,
          (stage, data) => {
            res.write(`data: ${JSON.stringify({ type: stage, ...data })}\n\n`);
          }
        );

        // Deduct credits
        await CreditService.deduct(
          user._id.toString(),
          creditCost,
          'humanize',
          job._id.toString(),
          `Humanize ${wordCount} words`
        );

        // Update job
        job.outputText = result.rewrittenText;
        job.outputHtml = result.rewrittenText;
        job.aiScoreIn = result.aiScoreIn;
        job.aiScoreOut = result.aiScoreOut;
        job.changesCount = result.changes.length;
        job.creditsUsed = creditCost;
        job.iterations = result.iterations;
        job.tokenUsage = result.tokenUsage;
        job.status = 'completed';
        await job.save();

        // Send final result
        res.write(
          `data: ${JSON.stringify({
            type: 'done',
            jobId: job._id,
            rewrittenText: result.rewrittenText,
            changes: result.changes,
            aiScoreIn: result.aiScoreIn,
            aiScoreOut: result.aiScoreOut,
            tokenUsage: result.tokenUsage,
            iterations: result.iterations,
            changesCount: result.changes.length,
            creditsUsed: creditCost,
          })}\n\n`
        );
      } catch (err: any) {
        console.error('[Humanizer] Pipeline failed:', err.message, err.stack);
        job.status = 'failed';
        await job.save();
        res.write(`data: ${JSON.stringify({ type: 'error', message: err.message })}\n\n`);
      }

      res.end();
    }
  );

  // Decision: Sync humanize endpoint — designed for queue workers and non-SSE clients.
  // Calls the same multi-agent pipeline as /run but returns JSON directly instead of SSE.
  router.post(
    '/humanize/run-sync',
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

      const job = await HumanizeJobModel.create({
        owner: user._id.toString(),
        inputText: text,
        tone,
        strength,
        lengthMode,
        status: 'processing',
      });

      try {
        const result = await HumanizerService.humanizePipeline(text, tone, strength, lengthMode);

        await CreditService.deduct(
          user._id.toString(),
          creditCost,
          'humanize',
          job._id.toString(),
          `Humanize ${wordCount} words`
        );

        job.outputText = result.rewrittenText;
        job.outputHtml = result.rewrittenText;
        job.aiScoreIn = result.aiScoreIn;
        job.aiScoreOut = result.aiScoreOut;
        job.changesCount = result.changes.length;
        job.creditsUsed = creditCost;
        job.iterations = result.iterations;
        job.tokenUsage = result.tokenUsage;
        job.status = 'completed';
        await job.save();

        return res.json({
          code: Code.Success,
          data: {
            jobId: job._id,
            rewrittenText: result.rewrittenText,
            changes: result.changes,
            aiScoreIn: result.aiScoreIn,
            aiScoreOut: result.aiScoreOut,
            tokenUsage: result.tokenUsage,
            iterations: result.iterations,
            creditsUsed: creditCost,
          },
        });
      } catch (err: any) {
        job.status = 'failed';
        await job.save();
        return res.json({ code: Code.Error, message: err.message });
      }
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

  // Decision: Static AI-generated sample texts for users to test the humanizer.
  // Intentionally written in a robotic AI style so the before/after effect is clear.
  router.get('/humanize/samples', (_req, res) => {
    const SAMPLE_TEXTS = [
      {
        id: 'academic',
        label: 'Academic Essay',
        text: `The rapid advancement of artificial intelligence has fundamentally transformed the landscape of modern education. Furthermore, the integration of machine learning algorithms into pedagogical frameworks has demonstrated significant potential for personalized learning experiences. Research indicates that AI-driven adaptive learning platforms can improve student outcomes by approximately 30%, underscoring the pivotal role of technology in contemporary educational paradigms. Moreover, the implementation of natural language processing tools has facilitated more efficient assessment methodologies, enabling educators to provide timely and comprehensive feedback. It is worth noting that these technological innovations have also raised important ethical considerations regarding data privacy and algorithmic bias in educational settings.`,
      },
      {
        id: 'blog',
        label: 'Blog Post',
        text: `In today's fast-paced world, remote work has emerged as a game changer for businesses worldwide. Companies are increasingly leveraging digital collaboration tools to streamline their operations and foster a more inclusive work environment. The transition to remote work has unlocked unprecedented opportunities for organizations to tap into a global talent pool. Additionally, studies have shown that remote workers demonstrate higher productivity levels compared to their in-office counterparts. This paradigm shift in workplace dynamics is reshaping how we think about work-life balance and organizational culture.`,
      },
      {
        id: 'research',
        label: 'Research Summary',
        text: `This comprehensive literature review examines the multifaceted impact of climate change on global agricultural productivity. The analysis encompasses 47 peer-reviewed studies published between 2020 and 2025, revealing several key findings. Notably, rising temperatures have led to a significant decline in crop yields across tropical regions, with an average reduction of 8.3% per decade. Furthermore, changes in precipitation patterns have exacerbated water scarcity in arid and semi-arid zones, subsequently affecting irrigation-dependent farming systems. The evidence underscores the urgent need for innovative adaptation strategies, including the development of heat-resistant crop varieties and the implementation of precision agriculture techniques to optimize resource utilization.`,
      },
      {
        id: 'persuasive',
        label: 'Persuasive Argument',
        text: `The adoption of renewable energy sources is not merely an environmental imperative but a robust economic opportunity that nations cannot afford to overlook. Solar and wind energy technologies have achieved remarkable cost reductions, making them increasingly competitive with traditional fossil fuels. Moreover, the transition to clean energy has the potential to create millions of new jobs, thereby stimulating economic growth while simultaneously addressing the pressing challenge of climate change. It should be mentioned that countries at the forefront of renewable energy adoption have already begun to reap substantial economic benefits, positioning themselves as leaders in the emerging green economy. The evidence clearly demonstrates that investing in sustainable energy infrastructure is both a prudent fiscal decision and a moral obligation.`,
      },
    ];

    return res.json({ code: Code.Success, data: SAMPLE_TEXTS });
  });
};
