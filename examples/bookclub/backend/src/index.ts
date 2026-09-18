import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import { config } from './config.js';
import { pool } from './db.js';
import { asyncHandler, errorHandler } from './http.js';
import authRoutes from './routes/auth.js';
import bookRoutes from './routes/books.js';
import clubRoutes from './routes/clubs.js';
import voteRoutes from './routes/votes.js';
import threadRoutes from './routes/threads.js';

const app = express();

app.use(helmet());
app.use(cors({ origin: config.corsOrigin.split(',').map((origin) => origin.trim()), credentials: true }));
app.use(express.json({ limit: '1mb' }));

app.get('/health', asyncHandler(async (_req, res) => {
  await pool.query('SELECT 1');
  res.json({ status: 'ok' });
}));
app.use('/api/auth', authRoutes);
app.use('/api/books', bookRoutes);
app.use('/api/clubs', clubRoutes);
app.use('/api', voteRoutes);
app.use('/api', threadRoutes);
app.use((_req, res) => res.status(404).json({ error: 'Route not found' }));
app.use(errorHandler);

const server = app.listen(config.port, () => {
  console.log(`BookClub API listening on port ${config.port}`);
});

async function shutdown(signal: string) {
  console.log(`${signal} received; shutting down`);
  server.close(async () => {
    await pool.end();
    process.exit(0);
  });
}

process.on('SIGTERM', () => void shutdown('SIGTERM'));
process.on('SIGINT', () => void shutdown('SIGINT'));
