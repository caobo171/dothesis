import { Application } from 'express';
import mongooseLoader from './mongoose';
import expressLoader from './express';

export default async ({ app }: { app: Application }) => {
  await mongooseLoader();
  console.log('Mongoose loaded');

  expressLoader({ app });
  console.log('Express loaded');
};
