// Smoke test: invoke HumanizerService.humanizePipeline (now v8) on T1.
import 'dotenv/config';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { HumanizerService } from '../src/services/humanizer/humanizer.service';

async function main() {
  const corpusPath = path.resolve(__dirname, 'bench/corpus/T1.txt');
  const text = fs.readFileSync(corpusPath, 'utf8').trim();
  console.log('Smoke input (' + text.split(/\s+/).length + ' words):\n' + text + '\n');
  const r = await HumanizerService.humanizePipeline(text, 'academic', 50, 'match');
  console.log('--- v8 OUTPUT ---');
  console.log(r.rewrittenText);
  console.log('---');
  console.log('Score:', r.aiScoreIn, '→', r.aiScoreOut);
  console.log('Tokens:', r.tokenUsage.totalInputTokens, '→', r.tokenUsage.totalOutputTokens);
  if (r.aiScoreOut === null || r.aiScoreOut > 50) {
    console.log('ACCEPTANCE: scoreOut=' + r.aiScoreOut + ' (target <50). MISS.');
    process.exit(2);
  }
  console.log('ACCEPTANCE: scoreOut=' + r.aiScoreOut + ' (target <50). PASS.');
}

main().catch((e) => { console.error(e); process.exit(1); });
