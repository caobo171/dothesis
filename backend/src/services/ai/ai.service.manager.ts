import { OpenAIService } from './openai.service';
import { ClaudeService } from './claude.service';

type AIProvider = 'openai' | 'claude';

export class AIServiceManager {
  private static instance: AIServiceManager;
  private primaryProvider: AIProvider = 'openai';
  private secondaryProvider: AIProvider = 'claude';

  static getInstance(): AIServiceManager {
    if (!this.instance) {
      this.instance = new AIServiceManager();
    }
    return this.instance;
  }

  getService(provider?: AIProvider) {
    const p = provider || this.primaryProvider;
    return p === 'openai' ? OpenAIService : ClaudeService;
  }

  async tryWithFallback<T>(
    operation: string,
    fn: (service: typeof OpenAIService | typeof ClaudeService) => Promise<T>
  ): Promise<T> {
    try {
      const primaryService = this.getService(this.primaryProvider);
      return await fn(primaryService);
    } catch (err: any) {
      console.error(`[AI] ${operation} failed with ${this.primaryProvider}:`, err.message);
      console.log(`[AI] Falling back to ${this.secondaryProvider}`);
      const fallbackService = this.getService(this.secondaryProvider);
      return await fn(fallbackService);
    }
  }
}
