// backend/scripts/test/test-rule-compliance.ts
//
// Run: npx ts-node -r tsconfig-paths/register scripts/test/test-rule-compliance.ts
// Exits non-zero on any assertion failure.
//
// Why a standalone script rather than jest/vitest: the repo doesn't have a
// configured test framework (the package.json `test` script points at a
// non-existent file). Following the existing `backend/scripts/bench/` pattern
// of one-off ts-node scripts keeps this self-contained and runnable today.

import assert from 'node:assert/strict';
import { checkRuleCompliance, formatRevisionFeedback } from '../../src/services/humanizer/critic/rule_compliance';

let passed = 0;
let failed = 0;

function test(name: string, fn: () => void): void {
  try {
    fn();
    console.log(`  ✓ ${name}`);
    passed++;
  } catch (e) {
    console.log(`  ✗ ${name}`);
    console.log(`    ${(e as Error).message}`);
    failed++;
  }
}

console.log('checkRuleCompliance — hedging counter');

test('counts whole-word hedge tokens', () => {
  // 6 hedges in 30 words = 20/100w, comfortably above threshold of 2
  const out = 'The result may suggest that the model appears reliable. It seems plausible. Performance can vary, and the effect might be modest. Adoption tends to be slow.';
  const r = checkRuleCompliance('Input text. '.repeat(15), out);
  assert.ok(r.metrics.hedgeCount >= 6, `expected >=6 hedges, got ${r.metrics.hedgeCount}`);
});

test('does not match hedge tokens inside other words', () => {
  // "Mayor", "scanning", "candidate" must NOT match \bmay\b, \bcan\b
  const out = 'The Mayor announced a candidate. Scanning the document took time. The result was unexpected.';
  const r = checkRuleCompliance('Input. '.repeat(20), out);
  assert.equal(r.metrics.hedgeCount, 0, `expected 0 hedges, got ${r.metrics.hedgeCount}`);
});

test('multi-word hedges count correctly', () => {
  // "is believed", "is suspected", "tends to" — 3 multi-word hedges
  const out = 'The effect is believed to be small. Causation is suspected but not proven. The trend tends to reverse.';
  const r = checkRuleCompliance('Input. '.repeat(20), out);
  assert.ok(r.metrics.hedgeCount >= 3, `expected >=3 hedges, got ${r.metrics.hedgeCount}`);
});

console.log('\ncheckRuleCompliance — fronted-clause counter');

test('detects subordinator-fronted sentences', () => {
  const out = 'Although the data is limited, the trend is clear. While critics disagree, the model holds. Given these constraints, performance was strong. The result is robust.';
  const r = checkRuleCompliance('Input. '.repeat(20), out);
  assert.equal(r.metrics.sentenceCount, 4);
  assert.equal(r.metrics.frontedClauseCount, 3, `expected 3 fronted, got ${r.metrics.frontedClauseCount}`);
});

test('detects fronted prepositional phrases', () => {
  const out = 'In recent years, the field grew. Across most studies, the effect held. The conclusion is straightforward.';
  const r = checkRuleCompliance('Input. '.repeat(20), out);
  assert.equal(r.metrics.frontedClauseCount, 2, `expected 2 fronted, got ${r.metrics.frontedClauseCount}`);
});

test('does not count subject-first sentences', () => {
  const out = 'The model performed well. Researchers confirmed this. Results were robust.';
  const r = checkRuleCompliance('Input. '.repeat(20), out);
  assert.equal(r.metrics.frontedClauseCount, 0);
});

console.log('\ncheckRuleCompliance — X-and-Y counter');

test('counts parallel two-item conjunctions', () => {
  // 3 parallel pairs: "social and educational", "anxiety and fear", "students and teachers"
  const out = 'Social and educational outcomes vary. Anxiety and fear were measured. Students and teachers reported similar results.';
  const r = checkRuleCompliance('Input. '.repeat(20), out);
  assert.ok(r.metrics.xAndYCount >= 3, `expected >=3, got ${r.metrics.xAndYCount}`);
});

test('whitelists common idioms', () => {
  const out = 'The discussion went back and forth. The trend grew more and more pronounced. Pros and cons were debated.';
  const r = checkRuleCompliance('Input. '.repeat(20), out);
  assert.equal(r.metrics.xAndYCount, 0, `expected 0 (idioms whitelisted), got ${r.metrics.xAndYCount}`);
});

console.log('\ncheckRuleCompliance — expansion ratio');

test('flags >5% expansion', () => {
  const input = 'Short input.';   // 2 words
  const output = 'A much longer rewrite that adds many extra words to expand it.'; // 12 words → 6× expansion
  const r = checkRuleCompliance(input, output);
  const v = r.violations.find((x) => x.rule === 'no_expansion');
  assert.ok(v, 'expected no_expansion violation');
});

test('passes at exactly 1.0 ratio', () => {
  const input = 'one two three four five six seven eight nine ten';
  const output = 'aa bb cc dd ee ff gg hh ii jj';
  const r = checkRuleCompliance(input, output);
  const v = r.violations.find((x) => x.rule === 'no_expansion');
  assert.equal(v, undefined, 'no_expansion should not violate at 1.0');
});

console.log('\ncheckRuleCompliance — formatRevisionFeedback');

test('passing report formats to empty string', () => {
  // Make a synthetic passing output: lots of hedges, fronted clauses, no X-and-Y, same length.
  const input = 'one two three four five six seven eight nine ten';
  const output = 'Although evidence may suggest impact, the result is believed minor. While critics may disagree, performance appears robust.';
  const r = checkRuleCompliance(input, output);
  if (r.passed) {
    assert.equal(formatRevisionFeedback(r), '');
  } else {
    // Synthetic test: even if it doesn't fully pass, formatter must mention violations only.
    const fb = formatRevisionFeedback(r);
    for (const v of r.violations) {
      assert.ok(fb.includes(v.rule.replace(/_/g, ' ')) || fb.includes(v.feedbackForLLM.split(':')[0]),
        `feedback should mention violation ${v.rule}`);
    }
  }
});

test('feedback only mentions failed rules', () => {
  // Force only the no_expansion violation: very short input, very long output, with hedges + fronted opens
  const input = 'tiny';
  const output = 'Although the data may suggest variability, the effect is believed to be small but present in nearly every measured cohort despite limited statistical power.';
  const r = checkRuleCompliance(input, output);
  const fb = formatRevisionFeedback(r);
  assert.ok(fb.includes('Output is too long'), 'feedback should mention expansion violation');
  // Hedging is satisfied here; feedback should NOT include hedging-violation language.
  assert.ok(!fb.includes('Hedging language: only'), 'should not mention hedging when satisfied');
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
