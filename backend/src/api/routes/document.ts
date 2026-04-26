import { Router } from 'express';
import passport from 'passport';
import multer from 'multer';
import { v4 as uuidv4 } from 'uuid';
import { Code } from '@/Constants';
import { DocumentService } from '@/services/document.service';
import { DocumentModel } from '@/models/Document';

const upload = multer({ limits: { fileSize: 10 * 1024 * 1024 } }); // 10MB

const ALLOWED_MIMES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
  'text/markdown',
];

export default (router: Router) => {
  router.post(
    '/document/upload',
    passport.authenticate('jwt', { session: false }),
    upload.single('file'),
    async (req, res) => {
      try {
        const user = req.user as any;
        const file = req.file;
        if (!file) return res.json({ code: Code.InvalidInput, message: 'No file provided' });
        if (!ALLOWED_MIMES.includes(file.mimetype)) {
          return res.json({ code: Code.InvalidInput, message: 'Unsupported file type' });
        }

        const content = await DocumentService.parseFile(file.buffer, file.mimetype);
        const fileKey = `documents/${user._id}/${uuidv4()}-${file.originalname}`;
        await DocumentService.uploadToS3(file.buffer, fileKey, file.mimetype);

        const doc = await DocumentService.createFromText(
          user._id.toString(),
          file.originalname,
          content,
          'upload',
          undefined,
          fileKey,
          file.mimetype
        );

        return res.json({ code: Code.Success, data: doc });
      } catch (err: any) {
        return res.json({ code: Code.Error, message: err.message });
      }
    }
  );

  router.post(
    '/document/import-url',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      try {
        const user = req.user as any;
        const { url } = req.body;
        if (!url) return res.json({ code: Code.InvalidInput, message: 'URL required' });

        const { title, content } = await DocumentService.scrapeUrl(url);
        const doc = await DocumentService.createFromText(
          user._id.toString(),
          title,
          content,
          'url',
          url
        );

        return res.json({ code: Code.Success, data: doc });
      } catch (err: any) {
        return res.json({ code: Code.Error, message: err.message });
      }
    }
  );

  router.post(
    '/document/list',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const docs = await DocumentModel.find({ owner: user._id.toString() })
        .sort({ createdAt: -1 })
        .select('-content');
      return res.json({ code: Code.Success, data: docs });
    }
  );

  router.post(
    '/document/get',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { id } = req.body;
      const doc = await DocumentModel.findById(id);
      if (!doc) return res.json({ code: Code.NotFound, message: 'Document not found' });
      return res.json({ code: Code.Success, data: doc });
    }
  );
};
