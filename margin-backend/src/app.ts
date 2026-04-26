import 'dotenv/config';
import express from 'express';
import http from 'http';
import { Server as SocketServer } from 'socket.io';
import loaders from '@/loaders';
import { initAutoCiteQueue } from '@/queues/autocite.queue';

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

  initAutoCiteQueue(io);
  console.log('Auto-cite queue initialized');

  const port = process.env.PORT || 8001;
  server.listen(port, () => {
    console.log(`Margin backend running on port ${port}`);
  });
};

start();
