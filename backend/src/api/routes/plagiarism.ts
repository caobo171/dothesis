import { Router } from 'express';
import passport from 'passport';
import { Code, CreditCosts } from '@/Constants';
import { PlagiarismJobModel } from '@/models/PlagiarismJob';
import { CreditService } from '@/services/credit.service';
import plagiarismQueue from '@/queues/plagiarism.queue';

export default (router: Router) => {
  router.post(
    '/plagiarism/check',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const { text } = req.body;

      if (!text || text.trim().length === 0) {
        return res.json({ code: Code.InvalidInput, message: 'Text is required' });
      }

      if (!(await CreditService.hasEnough(user._id.toString(), CreditCosts.PLAGIARISM_PER_CHECK))) {
        return res.json({ code: Code.InsufficientCredits, message: 'Insufficient credits' });
      }

      const job = await PlagiarismJobModel.create({
        owner: user._id.toString(),
        status: 'pending',
      });

      await plagiarismQueue.add({
        jobId: job._id.toString(),
        userId: user._id.toString(),
        text,
      });

      return res.json({ code: Code.Success, data: { jobId: job._id } });
    }
  );

  router.post(
    '/plagiarism/get',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { id } = req.body;
      const job = await PlagiarismJobModel.findById(id);
      if (!job) return res.json({ code: Code.NotFound, message: 'Job not found' });
      return res.json({ code: Code.Success, data: job });
    }
  );
};
