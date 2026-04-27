import { OpenAIService } from './openai.service';
import { ClaudeService } from './claude.service';
import { GeminiService } from './gemini.service';

// Decision: Added AIChatResult type so chat() returns token usage alongside text.
// The multi-agent humanizer pipeline (Task 3) needs per-step token tracking.
export type AIChatResult = {
  text: string;
  usage: { inputTokens: number; outputTokens: number };
};

type AIProvider = 'openai' | 'claude' | 'gemini';
type AIService = typeof OpenAIService | typeof ClaudeService | typeof GeminiService;

const SERVICES: Record<AIProvider, AIService> = {
  openai: OpenAIService,
  claude: ClaudeService,
  gemini: GeminiService,
};

export class AIServiceManager {
  private static instance: AIServiceManager;
  private primaryProvider: AIProvider;
  private fallbackOrder: AIProvider[];

  constructor() {
    const primary = (process.env.AI_PROVIDER as AIProvider) || 'openai';
    this.primaryProvider = primary;
    this.fallbackOrder = (['openai', 'claude', 'gemini'] as AIProvider[]).filter(p => p !== primary);
  }

  static getInstance(): AIServiceManager {
    if (!this.instance) {
      this.instance = new AIServiceManager();
    }
    return this.instance;
  }

  getService(provider?: AIProvider): AIService {
    return SERVICES[provider || this.primaryProvider];
  }

  async tryWithFallback<T>(
    operation: string,
    fn: (service: AIService) => Promise<T>
  ): Promise<T> {
    try {
      return await fn(this.getService(this.primaryProvider));
    } catch (err: any) {
      console.error(`[AI] ${operation} failed with ${this.primaryProvider}:`, err.message);

      for (const fallback of this.fallbackOrder) {
        try {
          console.log(`[AI] Falling back to ${fallback}`);
          return await fn(this.getService(fallback));
        } catch (fallbackErr: any) {
          console.error(`[AI] ${operation} failed with ${fallback}:`, fallbackErr.message);
        }
      }

      throw new Error(`[AI] ${operation} failed with all providers`);
    }
  }
}
