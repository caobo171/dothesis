import { Application } from 'express';
import mongooseLoader from './mongoose';
import expressLoader from './express';
import passportLoader from './passport';

export default async ({ app }: { app: Application }) => {
  await mongooseLoader();
  console.log('Mongoose loaded');

  expressLoader({ app });
  console.log('Express loaded');

  passportLoader({ app });
  console.log('Passport loaded');
};
