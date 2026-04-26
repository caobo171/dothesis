import { Request, Response, NextFunction } from 'express';

export const wrapAsync = (fn: Function) => {
  return (req: Request, res: Response, next: NextFunction) => {
    fn(req, res, next).catch(next);
  };
};

export const safeParse = (str: string): any => {
  try {
    return JSON.parse(str);
  } catch {
    return null;
  }
};

export const clearDotsFromGmail = (email: string): string => {
  const [local, domain] = email.split('@');
  if (domain === 'gmail.com') {
    return local.replace(/\./g, '') + '@' + domain;
  }
  return email;
};
