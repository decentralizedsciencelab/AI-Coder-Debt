import { Router } from 'express';
import { z } from 'zod';
import { authenticate } from '../auth.js';
import { pool } from '../db.js';
import { asyncHandler, HttpError } from '../http.js';
import { requireMember } from '../permissions.js';
import type { AuthenticatedRequest } from '../types.js';

const router = Router();
const uuid = z.string().uuid();

router.get('/clubs/:clubId/threads', authenticate, asyncHandler(async (req: AuthenticatedRequest, res) => {
  const clubId = uuid.parse(req.params.clubId);
  await requireMember(clubId, req.user!.id);
  const bookId = z.string().uuid().optional().parse(req.query.bookId);
  const chapter = z.coerce.number().int().positive().optional().parse(req.query.chapter);
  const params: unknown[] = [clubId];
  const filters: string[] = [];
  if (bookId) { params.push(bookId); filters.push(`dt.book_id = $${params.length}`); }
  if (chapter) { params.push(chapter); filters.push(`dt.chapter_number = $${params.length}`); }
  const result = await pool.query(
    `SELECT dt.id, dt.title, dt.chapter_number AS "chapterNumber", dt.created_at AS "createdAt",
       json_build_object('id', b.id, 'title', b.title, 'author', b.author, 'coverUrl', b.cover_url) AS book,
       u.name AS "createdBy", COUNT(p.id)::int AS "postCount",
       MAX(p.created_at) AS "lastActivityAt"
     FROM discussion_threads dt
     JOIN books b ON b.id = dt.book_id
     JOIN users u ON u.id = dt.created_by
     LEFT JOIN posts p ON p.thread_id = dt.id
     WHERE dt.club_id = $1 ${filters.length ? `AND ${filters.join(' AND ')}` : ''}
     GROUP BY dt.id, b.id, u.name
     ORDER BY dt.chapter_number, COALESCE(MAX(p.created_at), dt.created_at) DESC`,
    params,
  );
  res.json({ threads: result.rows });
}));

router.post('/clubs/:clubId/threads', authenticate, asyncHandler(async (req: AuthenticatedRequest, res) => {
  const clubId = uuid.parse(req.params.clubId);
  await requireMember(clubId, req.user!.id);
  const input = z.object({
    bookId: z.string().uuid(),
    chapterNumber: z.number().int().positive().max(10000),
    title: z.string().trim().min(3).max(255),
    body: z.string().trim().min(1).max(10000),
  }).parse(req.body);
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const threadResult = await client.query(
      `INSERT INTO discussion_threads (club_id, book_id, chapter_number, title, created_by)
       VALUES ($1, $2, $3, $4, $5)
       RETURNING id, title, chapter_number AS "chapterNumber", created_at AS "createdAt"`,
      [clubId, input.bookId, input.chapterNumber, input.title, req.user!.id],
    );
    await client.query(
      'INSERT INTO posts (thread_id, user_id, body) VALUES ($1, $2, $3)',
      [threadResult.rows[0].id, req.user!.id, input.body],
    );
    await client.query('COMMIT');
    res.status(201).json({ thread: threadResult.rows[0] });
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
}));

router.get('/threads/:threadId', authenticate, asyncHandler(async (req: AuthenticatedRequest, res) => {
  const threadId = uuid.parse(req.params.threadId);
  const threadResult = await pool.query(
    `SELECT dt.id, dt.club_id AS "clubId", dt.title, dt.chapter_number AS "chapterNumber", dt.created_at AS "createdAt",
       json_build_object('id', b.id, 'title', b.title, 'author', b.author, 'coverUrl', b.cover_url) AS book,
       u.name AS "createdBy"
     FROM discussion_threads dt
     JOIN books b ON b.id = dt.book_id JOIN users u ON u.id = dt.created_by
     WHERE dt.id = $1`,
    [threadId],
  );
  const thread = threadResult.rows[0];
  if (!thread) throw new HttpError(404, 'Thread not found');
  await requireMember(thread.clubId, req.user!.id);
  const posts = await pool.query(
    `SELECT p.id, p.body, p.created_at AS "createdAt", p.updated_at AS "updatedAt",
       json_build_object('id', u.id, 'name', u.name) AS author
     FROM posts p JOIN users u ON u.id = p.user_id
     WHERE p.thread_id = $1 ORDER BY p.created_at`,
    [threadId],
  );
  res.json({ thread: { ...thread, posts: posts.rows } });
}));

router.post('/threads/:threadId/posts', authenticate, asyncHandler(async (req: AuthenticatedRequest, res) => {
  const threadId = uuid.parse(req.params.threadId);
  const { body } = z.object({ body: z.string().trim().min(1).max(10000) }).parse(req.body);
  const thread = await pool.query('SELECT club_id FROM discussion_threads WHERE id = $1', [threadId]);
  if (!thread.rows[0]) throw new HttpError(404, 'Thread not found');
  await requireMember(thread.rows[0].club_id, req.user!.id);
  const result = await pool.query(
    `INSERT INTO posts (thread_id, user_id, body) VALUES ($1, $2, $3)
     RETURNING id, body, created_at AS "createdAt", updated_at AS "updatedAt"`,
    [threadId, req.user!.id, body],
  );
  res.status(201).json({ post: { ...result.rows[0], author: { id: req.user!.id, name: req.user!.name } } });
}));

export default router;

