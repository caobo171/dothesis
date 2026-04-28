// backend/scripts/bench/generate-corpus.ts
//
// One-shot script to generate the 5 fixed AI-written corpus texts via Gemini.
// Run once; commit the resulting .txt files; never run again — corpus must be
// stable across the bake-off.

import * as fs from 'node:fs';
import * as path from 'node:path';
import 'dotenv/config';
import { GeminiService } from '../../src/services/ai/gemini.service';

type CorpusSpec = { id: string; tone: string; words: number; topic: string };

const CORPUS: CorpusSpec[] = [
  { id: 'T1', tone: 'academic literature review',     words: 100, topic: 'recent advances in transformer attention mechanisms' },
  { id: 'T2', tone: 'technical explainer',            words: 250, topic: 'how vector databases enable semantic search' },
  { id: 'T3', tone: 'argumentative essay',            words: 400, topic: 'why universal basic income would harm productivity' },
  { id: 'T4', tone: 'conversational blog',            words: 150, topic: 'my experience starting a morning routine' },
  { id: 'T5', tone: 'formal report',                  words: 500, topic: 'Q1 2026 outlook for the global lithium market' },
];

const SYSTEM_PROMPT = `You write text passages on demand. Output ONLY the requested passage — no preamble, no commentary, no markdown formatting, no quotation marks around it. Plain prose only.`;

const userPromptFor = (spec: CorpusSpec) =>
  `Write a ${spec.tone} passage of approximately ${spec.words} words about: ${spec.topic}.

Make it sound clearly machine-generated:
- Use formal connectors ("Furthermore", "Moreover", "Additionally")
- Uniform sentence length (12-18 words each)
- Generic verb choices ("utilize", "facilitate", "leverage", "encompass")
- Parallel structures across sentences
- Sterile, predictable rhythm

Output ONLY the passage.`;

async function main() {
  const outDir = path.resolve(__dirname, 'corpus');
  fs.mkdirSync(outDir, { recursive: true });

  for (const spec of CORPUS) {
    console.log(`[gen] ${spec.id}: ${spec.tone}, ~${spec.words} words on "${spec.topic}"`);
    // 8192 to leave headroom for Gemini 3's reasoning tokens (which count
    // against maxOutputTokens and otherwise cause mid-sentence truncation
    // on prompts that ask for prose passages).
    const r = await GeminiService.chat(SYSTEM_PROMPT, userPromptFor(spec), {
      temperature: 0.7,
      maxTokens: 8192,
      jsonMode: false,
    });
    const text = r.text.trim();
    const wc = text.split(/\s+/).length;
    const outPath = path.join(outDir, `${spec.id}.txt`);
    fs.writeFileSync(outPath, text + '\n');
    console.log(`[gen] wrote ${outPath} — ${wc} words (target ${spec.words})`);
  }
}

main().catch(e => {
  console.error(e);
  process.exit(1);
});
