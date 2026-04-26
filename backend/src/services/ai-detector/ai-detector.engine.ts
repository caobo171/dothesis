/**
 * AI Detection Engine
 *
 * Pluggable engine that routes AI detection requests to the configured provider.
 *
 * === Usage ===
 *
 *   import { AIDetectorEngine } from '@/services/ai-detector/ai-detector.engine';
 *
 *   const result = await AIDetectorEngine.detect("some text...");
 *   console.log(result.score);   // 0-100 (higher = more likely AI)
 *   console.log(result.metrics); // per-metric breakdown
 *   console.log(result.provider); // which provider was used
 *
 * === Switching Providers ===
 *
 * Set AI_DETECTOR_PROVIDER in .env:
 *
 *   AI_DETECTOR_PROVIDER=statistical   (default, free, no API key needed)
 *   AI_DETECTOR_PROVIDER=gptzero       (requires GPTZERO_API_KEY)
 *   AI_DETECTOR_PROVIDER=winston       (requires WINSTON_API_KEY)
 *
 * === Adding a New Provider ===
 *
 * 1. Create providers/your-provider.provider.ts implementing AIDetectionProvider
 * 2. Import and register it in the PROVIDERS map below
 * 3. Set AI_DETECTOR_PROVIDER=your-provider in .env
 */

import { AIDetectionProvider, AIDetectionResult } from './types';
import { StatisticalDetectionProvider } from './providers/statistical.provider';
import { GPTZeroProvider } from './providers/gptzero.provider';
import { WinstonProvider } from './providers/winston.provider';

const PROVIDERS: Record<string, () => AIDetectionProvider> = {
  statistical: () => new StatisticalDetectionProvider(),
  gptzero: () => new GPTZeroProvider(),
  winston: () => new WinstonProvider(),
};

export class AIDetectorEngine {
  private static provider: AIDetectionProvider;
  private static fallback: AIDetectionProvider = new StatisticalDetectionProvider();

  /**
   * Initialize the engine. Call once at startup.
   * Reads AI_DETECTOR_PROVIDER from env to select the provider.
   */
  static init() {
    const providerName = (process.env.AI_DETECTOR_PROVIDER || 'statistical').toLowerCase();
    const factory = PROVIDERS[providerName];

    if (!factory) {
      console.warn(`[AIDetector] Unknown provider "${providerName}", falling back to statistical`);
      this.provider = new StatisticalDetectionProvider();
    } else {
      this.provider = factory();
      console.log(`[AIDetector] Using provider: ${this.provider.name}`);
    }
  }

  /**
   * Detect AI-generated text.
   * Falls back to statistical provider if the primary provider fails.
   */
  static async detect(text: string): Promise<AIDetectionResult> {
    if (!this.provider) {
      this.init();
    }

    try {
      return await this.provider.analyze(text);
    } catch (err: any) {
      console.error(`[AIDetector] ${this.provider.name} failed:`, err.message);

      // Fall back to statistical if using an external provider
      if (this.provider.name !== 'statistical') {
        console.log('[AIDetector] Falling back to statistical provider');
        return this.fallback.analyze(text);
      }

      throw err;
    }
  }

  /** Get the name of the active provider */
  static getProviderName(): string {
    return this.provider?.name || 'uninitialized';
  }
}
