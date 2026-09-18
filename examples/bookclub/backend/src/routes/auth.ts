import { Router } from 'express';
import bcrypt from 'bcryptjs';
import { z } from 'zod';
import { authenticate, signToken } from '../auth.js';
import { pool } from '../db.js';
import { asyncHandler, HttpError } from '../http.js';
import type { AuthenticatedRequest } from '../types.js';

const router = Router();

const credentialsSchema = z.object({
  email: z.string().email().transform((value) => value.toLowerCase().trim()),
  password: z.string().min(8).max(72),
});

router.post('/register', asyncHandler(async (req, res) => {
  const input = credentialsSchema.extend({ name: z.string().trim().min(2).max(120) }).parse(req.body);
  const passwordHash = await bcrypt.hash(input.password, 12);
  const result = await pool.query(
    `INSERT INTO users (name, email, password_hash)
     VALUES ($1, $2, $3)
     RETURNING id, name, email, created_at AS "createdAt"`,
    [input.name, input.email, passwordHash],
  );
  const user = result.rows[0];
  res.status(201).json({ user, token: signToken(user) });
}));

router.post('/login', asyncHandler(async (req, res) => {
  const input = credentialsSchema.parse(req.body);
  const result = await pool.query(
    'SELECT id, name, email, password_hash FROM users WHERE email = $1',
    [input.email],
  );
  const record = result.rows[0];
  if (!record || !(await bcrypt.compare(input.password, record.password_hash))) {
    throw new HttpError(401, 'Email or password is incorrect');
  }
  const user = { id: record.id, name: record.name, email: record.email };
  res.json({ user, token: signToken(user) });
}));

router.get('/me', authenticate, asyncHandler(async (req: AuthenticatedRequest, res) => {
  const result = await pool.query(
    'SELECT id, name, email, created_at AS "createdAt" FROM users WHERE id = $1',
    [req.user!.id],
  );
  if (!result.rows[0]) throw new HttpError(404, 'User not found');
  res.json({ user: result.rows[0] });
}));

export default router;

