// backend/src/scripts/test-perturbation.ts

// Decision: Standalone assertion test script following the project's existing pattern
// (see score-samples.ts). No Jest/Mocha — runs via `npx ts-node`. Each test logs
// pass/fail with a descriptive message.

import * as assert from 'assert';
import { PerturbationEngine } from '@/services/humanizer/perturbation/perturbation.engine';
import {
  synonymSwap,
  toggleContraction,
  injectHumanMarker,
  splitSentence,
  varyPunctuation,
  varyStarter,
} from '@/services/humanizer/perturbation/operations';

// Seeded RNG for deterministic tests (mulberry32)
function seededRng(seed: number): () => number {
  return function () {
    seed |= 0;
    seed = (seed + 0x6D2B79F5) | 0;
    let t = seed;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

let passed = 0;
let failed = 0;

function test(name: string, fn: () => void) {
  try {
    fn();
    console.log(`  ✓ ${name}`);
    passed++;
  } catch (err: any) {
    console.log(`  ✗ ${name}`);
    console.log(`      ${err.message}`);
    failed++;
  }
}

console.log('\n=== Perturbation Operations ===\n');

test('synonymSwap replaces a known word in EN', () => {
  const result = synonymSwap('This is an important finding.', 'en', seededRng(1));
  assert.notStrictEqual(result, 'This is an important finding.');
  assert.match(result, /This is an (key|central|big|real) finding\./);
});

test('synonymSwap returns input unchanged when no matches', () => {
  const result = synonymSwap('Quick fox jumps.', 'en', seededRng(1));
  assert.strictEqual(result, 'Quick fox jumps.');
});

test('synonymSwap preserves capitalization for sentence-start words', () => {
  const result = synonymSwap('Important findings emerged.', 'en', seededRng(1));
  assert.match(result, /^[A-Z]/);
});

test('toggleContraction contracts "do not" → "don\'t"', () => {
  const result = toggleContraction('We do not agree with the conclusion.', 'en', seededRng(1));
  assert.match(result, /don't/);
});

test('toggleContraction is a no-op for Vietnamese', () => {
  const input = 'Chúng tôi không đồng ý với kết luận.';
  const result = toggleContraction(input, 'vi', seededRng(1));
  assert.strictEqual(result, input);
});

test('injectHumanMarker prepends a filler phrase in EN', () => {
  const result = injectHumanMarker('The data is clear.', 'en', seededRng(1));
  assert.match(result, /^(Honestly|Look|I mean|Actually|Frankly|Truthfully|In reality|To be fair|Granted|Sure), /);
});

test('injectHumanMarker prepends a filler phrase in VI', () => {
  const result = injectHumanMarker('Dữ liệu rất rõ ràng.', 'vi', seededRng(1));
  assert.match(result, /^(Thực ra|Nói thật|Thẳng thắn mà nói|Theo mình|Nhìn chung|Có điều|Thật ra|Phải công nhận), /);
});

test('splitSentence splits at a comma into two sentences', () => {
  const input = 'The teacher walked into the room, and everyone went silent immediately.';
  const result = splitSentence(input, 'en', seededRng(1));
  assert.notStrictEqual(result, input);
  assert.ok(result.includes('. '), 'Expected a period+space mid-string');
});

test('splitSentence is a no-op when no commas present', () => {
  const input = 'This sentence has no commas.';
  const result = splitSentence(input, 'en', seededRng(1));
  assert.strictEqual(result, input);
});

test('varyPunctuation replaces a comma with em dash, semicolon, or ellipsis', () => {
  const input = 'The data, which was collected last year, shows growth.';
  const result = varyPunctuation(input, 'en', seededRng(1));
  assert.notStrictEqual(result, input);
  assert.ok(result.includes(' —') || result.includes(';') || result.includes(' …'));
});

test('varyStarter prepends And/But/So', () => {
  const result = varyStarter('The findings were unexpected.', 'en', seededRng(1));
  assert.match(result, /^(And |But |So |Still, |Yet |Plus, )/);
});

console.log('\n=== PerturbationEngine ===\n');

test('PerturbationEngine.getRate scales with strength', () => {
  assert.strictEqual(PerturbationEngine.getRate(20), 0.20);
  assert.strictEqual(PerturbationEngine.getRate(50), 0.35);
  assert.strictEqual(PerturbationEngine.getRate(80), 0.50);
});

test('PerturbationEngine.perturb produces different output from input (EN, strength 50)', () => {
  const input = 'The research demonstrates that machine learning is important. ' +
    'Significant findings emerged from the analysis. ' +
    'Furthermore, the results enable us to consider new approaches. ' +
    'It is important to note that these benefits are substantial.';
  // Decision: seed 1 chosen because it produces rng values ≤ 0.35 for sentence 2
  // (seed 42 happens to roll above rate for all sentences, never triggering perturbation).
  const result = PerturbationEngine.perturb(input, 50, seededRng(1));
  assert.notStrictEqual(result, input, 'Output should differ from input');
});

test('PerturbationEngine.perturb produces different output from input (VI, strength 50)', () => {
  const input = 'Nghiên cứu thể hiện rằng học máy quan trọng. ' +
    'Yếu tố này đóng vai trò đáng kể trong phương pháp mới. ' +
    'Ngoài ra, kết quả cho thấy lợi ích rõ ràng cần thiết.';
  // Decision: seed 1 chosen because it reliably triggers perturbation on sentence 2.
  const result = PerturbationEngine.perturb(input, 50, seededRng(1));
  assert.notStrictEqual(result, input);
});

test('PerturbationEngine.perturb is deterministic with seeded rng', () => {
  const input = 'The research demonstrates important findings.';
  const a = PerturbationEngine.perturb(input, 50, seededRng(42));
  const b = PerturbationEngine.perturb(input, 50, seededRng(42));
  assert.strictEqual(a, b, 'Same seed should produce same output');
});

test('PerturbationEngine.perturb preserves text length within reasonable bounds', () => {
  const input = 'The research demonstrates that machine learning is important. ' +
    'Significant findings emerged from the analysis.';
  const result = PerturbationEngine.perturb(input, 50, seededRng(7));
  // Output should be within 50%-200% of input length
  assert.ok(result.length > input.length * 0.5, 'Output too short');
  assert.ok(result.length < input.length * 2.0, 'Output too long');
});

console.log(`\n=== Results: ${passed} passed, ${failed} failed ===\n`);
process.exit(failed === 0 ? 0 : 1);
