/**
 * Winston AI Detection Provider (Stub)
 *
 * Integrate when ready:
 * 1. Sign up at https://gowinston.ai
 * 2. Set WINSTON_API_KEY in .env
 * 3. Set AI_DETECTOR_PROVIDER=winston in .env
 *
 * API docs: https://docs.gowinston.ai
 * Pricing: $12/month (AI detection), $19/month (+ plagiarism)
 */

import axios from 'axios';
import { AIDetectionProvider, AIDetectionResult } from '../types';

export class WinstonProvider implements AIDetectionProvider {
  readonly name = 'winston';
  private apiKey: string;

  constructor() {
    this.apiKey = process.env.WINSTON_API_KEY || '';
    if (!this.apiKey) {
      console.warn('[AIDetector] WINSTON_API_KEY not set — provider will fail on calls');
    }
  }

  async analyze(text: string): Promise<AIDetectionResult> {
    const res = await axios.post(
      'https://api.gowinston.ai/v2/ai-content-detection',
      { text, language: 'en' },
      {
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.apiKey}`,
        },
        timeout: 15000,
      }
    );

    const data = res.data;
    // Winston returns a score where higher = more human, so we invert
    const humanScore = data.score ?? 50;
    const aiScore = Math.round(100 - humanScore);

    return {
      score: aiScore,
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
