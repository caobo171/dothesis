import Bull from 'bull';
import { Server as SocketServer } from 'socket.io';
import { AutoCiteJobModel } from '@/models/AutoCiteJob';
import { CitationSearchService } from '@/services/citation.service';
import { CreditService } from '@/services/credit.service';
import { CreditCosts } from '@/Constants';

const autociteQueue = new Bull('autocite', process.env.REDIS_URL || 'redis://localhost:6379');

export function initAutoCiteQueue(io: SocketServer) {
  autociteQueue.process(async (job) => {
    const { jobId, userId, text, style } = job.data;
    const room = `autocite:${jobId}`;

    const emitProgress = (status: string, data: any = {}) => {
      io.to(room).emit('autocite:progress', { jobId, status, ...data });
    };

    try {
      // Step 1: Extract claims
      await AutoCiteJobModel.findByIdAndUpdate(jobId, { status: 'extracting' });
      emitProgress('extracting');

      const claimTexts = await CitationSearchService.extractClaims(text);
      const claims = claimTexts.map((t) => ({
        text: t,
        sourceId: null,
        status: 'pending',
        candidates: [],
      }));

      await AutoCiteJobModel.findByIdAndUpdate(jobId, { claims });
      emitProgress('searching', { claimCount: claims.length });

      // Step 2: Search for sources for each claim
      await AutoCiteJobModel.findByIdAndUpdate(jobId, { status: 'searching' });
      const allSources: any[] = [];

      for (let i = 0; i < claims.length; i++) {
        const results = await CitationSearchService.searchAll(claims[i].text);

        for (const r of results) {
          if (!allSources.find((s) => s.id === r.id)) {
            allSources.push({
              id: r.id,
              cite: '',
              authorShort: r.authors.split(',')[0]?.trim() || 'Unknown',
              year: r.year,
              title: r.title,
              snippet: r.snippet,
              conf: 0,
              sourceApi: r.sourceApi,
            });
          }
        }

        emitProgress('searching', { claimIndex: i + 1, claimCount: claims.length });
      }

      // Step 3: Rank candidates for each claim
      await AutoCiteJobModel.findByIdAndUpdate(jobId, { status: 'matching' });
      emitProgress('matching');

      for (let i = 0; i < claims.length; i++) {
        const results = await CitationSearchService.searchAll(claims[i].text);
        const rankings = await CitationSearchService.rankCandidates(claims[i].text, results);
        claims[i].candidates = rankings.map((r) => ({
          sourceId: r.id,
          relevanceScore: r.score,
        }));

        // Update sources with ranking scores
        for (const ranking of rankings) {
          const src = allSources.find((s) => s.id === ranking.id);
          if (src) src.conf = Math.max(src.conf, ranking.score);
        }
      }

      // Step 4: Format citations
      await AutoCiteJobModel.findByIdAndUpdate(jobId, { status: 'formatting' });
      emitProgress('formatting');

      const searchResults = await CitationSearchService.searchAll(claimTexts[0] || text.slice(0, 200));
      for (const src of allSources) {
        const rawResult = searchResults.find((r) => r.id === src.id) || {
          authors: src.authorShort,
          title: src.title,
          year: src.year,
          journal: null,
          doi: null,
          url: null,
        };
        src.cite = await CitationSearchService.formatCitation(rawResult as any, style);
      }

      // Finalize
      await AutoCiteJobModel.findByIdAndUpdate(jobId, {
        status: 'done',
        claims,
        sources: allSources,
        creditsUsed: CreditCosts.AUTOCITE_PER_ANALYSIS,
      });

      await CreditService.deduct(
        userId,
        CreditCosts.AUTOCITE_PER_ANALYSIS,
        'autocite',
        jobId,
        'Auto-cite analysis'
      );

      emitProgress('done', { claims, sources: allSources });
    } catch (err: any) {
      await AutoCiteJobModel.findByIdAndUpdate(jobId, { status: 'failed' });
      emitProgress('failed', { error: err.message });
    }
  });

  return autociteQueue;
}

export default autociteQueue;
