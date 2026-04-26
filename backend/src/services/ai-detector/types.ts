/**
 * AI Detection Engine — Type Definitions
 *
 * Provider-agnostic interface for AI text detection.
 * Implementations can use statistical analysis, external APIs (GPTZero, Winston AI),
 * or any combination thereof.
 */

export interface AIDetectionMetrics {
  sentenceLengthVariance: number;  // 0-100: how uniform sentence lengths are
  vocabularyDiversity: number;     // 0-100: how repetitive the vocabulary is
  burstiness: number;              // 0-100: how smooth vs jumpy complexity is
  transitionDensity: number;       // 0-100: how many formulaic connectors
  sentenceStarterDiversity: number; // 0-100: how repetitive sentence openings are
  humanMarkers: number;            // 0-100: absence of human filler/hedging words
  punctuationDiversity: number;    // 0-100: how uniform punctuation usage is
}

export interface AIDetectionResult {
  /** Overall AI probability score: 0 = definitely human, 100 = definitely AI */
  score: number;
  /** Per-metric breakdown (all 0-100, higher = more AI-like) */
  metrics: AIDetectionMetrics;
  /** Detected language */
  language: 'en' | 'vi';
  /** Which provider produced this result */
  provider: string;
}

/**
 * Interface that all AI detection providers must implement.
 * To add a new provider (e.g., GPTZero, Winston AI):
 * 1. Create a new file implementing AIDetectionProvider
 * 2. Register it in ai-detector.engine.ts
 * 3. Set AI_DETECTOR_PROVIDER env var to switch
 */
export interface AIDetectionProvider {
  readonly name: string;

  /**
   * Analyze text and return detection result.
   * Must be deterministic for the same input (statistical providers)
   * or best-effort consistent (API-based providers).
   */
  analyze(text: string): Promise<AIDetectionResult>;
}
