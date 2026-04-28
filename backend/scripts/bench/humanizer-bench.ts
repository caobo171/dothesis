// backend/scripts/bench/humanizer-bench.ts

// CLI: benchmark a humanizer method against the fixed corpus.
//
// Usage:
//   ts-node backend/scripts/bench/humanizer-bench.ts \
//     --method M3 \
//     --text T1                 # or 'all'
//     --copyscape true|false    # default true
//     --out bench-results/M3.json
//
// Behavior:
//   - Loads the requested method from the registry (which auto-imports all known methods).
//   - Reads corpus texts from backend/scripts/bench/corpus/<id>.txt.
//   - Runs the method on each, captures tokens + duration.
//   - When --copyscape true, calls AIDetectorEngine.detect on input and output.
//   - Appends one BenchRecord per (method, text) to the output JSON file.

// Load .env BEFORE any service module is imported — openai.service.ts
// instantiates `new OpenAI()` at import time and reads OPENAI_API_KEY then.
import 'dotenv/config';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { getMethod } from '../../src/services/humanizer/methods';
import { AIDetectorEngine } from '../../src/services/ai-detector';
import { SaplingProvider } from '../../src/services/ai-detector/providers/sapling.provider';
import type { BenchRecord, MethodOptions } from '../../src/services/humanizer/methods/types';

type Args = {
  method: string;
  text: string;        // 'T1' | ... | 'T5' | 'all'
  copyscape: boolean;
  sapling: boolean;
  out: string;
};

function parseArgs(): Args {
  const argv = process.argv.slice(2);
  const get = (flag: string, def?: string) => {
    const i = argv.indexOf(flag);
    if (i < 0) return def;
    return argv[i + 1];
  };
  const method = get('--method');
  if (!method) throw new Error('--method required');
  return {
    method,
    text: get('--text', 'all')!,
    // Defaults flipped post-v10.1: Copyscape is out of credit on the project
    // account and the bake-off result already shipped (M19/M21 win). Sapling
    // is now the default judge for ongoing evaluation.
    copyscape: (get('--copyscape', 'false')!) === 'true',
    sapling: (get('--sapling', 'true')!) === 'true',
    out: get('--out', `bench-results/${method}.json`)!,
  };
}

const TEXT_IDS = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10', 'T11', 'T12'];
const CORPUS_DIR = path.resolve(__dirname, 'corpus');

function loadText(id: string): string {
  const p = path.join(CORPUS_DIR, `${id}.txt`);
  return fs.readFileSync(p, 'utf8').trim();
}

async function scoreCopyscape(text: string): Promise<number | null> {
  try {
    const r = await AIDetectorEngine.detect(text);
    return r.score;
  } catch (e) {
    console.error('[bench] Copyscape error:', (e as Error).message);
    return null;
  }
}

async function scoreSapling(provider: SaplingProvider, text: string): Promise<number | null> {
  try {
    const r = await provider.analyze(text);
    return r.score;
  } catch (e) {
    console.error('[bench] Sapling error:', (e as Error).message);
    return null;
  }
}

async function main() {
  const args = parseArgs();
  const method = getMethod(args.method);
  const ids = args.text === 'all' ? TEXT_IDS : [args.text];
  const opts: MethodOptions = { tone: 'academic', strength: 50, lengthMode: 'match' };
  const sapling = args.sapling ? new SaplingProvider() : null;

  const existing: BenchRecord[] = fs.existsSync(args.out)
    ? JSON.parse(fs.readFileSync(args.out, 'utf8'))
    : [];

  for (const textId of ids) {
    const input = loadText(textId);
    console.log(`[bench] ${method.id} on ${textId} (${input.split(/\s+/).length} words)`);

    const scoreIn = args.copyscape ? await scoreCopyscape(input) : null;
    const saplingIn = sapling ? await scoreSapling(sapling, input) : null;

    const t0 = Date.now();
    const result = await method.run(input, opts);
    const durationMs = Date.now() - t0;

    const scoreOut = args.copyscape ? await scoreCopyscape(result.output) : null;
    const saplingOut = sapling ? await scoreSapling(sapling, result.output) : null;

    const totalInputTokens = result.tokenSteps.reduce((s, x) => s + x.inputTokens, 0);
    const totalOutputTokens = result.tokenSteps.reduce((s, x) => s + x.outputTokens, 0);

    const record: BenchRecord = {
      methodId: method.id,
      textId,
      scoreIn,
      scoreOut,
      saplingIn,
      saplingOut,
      tokenSteps: result.tokenSteps,
      totalInputTokens,
      totalOutputTokens,
      durationMs,
      output: result.output,
    };

    const judges = [
      args.copyscape ? `cs ${scoreIn}→${scoreOut}` : null,
      args.sapling ? `sap ${saplingIn}→${saplingOut}` : null,
    ].filter(Boolean).join(' | ');
    console.log(`[bench] ${method.id}/${textId}: ${judges} | tokens ${totalInputTokens}→${totalOutputTokens} | ${durationMs}ms`);
    existing.push(record);
  }

  fs.mkdirSync(path.dirname(args.out), { recursive: true });
  fs.writeFileSync(args.out, JSON.stringify(existing, null, 2));
  console.log(`[bench] wrote ${existing.length} records to ${args.out}`);
}

main().catch(e => {
  console.error(e);
  process.exit(1);
});
