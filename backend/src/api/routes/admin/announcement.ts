// backend/src/api/routes/admin/announcement.ts
//
// Admin CRUD for system announcements. All routes super-admin-gated since
// announcements are platform-wide UI.

import { Router } from 'express';
import passport from 'passport';
import { Code } from '@/Constants';
import { SystemAnnouncementModel } from '@/models/SystemAnnouncement';
import { requireAdmin } from '@/api/middlewares/requireAdmin';
import { requireSuperAdmin } from '@/api/middlewares/requireSuperAdmin';

const auth = passport.authenticate('jwt', { session: false });
const sa = [auth, requireAdmin, requireSuperAdmin];

export default () => {
  const router = Router();

  // List (super admin only — admin route, not the public one)
  router.post('/announcements', ...sa, async (req, res) => {
    const docs = await SystemAnnouncementModel.find().sort({ createdAt: -1 });
    return res.json({
      code: Code.Success,
      data: { items: docs.map((d) => d.secureRelease()), total: docs.length, page: 1, limit: docs.length },
    });
  });

  // Get one
  router.post('/announcements/get', ...sa, async (req, res) => {
    const { id } = req.body || {};
    if (!id) return res.json({ code: Code.InvalidInput, message: 'id required' });
    const doc = await SystemAnnouncementModel.findById(id);
    if (!doc) return res.json({ code: Code.NotFound, message: 'not found' });
    return res.json({ code: Code.Success, data: doc.secureRelease() });
  });

  // Create
  router.post('/announcements/create', ...sa, async (req, res) => {
    const { title, content, audience, enabled, startsAt, endsAt } = req.body || {};
    if (!title) return res.json({ code: Code.InvalidInput, message: 'title required' });
    const adminEmail = (req.user as any)?.email || 'unknown';
    const created = await SystemAnnouncementModel.create({
      title: String(title),
      content: String(content || ''),
      audience: ['all', 'free', 'paid'].includes(audience) ? audience : 'all',
      enabled: enabled === true || enabled === 'true',
      startsAt: startsAt ? new Date(String(startsAt)) : undefined,
      endsAt: endsAt ? new Date(String(endsAt)) : undefined,
      createdBy: adminEmail,
    });
    return res.json({ code: Code.Success, data: created.secureRelease() });
  });

  // Update
  router.post('/announcements/update', ...sa, async (req, res) => {
    const { id, title, content, audience, enabled, startsAt, endsAt } = req.body || {};
    if (!id) return res.json({ code: Code.InvalidInput, message: 'id required' });
    const doc = await SystemAnnouncementModel.findById(id);
    if (!doc) return res.json({ code: Code.NotFound, message: 'not found' });
    if (typeof title === 'string') doc.title = title;
    if (typeof content === 'string') doc.content = content;
    if (audience && ['all', 'free', 'paid'].includes(audience)) doc.audience = audience;
    if (typeof enabled === 'boolean' || enabled === 'true' || enabled === 'false') {
      doc.enabled = enabled === true || enabled === 'true';
    }
    // Allow clearing startsAt/endsAt by passing null/empty string explicitly.
    if (startsAt === null || startsAt === '') doc.startsAt = undefined;
    else if (startsAt) doc.startsAt = new Date(String(startsAt));
    if (endsAt === null || endsAt === '') doc.endsAt = undefined;
    else if (endsAt) doc.endsAt = new Date(String(endsAt));
    await doc.save();
    return res.json({ code: Code.Success, data: doc.secureRelease() });
  });

  // Delete
  router.post('/announcements/delete', ...sa, async (req, res) => {
    const { id } = req.body || {};
    if (!id) return res.json({ code: Code.InvalidInput, message: 'id required' });
    const doc = await SystemAnnouncementModel.findByIdAndDelete(id);
    if (!doc) return res.json({ code: Code.NotFound, message: 'not found' });
    return res.json({ code: Code.Success, data: { id } });
  });

  // Toggle enabled — convenience endpoint for the inline switch on the list.
  router.post('/announcements/toggle', ...sa, async (req, res) => {
    const { id, enabled } = req.body || {};
    if (!id) return res.json({ code: Code.InvalidInput, message: 'id required' });
    const doc = await SystemAnnouncementModel.findById(id);
    if (!doc) return res.json({ code: Code.NotFound, message: 'not found' });
    doc.enabled = enabled === true || enabled === 'true';
    await doc.save();
    return res.json({ code: Code.Success, data: doc.secureRelease() });
  });

  return router;
};
