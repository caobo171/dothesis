/**
 * Copyscape AI Detection Provider
 *
 * Calls Copyscape's o=aicheck endpoint to determine AI probability for a given text.
 * Returns aiscore (0.01–0.99) converted to our 0-100 integer scale.
 *
 * Reuses COPYSCAPE_USERNAME and COPYSCAPE_API_KEY env vars already present for the
 * plagiarism feature — no new credentials required.
 *
 * Pricing: ~$0.03 per 200 words checked.
 * Docs: https://www.copyscape.com/api/
 *
 * To enable: set AI_DETECTOR_PROVIDER=copyscape in .env, then register this class
 * in ai-detector.engine.ts PROVIDERS map.
 */

import axios from 'axios';
import { AIDetectionProvider, AIDetectionResult } from '../types';

const COPYSCAPE_API_URL = 'https://www.copyscape.com/api/';

export class CopyscapeProvider implements AIDetectionProvider {
  readonly name = 'copyscape';

  private username: string;
  private apiKey: string;

  constructor() {
    // Reuse existing Copyscape credentials from the plagiarism feature
    this.username = process.env.COPYSCAPE_USERNAME || '';
    this.apiKey = process.env.COPYSCAPE_API_KEY || '';

    if (!this.username || !this.apiKey) {
      console.warn(
        '[AIDetector] COPYSCAPE_USERNAME or COPYSCAPE_API_KEY not set — CopyscapeProvider will fail on calls'
      );
    }
  }

  async analyze(text: string): Promise<AIDetectionResult> {
    // POST with query params (Copyscape API does not use a JSON body)
    const res = await axios.post(COPYSCAPE_API_URL, null, {
      params: {
        u: this.username,
        k: this.apiKey,
        o: 'aicheck',   // AI detection operation — distinct from plagiarism check
        e: 'UTF-8',
        t: text,
        f: 'json',
        l: '0.50',      // Spend limit per call as a safety cap (~$0.50 max)
      },
      timeout: 15000,
    });

    const data = res.data;

    // Copyscape signals API-level errors inside the response body
    if (data.error) {
      throw new Error(`Copyscape API error: ${data.error}`);
    }

    // aiscore: 0.01 (very likely human) → 0.99 (very likely AI)
    // Convert to our 0-100 integer scale used throughout the humanizer pipeline
    const score = Math.round((data.aiscore ?? 0) * 100);

    return {
      score,
      metrics: {
        // Copyscape provides a single aggregate score; individual metrics not available
        sentenceLengthVariance: 0,
        vocabularyDiversity: 0,
        burstiness: 0,
        transitionDensity: 0,
        sentenceStarterDiversity: 0,
        humanMarkers: 0,
        punctuationDiversity: 0,
      },
      language: 'en', // Copyscape does not return a language field; default to English
      provider: this.name,
    };
  }
}
