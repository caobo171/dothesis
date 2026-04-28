// Generate the v2 corpus extension (T6-T12) — broader coverage to stress-test
// the v10.1 router. Same generation method as generate-corpus.ts: Gemini with
// "make this sound clearly machine-generated" prompt, varied tones and lengths.

import * as fs from 'node:fs';
import * as path from 'node:path';
import 'dotenv/config';
import { GeminiService } from '../../src/services/ai/gemini.service';

type Spec = { id: string; tone: string; words: number; topic: string };

const CORPUS: Spec[] = [
  { id: 'T6',  tone: 'short paragraph (1 paragraph only)',     words: 80,   topic: 'why microservices add complexity' },
  { id: 'T7',  tone: 'long-form essay (3 paragraphs)',         words: 700,  topic: 'the social impact of streaming services on local bookstores' },
  { id: 'T8',  tone: 'how-to tutorial intro',                  words: 200,  topic: 'how to set up environment variables in a Node.js project' },
  { id: 'T9',  tone: 'news article style',                     words: 250,  topic: 'a new open-source LLM released this week with claimed GPT-4 parity' },
  { id: 'T10', tone: 'first-person personal story',            words: 180,  topic: 'my first time running a 10K race' },
  { id: 'T11', tone: 'business memo / internal email',         words: 150,  topic: 'announcement of a new flexible-work policy at a tech company' },
  { id: 'T12', tone: 'product review',                         words: 220,  topic: 'a wireless mechanical keyboard a writer has been using for 3 months' },
];

const SYSTEM = `You write text passages on demand. Output ONLY the requested passage — no preamble, no commentary, no markdown. Plain prose only.`;

const promptFor = (s: Spec) =>
  `Write a ${s.tone} of approximately ${s.words} words about: ${s.topic}.

Make it sound clearly machine-generated:
- Formal connectors ("Furthermore", "Moreover", "Additionally")
- Uniform sentence length (12-18 words each)
- Generic verb choices ("utilize", "facilitate", "leverage", "encompass")
- Parallel structures
- Sterile, predictable rhythm

Output ONLY the passage.`;

async function main() {
  const outDir = path.resolve(__dirname, 'corpus');
  for (const spec of CORPUS) {
    console.log(`[gen] ${spec.id}: ${spec.tone}, ~${spec.words}w on "${spec.topic}"`);
    const r = await GeminiService.chat(SYSTEM, promptFor(spec), {
      temperature: 0.7,
      maxTokens: 8192,
      jsonMode: false,
    });
    const text = r.text.trim();
    fs.writeFileSync(path.join(outDir, `${spec.id}.txt`), text + '\n');
    console.log(`[gen]  → ${text.split(/\s+/).length} words`);
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
