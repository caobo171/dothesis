import { Router } from 'express';
import passport from 'passport';
import { Code, CreditCosts } from '@/Constants';
import { AutoCiteJobModel } from '@/models/AutoCiteJob';
import { CreditService } from '@/services/credit.service';
import autociteQueue from '@/queues/autocite.queue';

export default (router: Router) => {
  router.post(
    '/cite/analyze',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const { text, style = 'apa' } = req.body;

      if (!text || text.trim().length === 0) {
        return res.json({ code: Code.InvalidInput, message: 'Text is required' });
      }

      if (!(await CreditService.hasEnough(user._id.toString(), CreditCosts.AUTOCITE_PER_ANALYSIS))) {
        return res.json({ code: Code.InsufficientCredits, message: 'Insufficient credits' });
      }

      const job = await AutoCiteJobModel.create({
        owner: user._id.toString(),
        style,
        status: 'pending',
      });

      await autociteQueue.add({
        jobId: job._id.toString(),
        userId: user._id.toString(),
        text,
        style,
      });

      return res.json({ code: Code.Success, data: { jobId: job._id } });
    }
  );

  router.post(
    '/cite/accept',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { jobId, claimIndex, sourceId } = req.body;

      const job = await AutoCiteJobModel.findById(jobId);
      if (!job) return res.json({ code: Code.NotFound, message: 'Job not found' });

      if (claimIndex >= 0 && claimIndex < job.claims.length) {
        job.claims[claimIndex].sourceId = sourceId;
        job.claims[claimIndex].status = 'cited';
        await job.save();
      }

      return res.json({ code: Code.Success, data: job });
    }
  );

  router.post(
    '/cite/remove',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { jobId, claimIndex } = req.body;

      const job = await AutoCiteJobModel.findById(jobId);
      if (!job) return res.json({ code: Code.NotFound, message: 'Job not found' });

      if (claimIndex >= 0 && claimIndex < job.claims.length) {
        job.claims[claimIndex].sourceId = undefined;
        job.claims[claimIndex].status = 'pending';
        await job.save();
      }

      return res.json({ code: Code.Success, data: job });
    }
  );

  router.post(
    '/cite/get',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { id } = req.body;
      const job = await AutoCiteJobModel.findById(id);
      if (!job) return res.json({ code: Code.NotFound, message: 'Job not found' });
      return res.json({ code: Code.Success, data: job });
    }
  );

  router.post(
    '/cite/export',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { jobId, format = 'txt' } = req.body;

      const job = await AutoCiteJobModel.findById(jobId);
      if (!job) return res.json({ code: Code.NotFound, message: 'Job not found' });

      const citedSources = job.claims
        .filter((c) => c.sourceId && c.status === 'cited')
        .map((c) => job.sources.find((s) => s.id === c.sourceId))
        .filter(Boolean);

      const bibliography = citedSources.map((s: any) => s.cite).join('\n\n');

      if (format === 'txt') {
        res.setHeader('Content-Type', 'text/plain');
        res.setHeader('Content-Disposition', 'attachment; filename=bibliography.txt');
        return res.send(bibliography);
      }

      return res.json({ code: Code.Success, data: { bibliography } });
    }
  );
};
