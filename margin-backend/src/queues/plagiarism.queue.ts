import Bull from 'bull';
import { Server as SocketServer } from 'socket.io';
import { PlagiarismJobModel } from '@/models/PlagiarismJob';
import { PlagiarismService } from '@/services/plagiarism.service';
import { CreditService } from '@/services/credit.service';
import { CreditCosts } from '@/Constants';

const plagiarismQueue = new Bull('plagiarism', process.env.REDIS_URL || 'redis://localhost:6379');

export function initPlagiarismQueue(io: SocketServer) {
  plagiarismQueue.process(async (job) => {
    const { jobId, userId, text } = job.data;
    const room = `plagiarism:${jobId}`;

    const emitProgress = (status: string, data: any = {}) => {
      io.to(room).emit('plagiarism:progress', { jobId, status, ...data });
    };

    try {
      await PlagiarismJobModel.findByIdAndUpdate(jobId, { status: 'processing' });
      emitProgress('processing');

      const result = await PlagiarismService.checkWithCopyscape(text);

      await PlagiarismJobModel.findByIdAndUpdate(jobId, {
        status: 'done',
        overallScore: result.overallScore,
        matches: result.matches,
        creditsUsed: CreditCosts.PLAGIARISM_PER_CHECK,
      });

      await CreditService.deduct(
        userId,
        CreditCosts.PLAGIARISM_PER_CHECK,
        'plagiarism',
        jobId,
        'Plagiarism check'
      );

      emitProgress('done', { overallScore: result.overallScore, matches: result.matches });
    } catch (err: any) {
      await PlagiarismJobModel.findByIdAndUpdate(jobId, { status: 'failed' });
      emitProgress('failed', { error: err.message });
    }
  });

  return plagiarismQueue;
}

export default plagiarismQueue;
