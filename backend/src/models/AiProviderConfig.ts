// backend/src/models/AiProviderConfig.ts
//
// Admin-managed AI provider configuration. Each row is a single provider
// credential set (one OpenAI account, one Anthropic account, etc) with a
// designated purpose so different sections of the product can route to
// different providers.
//
// API keys are stored encrypted at rest via packages/crypto/encryption. The
// secureRelease() method NEVER returns the ciphertext — the admin UI only
// sees a hasKey boolean. To rotate a key, the admin uploads a new plaintext
// value via the update route, which encrypts before saving.
//
// SERVICE INTEGRATION NOTE: this slice ships the model + admin CRUD only.
// Wiring the existing humanizer/plagiarism services to read from this
// collection (with env-var fallback when no record matches a purpose) is
// deferred to a follow-up. See AiProviderService.resolve() below for the
// helper consumers will use.

import { prop, getModelForClass, modelOptions, DocumentType } from '@typegoose/typegoose';
import { decryptSecret } from '@/packages/crypto/encryption';

export type AiProvider = 'openai' | 'anthropic' | 'gemini' | 'custom';
export type AiPurpose = 'humanize' | 'plagiarism' | 'autocite' | 'general';

@modelOptions({ schemaOptions: { collection: 'ai_provider_configs', timestamps: true } })
export class AiProviderConfig {
  @prop({ required: true })
  public provider!: AiProvider;

  @prop({ required: true })
  public name!: string;

  // Encrypted ciphertext (NOT plaintext). Empty string means "no key set".
  @prop({ default: '' })
  public apiKey!: string;

  @prop()
  public baseUrl?: string;

  @prop({ required: true })
  public defaultModel!: string;

  @prop({ default: false })
  public enabled!: boolean;

  @prop({ default: 0 })
  public order!: number;

  @prop({ default: 'general' })
  public purpose!: AiPurpose;

  // Plaintext key for service-side use. Never expose this from a route handler.
  public getDecryptedKey(this: DocumentType<AiProviderConfig>): string {
    return decryptSecret(this.apiKey || '');
  }

  // Public release for the admin UI. Strips ciphertext; reports hasKey only.
  public secureRelease(this: DocumentType<AiProviderConfig>) {
    const obj: any = (this as any).toObject ? (this as any).toObject() : { ...this };
    obj.id = String(obj._id);
    obj.hasKey = !!obj.apiKey;
    delete obj.apiKey;
    delete obj.__v;
    return obj;
  }
}

export const AiProviderConfigModel = getModelForClass(AiProviderConfig);
