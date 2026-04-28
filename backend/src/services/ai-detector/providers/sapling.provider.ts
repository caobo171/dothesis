/**
 * Sapling AI Detection Provider
 *
 * Calls Sapling's /api/v1/aidetect endpoint as a second-opinion judge alongside
 * Copyscape. Used primarily in the bench harness to compare detector verdicts
 * (e.g. when one detector says "human" and another says "AI", we know our
 * humanizer is over-fitting to the agreeable detector).
 *
 * Sapling returns score ∈ [0, 1] where 0 = human, 1 = AI. We convert to our
 * 0-100 integer scale to match Copyscape's representation.
 *
 * Trial keys: 50,000 chars / 24h. Pricing: usage-based for production.
 * Docs: https://sapling.ai/docs/api/detector/
 */

import axios from 'axios';
import { AIDetectionProvider, AIDetectionResult } from '../types';

const SAPLING_API_URL = 'https://api.sapling.ai/api/v1/aidetect';

export class SaplingProvider implements AIDetectionProvider {
  readonly name = 'sapling';

  private apiKey: string;

  constructor() {
    this.apiKey = process.env.SAPLING_API_KEY || '';
    if (!this.apiKey) {
      console.warn('[AIDetector] SAPLING_API_KEY not set — SaplingProvider will fail on calls');
    }
  }

  async analyze(text: string): Promise<AIDetectionResult> {
    const res = await axios.post(
      SAPLING_API_URL,
      {
        key: this.apiKey,
        text,
        sent_scores: false,   // we only need the aggregate score for the bake-off
        score_string: false,  // skip the HTML heatmap to keep responses small
      },
      {
        headers: { 'Content-Type': 'application/json' },
        timeout: 90000,
      },
    );

    const data = res.data;
    if (typeof data.score !== 'number') {
      throw new Error(`Sapling response missing score: ${JSON.stringify(data).slice(0, 200)}`);
    }

    // 0 → human, 1 → AI. Multiply to match the 0-100 scale used by Copyscape and
    // the rest of the humanizer pipeline.
    const score = Math.round(data.score * 100);

    return {
      score,
      metrics: {
        sentenceLengthVariance: 0,
        vocabularyDiversity: 0,
        burstiness: 0,
        transitionDensity: 0,
        sentenceStarterDiversity: 0,
        humanMarkers: 0,
        punctuationDiversity: 0,
      },
      language: 'en',
      provider: this.name,
    };
  }
}
