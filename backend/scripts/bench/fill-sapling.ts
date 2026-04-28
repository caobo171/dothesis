// Fill in missing saplingOut values on an existing bench-results JSON.
// Skips records that already have saplingOut. Persists incrementally so
// re-running the script picks up where it left off if interrupted.
//
// Usage: ts-node scripts/bench/fill-sapling.ts <bench.json>

import 'dotenv/config';
import * as fs from 'node:fs';
import { SaplingProvider } from '../../src/services/ai-detector/providers/sapling.provider';
import type { BenchRecord } from '../../src/services/humanizer/methods/types';

async function main() {
  const inPath = process.argv[2];
  if (!inPath) throw new Error('usage: fill-sapling <bench.json>');

  const records: BenchRecord[] = JSON.parse(fs.readFileSync(inPath, 'utf8'));
  const sap = new SaplingProvider();

  const todo = records.filter((r) => r.saplingOut == null && r.output);
  console.log(`[fill] ${todo.length} of ${records.length} records need saplingOut`);

  for (let i = 0; i < todo.length; i++) {
    const r = todo[i];
    process.stdout.write(`[${i + 1}/${todo.length}] ${r.methodId}/${r.textId} … `);
    try {
      const res = await sap.analyze(r.output);
      r.saplingOut = res.score;
      console.log(`sap out=${r.saplingOut}  (cs out=${r.scoreOut})`);
    } catch (e) {
      console.log('ERROR', (e as Error).message);
      r.saplingOut = null;
    }
    // Persist incrementally.
    fs.writeFileSync(inPath, JSON.stringify(records, null, 2));
  }

  console.log(`\n[fill] complete. Updated ${inPath}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
