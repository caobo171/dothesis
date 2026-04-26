/**
 * GPTZero AI Detection Provider (Stub)
 *
 * Integrate when ready:
 * 1. Sign up at https://gptzero.me/api
 * 2. Set GPTZERO_API_KEY in .env
 * 3. Set AI_DETECTOR_PROVIDER=gptzero in .env
 *
 * API docs: https://gptzero.me/docs
 * Pricing: Starts at $18/month for API access
 */

import axios from 'axios';
import { AIDetectionProvider, AIDetectionResult } from '../types';

export class GPTZeroProvider implements AIDetectionProvider {
  readonly name = 'gptzero';
  private apiKey: string;

  constructor() {
    this.apiKey = process.env.GPTZERO_API_KEY || '';
    if (!this.apiKey) {
      console.warn('[AIDetector] GPTZERO_API_KEY not set — provider will fail on calls');
    }
  }

  async analyze(text: string): Promise<AIDetectionResult> {
    const res = await axios.post(
      'https://api.gptzero.me/v2/predict/text',
      { document: text },
      {
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': this.apiKey,
        },
        timeout: 15000,
      }
    );

    const data = res.data;
    const score = Math.round((data.documents?.[0]?.average_generated_prob ?? 0.5) * 100);

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
