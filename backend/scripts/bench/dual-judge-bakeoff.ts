// Re-bake-off: run all 8 candidate methods on T1-T5 against BOTH Copyscape
// and Sapling. Scores each input once and caches it so we don't pay for
// redundant input judging across methods. Writes one consolidated JSON.
//
// Usage:
//   ts-node scripts/bench/dual-judge-bakeoff.ts [--methods M1,M2,...] [--out path]
//
// Defaults: methods = M1..M8 ; out = bench-results/dual-judge.json
//
// One-time spend (rough):
//   - Input judging:    5 texts × 2 judges = 10 calls (cached, ~$0.50)
//   - Pipeline runs:    5 texts × 8 methods = 40 humanize runs (~30 min LLM)
//   - Output judging:   40 outputs × 2 judges = 80 calls (~$3-5)

import 'dotenv/config';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { getMethod, listMethods } from '../../src/services/humanizer/methods';
import { AIDetectorEngine } from '../../src/services/ai-detector';
import { SaplingProvider } from '../../src/services/ai-detector/providers/sapling.provider';
import type { BenchRecord, MethodOptions } from '../../src/services/humanizer/methods/types';

const TEXT_IDS = ['T1', 'T2', 'T3', 'T4', 'T5'];
const CORPUS_DIR = path.resolve(__dirname, 'corpus');

function getArg(flag: string, def?: string): string | undefined {
  const i = process.argv.indexOf(flag);
  return i < 0 ? def : process.argv[i + 1];
}

async function copyscape(text: string): Promise<number | null> {
  try { return (await AIDetectorEngine.detect(text)).score; }
  catch (e) { console.error('  copyscape err:', (e as Error).message); return null; }
}

async function sapling(prov: SaplingProvider, text: string): Promise<number | null> {
  try { return (await prov.analyze(text)).score; }
  catch (e) { console.error('  sapling err:', (e as Error).message); return null; }
}

async function main() {
  const methodsArg = getArg('--methods');
  const out = getArg('--out', 'bench-results/dual-judge.json')!;
  const methods = methodsArg
    ? methodsArg.split(',')
    : listMethods().map((m) => m.id).filter((id) => id !== 'M0');
  console.log(`[bakeoff] methods: ${methods.join(',')}`);
  console.log(`[bakeoff] texts:   ${TEXT_IDS.join(',')}`);

  const sap = new SaplingProvider();
  const opts: MethodOptions = { tone: 'academic', strength: 50, lengthMode: 'match' };

  // 1. Score each input once (cache).
  console.log('\n[bakeoff] scoring inputs (cached for all methods)…');
  const inputs: Record<string, { text: string; cs: number | null; sap: number | null }> = {};
  for (const id of TEXT_IDS) {
    const text = fs.readFileSync(path.join(CORPUS_DIR, `${id}.txt`), 'utf8').trim();
    const cs = await copyscape(text);
    const s = await sapling(sap, text);
    inputs[id] = { text, cs, sap: s };
    console.log(`  ${id}: cs=${cs} sap=${s}`);
  }

  // 2. Run each method on each text, score output with both judges.
  const records: BenchRecord[] = [];
  let runIdx = 0;
  const total = methods.length * TEXT_IDS.length;
  for (const mid of methods) {
    let method;
    try { method = getMethod(mid); }
    catch (e) { console.log(`[bakeoff] skip ${mid}: ${(e as Error).message}`); continue; }
    for (const tid of TEXT_IDS) {
      runIdx++;
      const inp = inputs[tid];
      const t0 = Date.now();
      let result;
      try { result = await method.run(inp.text, opts); }
      catch (e) {
        console.log(`[${runIdx}/${total}] ${mid}/${tid} FAILED: ${(e as Error).message}`);
        continue;
      }
      const durationMs = Date.now() - t0;
      const csOut = await copyscape(result.output);
      const sapOut = await sapling(sap, result.output);

      const totIn = result.tokenSteps.reduce((s, x) => s + x.inputTokens, 0);
      const totOut = result.tokenSteps.reduce((s, x) => s + x.outputTokens, 0);
      const rec: BenchRecord = {
        methodId: mid,
        textId: tid,
        scoreIn: inp.cs,
        scoreOut: csOut,
        saplingIn: inp.sap,
        saplingOut: sapOut,
        tokenSteps: result.tokenSteps,
        totalInputTokens: totIn,
        totalOutputTokens: totOut,
        durationMs,
        output: result.output,
      };
      records.push(rec);
      console.log(`[${runIdx}/${total}] ${mid}/${tid}: cs ${inp.cs}→${csOut} | sap ${inp.sap}→${sapOut} | ${durationMs}ms`);

      // Persist incrementally so we don't lose data on crash.
      fs.mkdirSync(path.dirname(out), { recursive: true });
      fs.writeFileSync(out, JSON.stringify(records, null, 2));
    }
  }

  console.log(`\n[bakeoff] wrote ${records.length} records to ${out}`);

  // 3. Summary table.
  console.log('\n--- summary (mean drop across T1-T5) ---');
  const byMethod: Record<string, { csDrops: number[]; sapDrops: number[] }> = {};
  for (const r of records) {
    byMethod[r.methodId] ||= { csDrops: [], sapDrops: [] };
    if (r.scoreIn != null && r.scoreOut != null) byMethod[r.methodId].csDrops.push(r.scoreIn - r.scoreOut);
    if (r.saplingIn != null && r.saplingOut != null) byMethod[r.methodId].sapDrops.push(r.saplingIn - r.saplingOut);
  }
  console.log('Method | cs mean drop | sap mean drop');
  for (const [m, d] of Object.entries(byMethod)) {
    const cs = d.csDrops.length ? (d.csDrops.reduce((a, b) => a + b, 0) / d.csDrops.length).toFixed(1) : '—';
    const sp = d.sapDrops.length ? (d.sapDrops.reduce((a, b) => a + b, 0) / d.sapDrops.length).toFixed(1) : '—';
    console.log(`${m}    | ${cs}        | ${sp}`);
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
