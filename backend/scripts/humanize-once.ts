// Humanize a single text file via the integrated v8.1 pipeline + Copyscape.
// Usage: ts-node scripts/humanize-once.ts <input-path> [output-path]
import 'dotenv/config';
import * as fs from 'node:fs';
import { HumanizerService } from '../src/services/humanizer/humanizer.service';

async function main() {
  const inPath = process.argv[2];
  if (!inPath) throw new Error('usage: humanize-once <input-path> [output-path]');
  const outPath = process.argv[3] || inPath.replace(/(\.txt)?$/, '.humanized.txt');
  const text = fs.readFileSync(inPath, 'utf8').trim();
  console.log('Input (' + text.split(/\s+/).length + ' words):\n' + text + '\n');
  const r = await HumanizerService.humanizePipeline(text, 'academic', 50, 'match');
  fs.writeFileSync(outPath, r.rewrittenText + '\n');
  console.log('--- v8.1 OUTPUT ---');
  console.log(r.rewrittenText);
  console.log('---');
  console.log('Copyscape:', r.aiScoreIn, '→', r.aiScoreOut);
  console.log('Tokens:', r.tokenUsage.totalInputTokens, '→', r.tokenUsage.totalOutputTokens);
  console.log('Wrote:', outPath);
}

main().catch((e) => { console.error(e); process.exit(1); });
