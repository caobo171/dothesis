// backend/src/api/routes/announcement.public.ts
//
// Public endpoint that returns currently-active announcements. Used by the
// workspace layout to render banners. JWT-authenticated (so we can filter by
// the user's plan if requested), but NOT admin-gated.
//
// "Active" means: enabled === true AND
//   (startsAt is unset OR startsAt <= now) AND (endsAt is unset OR endsAt >= now).

import { Router } from 'express';
import passport from 'passport';
import { Code } from '@/Constants';
import { SystemAnnouncementModel } from '@/models/SystemAnnouncement';

export default (router: Router) => {
  router.post('/announcements/active', passport.authenticate('jwt', { session: false }), async (req, res) => {
    const me = req.user as any;
    const now = new Date();

    const docs = await SystemAnnouncementModel.find({
      enabled: true,
      $and: [
        { $or: [{ startsAt: { $exists: false } }, { startsAt: null }, { startsAt: { $lte: now } }] },
        { $or: [{ endsAt: { $exists: false } }, { endsAt: null }, { endsAt: { $gte: now } }] },
      ],
    }).sort({ createdAt: -1 });

    // Audience filter — paid means anyone NOT on free.
    const userPlan = me?.plan || 'free';
    const filtered = docs.filter((d) => {
      if (d.audience === 'all') return true;
      if (d.audience === 'free') return userPlan === 'free';
      if (d.audience === 'paid') return userPlan !== 'free';
      return true;
    });

    return res.json({ code: Code.Success, data: filtered.map((d) => d.secureRelease()) });
  });
};
