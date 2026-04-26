import express, { Application } from 'express';
import cors from 'cors';
import bodyParser from 'body-parser';
import multer from 'multer';
import session from 'express-session';
import routes from '@/api';

export default ({ app }: { app: Application }) => {
  app.use(cors({ origin: '*', methods: 'GET,HEAD,PUT,PATCH,POST,DELETE' }));

  app.use(
    bodyParser.json({
      limit: '50mb',
      verify: (req: any, res, buf) => {
        req.rawBody = buf;
      },
    })
  );
  app.use(bodyParser.urlencoded({ extended: true, limit: '50mb' }));
  app.use(multer().none());

  app.use(
    session({
      secret: process.env.JWT_SECRET || 'margin_secret',
      resave: false,
      saveUninitialized: false,
    })
  );

  app.get('/status', (req, res) => res.send('OK'));

  const apiRoutes = routes();
  app.use('/api', apiRoutes);
};
