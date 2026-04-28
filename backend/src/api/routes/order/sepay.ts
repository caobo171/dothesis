// backend/src/api/routes/order/sepay.ts
//
// Sepay webhook receiver. Sepay calls this URL whenever a transfer hits the
// configured bank account. Body shape (from Sepay docs):
//   {
//     id, gateway, transactionDate, accountNumber,
//     code,             // memo, e.g. "DTH123456" for our format
//     content,
//     transferType,     // "in" / "out"
//     transferAmount,   // VND
//     accumulated, subAccount, referenceCode, description
//   }
//
// Routing logic:
//   1. Filter to transferType === 'in'.
//   2. Extract idcredit by stripping BANK_INFO.formatMsg from `code`.
//   3. Match the package by exact transferAmount.
//   4. Grant the package's credit count via CreditService.
//
// The webhook is unauthenticated by design (Sepay doesn't sign the body).
// Defense: we trust amount-matched packages only, and we use Sepay's `id` as
// the orderId on the Credit row so retries dedupe.

import { Router } from 'express';
import { Code, BANK_INFO, PRICING_PACKAGES_VND } from '@/Constants';
import { UserModel } from '@/models/User';
import { CreditService } from '@/services/credit.service';

export default (router: Router) => {
  router.post('/order/sepay/webhook', async (req, res) => {
    const body = req.body || {};
    const code: string = String(body.code || '');
    const transferType: string = String(body.transferType || '');
    const amount = Number(body.transferAmount || 0);
    const txnId = String(body.id || '');

    if (transferType !== 'in') {
      return res.json({ code: Code.Success, data: { ignored: 'not inbound' } });
    }
    if (!code || !amount || !txnId) {
      return res.json({ code: Code.InvalidInput, message: 'missing fields' });
    }

    // Extract idcredit. memo is "<formatMsg><idcredit>"; tolerate extra prefix
    // characters (some banks prepend their own SVQR/TKP markers) by searching
    // for the formatMsg substring rather than requiring it at offset 0.
    const idx = code.indexOf(BANK_INFO.formatMsg);
    if (idx < 0) {
      return res.json({ code: Code.InvalidInput, message: 'memo prefix not found' });
    }
    const numericPart = code.slice(idx + BANK_INFO.formatMsg.length).match(/^\d+/)?.[0];
    const idcredit = numericPart ? Number(numericPart) : NaN;
    if (!idcredit) {
      return res.json({ code: Code.InvalidInput, message: 'idcredit not parsable' });
    }

    // Match the package by exact VND amount. We deliberately do not honour
    // arbitrary amounts — that opens the door to underpayment scams.
    const pkg = PRICING_PACKAGES_VND.find((p) => p.price_vnd === amount);
    if (!pkg) {
      return res.json({ code: Code.InvalidInput, message: `no package for amount ${amount}` });
    }

    try {
      const user = await UserModel.findOne({ idcredit });
      if (!user) {
        return res.json({ code: Code.NotFound, message: 'user not found for idcredit' });
      }
      await CreditService.addCredits(
        user._id.toString(),
        pkg.credit,
        `Sepay: ${pkg.id}`,
        'sepay',
        txnId
      );
      return res.json({ code: Code.Success, data: { granted: pkg.credit } });
    } catch (err: any) {
      console.error('Sepay webhook grant error:', err?.message || err);
      return res.json({ code: Code.Error, message: 'Grant failed' });
    }
  });
};
