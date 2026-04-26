/**
 * AI Detector Calibration Test
 *
 * Scores sample texts with the statistical detector — no LLM needed.
 *
 * Usage:
 *   cd backend
 *   npm run score
 */

import { StatisticalDetectionProvider } from '@/services/ai-detector/providers/statistical.provider';
import * as fs from 'fs';
import * as path from 'path';

const detector = new StatisticalDetectionProvider();

const SAMPLES: Array<{ name: string; text: string; expectedRange: [number, number] }> = [
  {
    name: 'AI-generated English (should score 50-85)',
    text: fs.readFileSync(path.resolve(__dirname, '../../../tests/humanizer/en.txt'), 'utf-8').trim(),
    expectedRange: [50, 85],
  },
  {
    name: 'AI-generated Vietnamese (should score 55-85)',
    text: fs.readFileSync(path.resolve(__dirname, '../../../tests/humanizer/vi.txt'), 'utf-8').trim(),
    expectedRange: [55, 85],
  },
  {
    name: 'Human-written English (should score 15-45)',
    text: `I've been thinking about this problem for a while now, and honestly? I'm not sure there's a clean answer. The data seems to suggest one thing — higher engagement correlates with better outcomes — but my gut tells me we're missing something. Maybe it's the sample size. Or maybe (and this is what keeps me up at night) we're measuring the wrong thing entirely. Anyway, that's just my take. Could be totally wrong.`,
    expectedRange: [15, 45],
  },
  {
    name: 'Human-written Vietnamese (should score 10-45)',
    text: `Nói thật thì mình cũng không chắc lắm về kết quả này. Dữ liệu có vẻ cho thấy một xu hướng rõ ràng — sinh viên tham gia nhiều hơn thì kết quả tốt hơn — nhưng mình cảm giác là thiếu gì đó. Có lẽ là do mẫu quá nhỏ? Hoặc có thể (và đây là điều mình suy nghĩ nhiều nhất) chúng ta đang đo sai thứ. Dù sao đi nữa, đây chỉ là ý kiến cá nhân thôi.`,
    expectedRange: [10, 45],
  },
  {
    name: 'Mixed text (should score 25-60)',
    text: `The research methodology involved a mixed-methods approach combining quantitative surveys with qualitative interviews. Honestly, the interview data was way more interesting than the numbers — people said things I never expected. Furthermore, the statistical analysis revealed significant correlations between variables. But here's the thing: correlation isn't causation, and I think we'd be foolish to ignore that.`,
    expectedRange: [25, 60],
  },
];

async function main() {
  console.log('');
  console.log('╔══════════════════════════════════════════════════════════╗');
  console.log('║          DoThesis AI Detector Calibration Test          ║');
  console.log('╚══════════════════════════════════════════════════════════╝');
  console.log(`  Provider: ${detector.name}`);
  console.log('');

  let passed = 0;

  for (const sample of SAMPLES) {
    const result = await detector.analyze(sample.text);
    const inRange = result.score >= sample.expectedRange[0] && result.score <= sample.expectedRange[1];
    const status = inRange ? '✅' : '❌';
    if (inRange) passed++;

    console.log(`${status} ${sample.name}`);
    console.log(`   Score: ${result.score}%  (expected: ${sample.expectedRange[0]}-${sample.expectedRange[1]}%)`);
    console.log(`   Language: ${result.language}`);
    console.log(`   Metrics:`);

    for (const [key, value] of Object.entries(result.metrics)) {
      const label = key.replace(/([A-Z])/g, ' $1').trim();
      const bar = '█'.repeat(Math.floor(value / 5)) + '░'.repeat(20 - Math.floor(value / 5));
      console.log(`     ${label.padEnd(28)} ${bar} ${value}%`);
    }
    console.log('');
  }

  console.log(`${'='.repeat(60)}`);
  console.log(`  Result: ${passed}/${SAMPLES.length} passed`);
  console.log('');

  if (passed < SAMPLES.length) process.exit(1);
}

main().catch(console.error);
