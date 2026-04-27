// backend/src/services/aiProvider.service.ts
//
// Helper for product code (humanize, plagiarism, autocite services) to fetch
// the active provider config for a given purpose. Handles the env-var fallback
// so existing services continue to work even before any AiProviderConfig row
// exists in the database.
//
// THIS SLICE: the helper is implemented but no existing service is rewired
// to use it. Wiring is intentionally deferred to a separate change so the
// admin portal port doesn't risk regressions in production model usage.

import { AiProviderConfigModel, AiPurpose } from '@/models/AiProviderConfig';

type ResolvedProvider = {
  source: 'db' | 'env';
  provider: string;
  apiKey: string;
  baseUrl?: string;
  defaultModel: string;
};

const ENV_FALLBACKS: Record<AiPurpose, () => ResolvedProvider | null> = {
  humanize: () => {
    const apiKey = process.env.OPENAI_API_KEY || '';
    if (!apiKey) return null;
    return { source: 'env', provider: 'openai', apiKey, defaultModel: process.env.OPENAI_MODEL || 'gpt-4o' };
  },
  plagiarism: () => {
    const apiKey = process.env.OPENAI_API_KEY || '';
    if (!apiKey) return null;
    return { source: 'env', provider: 'openai', apiKey, defaultModel: process.env.OPENAI_MODEL || 'gpt-4o' };
  },
  autocite: () => {
    const apiKey = process.env.OPENAI_API_KEY || '';
    if (!apiKey) return null;
    return { source: 'env', provider: 'openai', apiKey, defaultModel: process.env.OPENAI_MODEL || 'gpt-4o' };
  },
  general: () => {
    const apiKey = process.env.OPENAI_API_KEY || '';
    if (!apiKey) return null;
    return { source: 'env', provider: 'openai', apiKey, defaultModel: process.env.OPENAI_MODEL || 'gpt-4o' };
  },
};

export class AiProviderService {
  // Returns the lowest-order enabled provider for the given purpose, or
  // an env-var fallback if no record exists.
  static async resolve(purpose: AiPurpose): Promise<ResolvedProvider | null> {
    const doc = await AiProviderConfigModel.findOne({ purpose, enabled: true }).sort({ order: 1 });
    if (doc) {
      const apiKey = doc.getDecryptedKey();
      if (apiKey) {
        return {
          source: 'db',
          provider: doc.provider,
          apiKey,
          baseUrl: doc.baseUrl,
          defaultModel: doc.defaultModel,
        };
      }
    }
    return ENV_FALLBACKS[purpose]?.() || null;
  }
}
