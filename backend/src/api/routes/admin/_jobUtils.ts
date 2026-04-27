// backend/src/api/routes/admin/_jobUtils.ts
//
// Shared helpers for admin job-section routes (humanize, plagiarism, autocite,
// documents). Centralizes the list/get/delete pattern so each section file is
// just a configuration of model + filters, not a copy of the same Express logic.
//
// The shape of the public response is the same as the rest of the admin API:
//   list    -> { code, data: { items, total, page, limit } }
//   detail  -> { code, data: <record-with-owner-enriched> }

import { Router, Request, Response } from 'express';
import passport from 'passport';
import { Code } from '@/Constants';
import { UserModel } from '@/models/User';
import { requireAdmin } from '@/api/middlewares/requireAdmin';
import { requireSuperAdmin } from '@/api/middlewares/requireSuperAdmin';

const auth = passport.authenticate('jwt', { session: false });

type JobModel = {
  countDocuments: (filter: any) => Promise<number>;
  find: (filter: any) => any;
  findById: (id: string) => any;
  findByIdAndDelete?: (id: string) => any;
};

type SectionConfig = {
  // URL path under /api/admin (e.g. '/humanize').
  path: string;
  model: JobModel;
  // Optional fields that participate in q-search (case-insensitive substring).
  searchFields?: string[];
  // Allowed status values for the dropdown (purely informational; not enforced
  // server-side because the frontend builds the dropdown from this list).
  statuses?: string[];
  // Whether the model exposes a status field that can be set to 'cancelled'.
  // Cancel route only registered when this is true.
  cancellable?: boolean;
};

// Convert a Mongoose doc to a plain JSON-safe object for the API response.
// Handles the lack of secureRelease() on most job models.
const toPlain = (doc: any) => {
  if (!doc) return null;
  const obj = typeof doc.toObject === 'function' ? doc.toObject() : { ...doc };
  obj.id = String(obj._id);
  delete obj.__v;
  return obj;
};

const escapeRegex = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

// Resolve a batch of owner ids → { id: { email, username } } so list rows
// can show owner labels without N+1 queries from the frontend.
async function resolveOwners(ids: string[]) {
  const unique = Array.from(new Set(ids.filter(Boolean)));
  if (!unique.length) return {};
  const owners = await UserModel.find({ _id: { $in: unique } });
  const map: Record<string, { email: string; username: string }> = {};
  for (const u of owners) {
    map[u._id.toString()] = { email: u.email, username: u.username };
  }
  return map;
}

export function registerJobSection(router: Router, config: SectionConfig) {
  const { path, model, searchFields = [], cancellable } = config;

  // ── List ──────────────────────────────────────────────────────────────
  router.post(path, auth, requireAdmin, async (req: Request, res: Response) => {
    const { q, status, owner, dateFrom, dateTo, page = 1, limit = 25 } = req.body || {};
    const pageNum = Math.max(1, parseInt(String(page), 10) || 1);
    const limitNum = Math.min(100, Math.max(1, parseInt(String(limit), 10) || 25));

    const filter: any = {};
    if (status) filter.status = String(status);
    if (owner) filter.owner = String(owner);
    if (dateFrom || dateTo) {
      filter.createdAt = {};
      if (dateFrom) filter.createdAt.$gte = new Date(String(dateFrom));
      if (dateTo) filter.createdAt.$lte = new Date(String(dateTo));
    }
    if (q && typeof q === 'string' && q.trim() && searchFields.length) {
      const rx = new RegExp(escapeRegex(q.trim()), 'i');
      filter.$or = searchFields.map((f) => ({ [f]: rx }));
    }

    const [total, docs] = await Promise.all([
      model.countDocuments(filter),
      model.find(filter).sort({ createdAt: -1 }).skip((pageNum - 1) * limitNum).limit(limitNum),
    ]);

    const ownerMap = await resolveOwners(docs.map((d: any) => d.owner));
    const items = docs.map((d: any) => ({
      ...toPlain(d),
      ownerInfo: ownerMap[d.owner] || null,
    }));

    return res.json({
      code: Code.Success,
      data: { items, total, page: pageNum, limit: limitNum },
    });
  });

  // ── Detail ────────────────────────────────────────────────────────────
  router.post(`${path}/get`, auth, requireAdmin, async (req: Request, res: Response) => {
    const { id } = req.body || {};
    if (!id) return res.json({ code: Code.InvalidInput, message: 'id required' });
    const doc = await model.findById(id);
    if (!doc) return res.json({ code: Code.NotFound, message: 'not found' });
    const ownerMap = await resolveOwners([doc.owner]);
    return res.json({
      code: Code.Success,
      data: { ...toPlain(doc), ownerInfo: ownerMap[doc.owner] || null },
    });
  });

  // ── Cancel (sets status='cancelled') ──────────────────────────────────
  if (cancellable) {
    router.post(`${path}/cancel`, auth, requireAdmin, async (req: Request, res: Response) => {
      const { id } = req.body || {};
      if (!id) return res.json({ code: Code.InvalidInput, message: 'id required' });
      const doc = await model.findById(id);
      if (!doc) return res.json({ code: Code.NotFound, message: 'not found' });
      // Only meaningful for jobs in flight. Already-terminal jobs no-op safely.
      doc.status = 'cancelled';
      await doc.save();
      return res.json({ code: Code.Success, data: toPlain(doc) });
    });
  }

  // ── Delete [SA] ───────────────────────────────────────────────────────
  router.post(`${path}/delete`, auth, requireAdmin, requireSuperAdmin, async (req: Request, res: Response) => {
    const { id } = req.body || {};
    if (!id) return res.json({ code: Code.InvalidInput, message: 'id required' });
    if (typeof model.findByIdAndDelete !== 'function') {
      return res.json({ code: Code.Error, message: 'delete not supported for this section' });
    }
    const doc = await model.findByIdAndDelete(id);
    if (!doc) return res.json({ code: Code.NotFound, message: 'not found' });
    return res.json({ code: Code.Success, data: { id } });
  });
}
