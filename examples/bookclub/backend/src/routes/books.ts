import { Router } from 'express';
import { z } from 'zod';
import { authenticate } from '../auth.js';
import { pool } from '../db.js';
import { asyncHandler } from '../http.js';

const router = Router();

router.get('/', asyncHandler(async (req, res) => {
  const search = z.string().trim().max(100).optional().parse(req.query.search);
  const params: unknown[] = [];
  let where = '';
  if (search) {
    params.push(`%${search}%`);
    where = 'WHERE title ILIKE $1 OR author ILIKE $1 OR isbn ILIKE $1';
  }
  const result = await pool.query(
    `SELECT id, isbn, title, author, description, cover_url AS "coverUrl", created_at AS "createdAt"
     FROM books ${where} ORDER BY title LIMIT 100`,
    params,
  );
  res.json({ books: result.rows });
}));

router.post('/', authenticate, asyncHandler(async (req, res) => {
  const input = z.object({
    title: z.string().trim().min(1).max(255),
    author: z.string().trim().min(1).max(255),
    isbn: z.string().trim().max(20).optional().nullable(),
    description: z.string().trim().max(5000).optional().default(''),
    coverUrl: z.string().url().optional().nullable(),
  }).parse(req.body);
  const result = await pool.query(
    `INSERT INTO books (title, author, isbn, description, cover_url)
     VALUES ($1, $2, $3, $4, $5)
     RETURNING id, isbn, title, author, description, cover_url AS "coverUrl", created_at AS "createdAt"`,
    [input.title, input.author, input.isbn || null, input.description, input.coverUrl || null],
  );
  res.status(201).json({ book: result.rows[0] });
}));

export default router;

