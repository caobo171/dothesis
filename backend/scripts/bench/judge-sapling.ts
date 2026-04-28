// Score existing bench results against Sapling as a second judge.
// Reads a bench results JSON (array of BenchRecord), calls Sapling on
// scoreIn-text and scoreOut-text for each row, writes augmented JSON
// with saplingIn / saplingOut fields.
//
// Usage:
//   ts-node scripts/bench/judge-sapling.ts <input.json> [output.json]

import 'dotenv/config';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { SaplingProvider } from '../../src/services/ai-detector/providers/sapling.provider';

type BenchRecord = {
  methodId: string;
  textId: string;
  scoreIn: number | null;
  scoreOut: number | null;
  output: string;
  // We add these:
  saplingIn?: number;
  saplingOut?: number;
};

async function main() {
  const inPath = process.argv[2];
  if (!inPath) throw new Error('usage: judge-sapling <bench.json> [out.json]');
  const outPath = process.argv[3] || inPath.replace(/\.json$/, '.sapling.json');
  const corpusDir = path.resolve(__dirname, 'corpus');

  const records: BenchRecord[] = JSON.parse(fs.readFileSync(inPath, 'utf8'));
  const sapling = new SaplingProvider();

  for (const r of records) {
    const inputText = fs.readFileSync(path.join(corpusDir, `${r.textId}.txt`), 'utf8').trim();

    process.stdout.write(`[sapling] ${r.methodId}/${r.textId} … `);
    try {
      const inRes = await sapling.analyze(inputText);
      const outRes = await sapling.analyze(r.output);
      r.saplingIn = inRes.score;
      r.saplingOut = outRes.score;
      console.log(`in=${r.saplingIn} out=${r.saplingOut}  (copyscape: ${r.scoreIn} → ${r.scoreOut})`);
    } catch (e) {
      console.log('ERROR', (e as Error).message);
    }
  }

  fs.writeFileSync(outPath, JSON.stringify(records, null, 2));
  console.log(`wrote ${outPath}`);

  // Side-by-side summary
  console.log('\n--- side-by-side ---');
  console.log('Text | Copyscape (in→out, drop) | Sapling (in→out, drop)');
  for (const r of records) {
    const cDrop = (r.scoreIn ?? 0) - (r.scoreOut ?? 0);
    const sDrop = (r.saplingIn ?? 0) - (r.saplingOut ?? 0);
    console.log(`${r.textId}   | ${r.scoreIn} → ${r.scoreOut} (Δ${cDrop})   | ${r.saplingIn} → ${r.saplingOut} (Δ${sDrop})`);
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
