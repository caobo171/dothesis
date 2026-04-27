// backend/src/api/routes/order/index.ts
//
// Aggregates all payment-provider routes. Mounted by api/index.ts.

import { Router } from 'express';
import paypal from './paypal';
import polar from './polar';
import paddle from './paddle';

export default (router: Router) => {
  paypal(router);
  polar(router);
  paddle(router);
};
