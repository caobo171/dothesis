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

  // Decision: Static sample texts for users to quickly test Auto-Cite.
  // Each sample contains academic claims that need citations, making the feature's value immediately clear.
  router.get('/cite/samples', (_req, res) => {
    const SAMPLE_TEXTS = [
      {
        id: 'psychology',
        label: 'Psychology Essay',
        text: `Cognitive behavioral therapy has been shown to be effective in treating major depressive disorder, with meta-analyses reporting response rates of approximately 60%. The development of CBT was heavily influenced by Aaron Beck's cognitive model of depression, which posits that negative automatic thoughts maintain depressive symptoms. Recent studies have demonstrated that combining CBT with pharmacotherapy yields superior outcomes compared to either treatment alone. Furthermore, mindfulness-based cognitive therapy has emerged as a promising approach for preventing relapse in patients with recurrent depression. Neuroimaging research has revealed that successful CBT treatment is associated with changes in prefrontal cortex activation patterns.`,
      },
      {
        id: 'climate',
        label: 'Climate Science',
        text: `Global mean surface temperature has increased by approximately 1.1°C since the pre-industrial era, primarily driven by anthropogenic greenhouse gas emissions. The Intergovernmental Panel on Climate Change has concluded that human influence on the climate system is unequivocal. Arctic sea ice extent has declined at a rate of 13% per decade since satellite observations began in 1979. Ocean acidification, caused by absorption of atmospheric CO2, threatens marine ecosystems and coral reef biodiversity. Climate models project that without significant emission reductions, global temperatures could rise by 2.1 to 3.5°C by the end of this century.`,
      },
      {
        id: 'education',
        label: 'Education Research',
        text: `Formative assessment practices have been associated with significant gains in student achievement across diverse educational contexts. Research by Black and Wiliam demonstrated that effective feedback can produce learning gains equivalent to one to two grade levels. The Zone of Proximal Development, a concept introduced by Vygotsky, remains foundational to understanding scaffolded instruction. Studies indicate that collaborative learning strategies improve both academic performance and social skills among elementary school students. The implementation of universal design for learning principles has shown promise in creating more inclusive classroom environments for students with diverse learning needs.`,
      },
      {
        id: 'business',
        label: 'Business Analysis',
        text: `The resource-based view of the firm suggests that sustainable competitive advantage derives from valuable, rare, inimitable, and non-substitutable resources. Porter's five forces framework remains widely used for analyzing industry attractiveness and competitive dynamics. Research has shown that companies with higher levels of employee engagement report 21% greater profitability. The adoption of agile methodologies in software development has been linked to improved project success rates and customer satisfaction. Digital transformation initiatives have been found to increase organizational revenue by an average of 23% compared to industry peers.`,
      },
      {
        id: 'education-vi',
        label: 'Nghiên cứu giáo dục (Tiếng Việt)',
        text: `Phương pháp đánh giá quá trình đã được chứng minh có tác động tích cực đến kết quả học tập của sinh viên trong nhiều bối cảnh giáo dục khác nhau. Nghiên cứu của Bloom cho thấy phương pháp dạy học cá nhân hóa có thể giúp 90% học sinh đạt mức thành tích mà chỉ 20% đạt được trong lớp học truyền thống. Lý thuyết kiến tạo của Piaget vẫn là nền tảng quan trọng trong việc thiết kế chương trình giảng dạy bậc đại học tại Việt Nam. Các nghiên cứu gần đây chỉ ra rằng việc tích hợp công nghệ thông tin vào giảng dạy làm tăng động lực học tập của sinh viên lên 35%. Mô hình học tập kết hợp (blended learning) đã cho thấy hiệu quả vượt trội so với phương pháp giảng dạy truyền thống trong giáo dục đại học Việt Nam.`,
      },
    ];

    return res.json({ code: Code.Success, data: SAMPLE_TEXTS });
  });

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
