import 'dotenv/config';
import express from 'express';
import http from 'http';
import { Server as SocketServer } from 'socket.io';
import loaders from '@/loaders';
import { initAutoCiteQueue } from '@/queues/autocite.queue';
import { initPlagiarismQueue } from '@/queues/plagiarism.queue';
import { Mailer } from '@/packages/mail/mail';

const app = express();
const server = http.createServer(app);

const io = new SocketServer(server, {
  cors: { origin: '*', methods: ['GET', 'POST'] },
});

// Make io accessible to routes
app.set('io', io);

io.on('connection', (socket) => {
  console.log('Socket connected:', socket.id);

  socket.on('join', (room: string) => {
    socket.join(room);
  });

  socket.on('disconnect', () => {
    console.log('Socket disconnected:', socket.id);
  });
});

const start = async () => {
  await loaders({ app });

  await Mailer.init();
  console.log('Mailer initialized');

  initAutoCiteQueue(io);
  console.log('Auto-cite queue initialized');

  initPlagiarismQueue(io);
  console.log('Plagiarism queue initialized');

  const port = process.env.PORT || 8001;
  server.listen(port, () => {
    console.log(`DoThesis backend running on port ${port}`);
  });
};

start();
