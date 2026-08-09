export type CreditPackage = {
  id: string;
  name: string;
  price_cents: number;
  old_price_cents: number;
  /** Same price in dong, converted server-side at USD_TO_VND so it always
   *  matches the amount baked into the SePay QR. Shown to UTC+7 users. */
  price_vnd: number;
  old_price_vnd: number;
  credits: number;
};
