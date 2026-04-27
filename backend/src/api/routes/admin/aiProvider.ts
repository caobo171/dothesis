// backend/src/api/routes/admin/aiProvider.ts
//
// Super-admin-only CRUD for AI provider configurations. Reorder via the
// "reorder" route which accepts a list of ids in the desired sequence.
//
// All read endpoints strip the encrypted apiKey from the response and report
// only `hasKey: boolean`. The plaintext key is never returned over the wire.

import { Router } from 'express';
import passport from 'passport';
import { Code } from '@/Constants';
import { AiProviderConfigModel } from '@/models/AiProviderConfig';
import { encryptSecret } from '@/packages/crypto/encryption';
import { requireAdmin } from '@/api/middlewares/requireAdmin';
import { requireSuperAdmin } from '@/api/middlewares/requireSuperAdmin';

const auth = passport.authenticate('jwt', { session: false });
const sa = [auth, requireAdmin, requireSuperAdmin];

const PROVIDERS = ['openai', 'anthropic', 'gemini', 'custom'] as const;
const PURPOSES = ['humanize', 'plagiarism', 'autocite', 'general'] as const;

export default () => {
  const router = Router();

  router.post('/ai-providers', ...sa, async (req, res) => {
    const docs = await AiProviderConfigModel.find().sort({ order: 1, createdAt: 1 });
    return res.json({
      code: Code.Success,
      data: { items: docs.map((d) => d.secureRelease()), total: docs.length, page: 1, limit: docs.length },
    });
  });

  router.post('/ai-providers/get', ...sa, async (req, res) => {
    const { id } = req.body || {};
    if (!id) return res.json({ code: Code.InvalidInput, message: 'id required' });
    const doc = await AiProviderConfigModel.findById(id);
    if (!doc) return res.json({ code: Code.NotFound, message: 'not found' });
    return res.json({ code: Code.Success, data: doc.secureRelease() });
  });

  router.post('/ai-providers/create', ...sa, async (req, res) => {
    const { provider, name, apiKey, baseUrl, defaultModel, enabled, order, purpose } = req.body || {};
    if (!provider || !PROVIDERS.includes(provider)) {
      return res.json({ code: Code.InvalidInput, message: 'invalid provider' });
    }
    if (!name) return res.json({ code: Code.InvalidInput, message: 'name required' });
    if (!defaultModel) return res.json({ code: Code.InvalidInput, message: 'defaultModel required' });
    if (purpose && !PURPOSES.includes(purpose)) {
      return res.json({ code: Code.InvalidInput, message: 'invalid purpose' });
    }
    const created = await AiProviderConfigModel.create({
      provider,
      name: String(name),
      apiKey: apiKey ? encryptSecret(String(apiKey)) : '',
      baseUrl: baseUrl ? String(baseUrl) : undefined,
      defaultModel: String(defaultModel),
      enabled: enabled === true || enabled === 'true',
      order: typeof order === 'number' ? order : Number(order) || 0,
      purpose: purpose || 'general',
    });
    return res.json({ code: Code.Success, data: created.secureRelease() });
  });

  // Update — apiKey is only updated if a non-empty value is passed. Empty
  // strings/undefined leave the existing ciphertext untouched so the admin
  // can edit other fields without re-pasting the key.
  router.post('/ai-providers/update', ...sa, async (req, res) => {
    const { id, provider, name, apiKey, baseUrl, defaultModel, enabled, order, purpose } = req.body || {};
    if (!id) return res.json({ code: Code.InvalidInput, message: 'id required' });
    const doc = await AiProviderConfigModel.findById(id);
    if (!doc) return res.json({ code: Code.NotFound, message: 'not found' });

    if (provider && PROVIDERS.includes(provider)) doc.provider = provider;
    if (typeof name === 'string') doc.name = name;
    if (typeof apiKey === 'string' && apiKey.length > 0) doc.apiKey = encryptSecret(apiKey);
    if (typeof baseUrl === 'string') doc.baseUrl = baseUrl || undefined;
    if (typeof defaultModel === 'string' && defaultModel) doc.defaultModel = defaultModel;
    if (typeof enabled === 'boolean' || enabled === 'true' || enabled === 'false') {
      doc.enabled = enabled === true || enabled === 'true';
    }
    if (typeof order === 'number' || (typeof order === 'string' && order !== '')) {
      doc.order = Number(order);
    }
    if (purpose && PURPOSES.includes(purpose)) doc.purpose = purpose;

    await doc.save();
    return res.json({ code: Code.Success, data: doc.secureRelease() });
  });

  router.post('/ai-providers/delete', ...sa, async (req, res) => {
    const { id } = req.body || {};
    if (!id) return res.json({ code: Code.InvalidInput, message: 'id required' });
    const doc = await AiProviderConfigModel.findByIdAndDelete(id);
    if (!doc) return res.json({ code: Code.NotFound, message: 'not found' });
    return res.json({ code: Code.Success, data: { id } });
  });

  router.post('/ai-providers/toggle', ...sa, async (req, res) => {
    const { id, enabled } = req.body || {};
    if (!id) return res.json({ code: Code.InvalidInput, message: 'id required' });
    const doc = await AiProviderConfigModel.findById(id);
    if (!doc) return res.json({ code: Code.NotFound, message: 'not found' });
    doc.enabled = enabled === true || enabled === 'true';
    await doc.save();
    return res.json({ code: Code.Success, data: doc.secureRelease() });
  });

  // Body: { ids: string[] } — resets `order` to 0..N-1 in the given order.
  router.post('/ai-providers/reorder', ...sa, async (req, res) => {
    const { ids } = req.body || {};
    if (!Array.isArray(ids)) return res.json({ code: Code.InvalidInput, message: 'ids array required' });
    await Promise.all(
      ids.map((id, idx) => AiProviderConfigModel.findByIdAndUpdate(id, { $set: { order: idx } }))
    );
    return res.json({ code: Code.Success, data: { ok: true } });
  });

  return router;
};
