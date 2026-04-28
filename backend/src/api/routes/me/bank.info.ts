// backend/src/api/routes/me/bank.info.ts
//
// Returns the bank account + memo + Sepay QR URL for a credit purchase.
// Each pricing package gets its own QR (different transfer amount) so the
// Sepay webhook can match an incoming transfer to a specific pack.
//
// idcredit is backfilled lazily here — the field was added after the model
// shipped, so existing users won't have one until they hit this route.

import { Router } from 'express';
import passport from 'passport';
import { Code, BANK_INFO, PRICING_PACKAGES_VND } from '@/Constants';
import { UserModel } from '@/models/User';
import type { DocumentType } from '@typegoose/typegoose';
import type { User } from '@/models/User';

// Generate a stable-but-unique numeric idcredit. Range chosen to fit comfortably
// in a bank memo (10 digits), unique under realistic load.
async function ensureIdCredit(user: DocumentType<User>): Promise<number> {
  if (typeof user.idcredit === 'number' && user.idcredit > 0) return user.idcredit;
  // Try a few times in case of unique-index collisions on the rare
  // simultaneous backfill. 6-digit range is plenty for a small product
  // and stays human-friendly in QR memos.
  for (let i = 0; i < 5; i++) {
    const candidate = Math.floor(100_000 + Math.random() * 9_900_000);
    const taken = await UserModel.exists({ idcredit: candidate });
    if (!taken) {
      user.idcredit = candidate;
      await user.save();
      return candidate;
    }
  }
  throw new Error('Could not allocate idcredit');
}

export default (router: Router) => {
  router.post(
    '/me/bank.info',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const me = req.user as DocumentType<User> | undefined;
      if (!me) return res.json({ code: Code.InvalidAuth, message: 'unauthenticated' });

      try {
        const idcredit = await ensureIdCredit(me);
        const bank = BANK_INFO.providers[BANK_INFO.current];
        const memoBase = `${BANK_INFO.formatMsg}${idcredit}`;

        // Per-package QRs. Each one encodes a fixed transfer amount + memo so
        // when Sepay's webhook fires we can match by exact amount + idcredit.
        const packages = PRICING_PACKAGES_VND.map((pkg) => {
          // Sepay QR URL format. Bank arg differs per provider — keep aligned
          // with what Sepay accepts in their qr.sepay.vn proxy.
          const sepayBank = BANK_INFO.current === 'OCB' ? 'OCB' : 'VietinBank';
          const memo = memoBase;
          const qrUrl =
            `https://qr.sepay.vn/img?acc=${encodeURIComponent(bank.number)}` +
            `&bank=${sepayBank}` +
            `&amount=${pkg.price_vnd}` +
            `&des=${encodeURIComponent(memo)}`;
          return {
            id: pkg.id,
            credit: pkg.credit,
            price_vnd: pkg.price_vnd,
            memo,
            qr_url: qrUrl,
          };
        });

        return res.json({
          code: Code.Success,
          data: {
            bank: {
              name: bank.name,
              number: bank.number,
              provider: BANK_INFO.current,
            },
            idcredit,
            memo_prefix: BANK_INFO.formatMsg,
            packages,
          },
        });
      } catch (err: any) {
        console.error('bank.info error:', err?.message || err);
        return res.json({ code: Code.Error, message: 'Failed to build bank info' });
      }
    }
  );
};
