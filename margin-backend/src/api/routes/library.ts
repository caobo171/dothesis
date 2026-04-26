import { Router } from 'express';
import passport from 'passport';
import { Code } from '@/Constants';
import { CitationModel } from '@/models/Citation';
import { CitationFolderModel } from '@/models/CitationFolder';

export default (router: Router) => {
  // ---- FOLDERS ----

  router.post(
    '/library/folders/list',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const folders = await CitationFolderModel.find({ owner: user._id.toString() }).sort({ createdAt: -1 });

      // Add citation counts
      const foldersWithCounts = await Promise.all(
        folders.map(async (f: any) => {
          const count = await CitationModel.countDocuments({ folderId: f._id.toString() });
          return { ...f.toObject(), id: f._id, citationCount: count };
        })
      );

      return res.json({ code: Code.Success, data: foldersWithCounts });
    }
  );

  router.post(
    '/library/folders/create',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const { name, color = '#0022FF' } = req.body;
      if (!name) return res.json({ code: Code.InvalidInput, message: 'Name required' });

      const folder = await CitationFolderModel.create({
        owner: user._id.toString(),
        name,
        color,
      });

      return res.json({ code: Code.Success, data: folder });
    }
  );

  router.post(
    '/library/folders/update',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { id, name, color } = req.body;
      const update: any = {};
      if (name) update.name = name;
      if (color) update.color = color;

      const folder = await CitationFolderModel.findByIdAndUpdate(id, update, { new: true });
      return res.json({ code: Code.Success, data: folder });
    }
  );

  router.post(
    '/library/folders/delete',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { id } = req.body;
      await CitationFolderModel.findByIdAndDelete(id);
      // Move citations to unfiled
      await CitationModel.updateMany({ folderId: id }, { folderId: null });
      return res.json({ code: Code.Success });
    }
  );

  // ---- CITATIONS ----

  router.post(
    '/library/citations/list',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const { folderId } = req.body;
      const filter: any = { owner: user._id.toString() };
      if (folderId) filter.folderId = folderId;

      const citations = await CitationModel.find(filter).sort({ createdAt: -1 });
      return res.json({ code: Code.Success, data: citations });
    }
  );

  router.post(
    '/library/citations/save',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const { folderId, style, formattedText, author, year, title, journal, doi, url, sourceApi } =
        req.body;

      const citation = await CitationModel.create({
        owner: user._id.toString(),
        folderId: folderId || null,
        style,
        formattedText,
        author,
        year,
        title,
        journal,
        doi,
        url,
        sourceApi,
      });

      return res.json({ code: Code.Success, data: citation });
    }
  );

  router.post(
    '/library/citations/update',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { id, ...updates } = req.body;
      const citation = await CitationModel.findByIdAndUpdate(id, updates, { new: true });
      return res.json({ code: Code.Success, data: citation });
    }
  );

  router.post(
    '/library/citations/delete',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { id } = req.body;
      await CitationModel.findByIdAndDelete(id);
      return res.json({ code: Code.Success });
    }
  );

  // Export folder bibliography
  router.post(
    '/library/export',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const { folderId } = req.body;
      const filter: any = { owner: user._id.toString() };
      if (folderId) filter.folderId = folderId;

      const citations = await CitationModel.find(filter).sort({ author: 1 });
      const text = citations.map((c: any) => c.formattedText).join('\n\n');

      res.setHeader('Content-Type', 'text/plain');
      res.setHeader('Content-Disposition', 'attachment; filename=bibliography.txt');
      return res.send(text);
    }
  );
};
