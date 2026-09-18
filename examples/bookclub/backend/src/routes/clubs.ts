import { Router } from 'express';
import { z } from 'zod';
import { authenticate, optionalAuth } from '../auth.js';
import { pool } from '../db.js';
import { asyncHandler, HttpError } from '../http.js';
import type { AuthenticatedRequest } from '../types.js';

const router = Router();
const uuid = z.string().uuid();

router.get('/', optionalAuth, asyncHandler(async (req: AuthenticatedRequest, res) => {
  const search = z.string().trim().max(100).optional().parse(req.query.search);
  const params: unknown[] = [req.user?.id ?? null];
  let searchClause = '';
  if (search) {
    params.push(`%${search}%`);
    searchClause = 'AND (c.name ILIKE $2 OR c.description ILIKE $2)';
  }
  const result = await pool.query(
    `SELECT c.id, c.name, c.description, c.is_public AS "isPublic", c.created_at AS "createdAt",
       u.name AS "ownerName", COUNT(cm.user_id)::int AS "memberCount",
       EXISTS (SELECT 1 FROM club_members mine WHERE mine.club_id = c.id AND mine.user_id = $1) AS "isMember",
       CASE WHEN b.id IS NULL THEN NULL ELSE json_build_object(
         'id', b.id, 'title', b.title, 'author', b.author, 'coverUrl', b.cover_url
       ) END AS "currentBook"
     FROM clubs c
     JOIN users u ON u.id = c.owner_id
     LEFT JOIN club_members cm ON cm.club_id = c.id
     LEFT JOIN books b ON b.id = c.current_book_id
     WHERE (c.is_public OR EXISTS (
       SELECT 1 FROM club_members access WHERE access.club_id = c.id AND access.user_id = $1
     )) ${searchClause}
     GROUP BY c.id, u.name, b.id
     ORDER BY "isMember" DESC, c.created_at DESC`,
    params,
  );
  res.json({ clubs: result.rows });
}));

router.post('/', authenticate, asyncHandler(async (req: AuthenticatedRequest, res) => {
  const input = z.object({
    name: z.string().trim().min(3).max(160),
    description: z.string().trim().max(3000).optional().default(''),
    isPublic: z.boolean().optional().default(true),
  }).parse(req.body);
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const clubResult = await client.query(
      `INSERT INTO clubs (name, description, is_public, owner_id)
       VALUES ($1, $2, $3, $4)
       RETURNING id, name, description, is_public AS "isPublic", created_at AS "createdAt"`,
      [input.name, input.description, input.isPublic, req.user!.id],
    );
    await client.query(
      `INSERT INTO club_members (club_id, user_id, role) VALUES ($1, $2, 'owner')`,
      [clubResult.rows[0].id, req.user!.id],
    );
    await client.query('COMMIT');
    res.status(201).json({ club: clubResult.rows[0] });
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
}));

router.get('/:clubId', optionalAuth, asyncHandler(async (req: AuthenticatedRequest, res) => {
  const clubId = uuid.parse(req.params.clubId);
  const result = await pool.query(
    `SELECT c.id, c.name, c.description, c.is_public AS "isPublic", c.created_at AS "createdAt",
       u.name AS "ownerName", COUNT(cm.user_id)::int AS "memberCount",
       EXISTS (SELECT 1 FROM club_members mine WHERE mine.club_id = c.id AND mine.user_id = $2) AS "isMember",
       (SELECT role FROM club_members mine WHERE mine.club_id = c.id AND mine.user_id = $2) AS "myRole",
       CASE WHEN b.id IS NULL THEN NULL ELSE json_build_object(
         'id', b.id, 'title', b.title, 'author', b.author, 'description', b.description, 'coverUrl', b.cover_url
       ) END AS "currentBook"
     FROM clubs c
     JOIN users u ON u.id = c.owner_id
     LEFT JOIN club_members cm ON cm.club_id = c.id
     LEFT JOIN books b ON b.id = c.current_book_id
     WHERE c.id = $1
     GROUP BY c.id, u.name, b.id`,
    [clubId, req.user?.id ?? null],
  );
  const club = result.rows[0];
  if (!club || (!club.isPublic && !club.isMember)) throw new HttpError(404, 'Club not found');
  res.json({ club });
}));

router.post('/:clubId/join', authenticate, asyncHandler(async (req: AuthenticatedRequest, res) => {
  const clubId = uuid.parse(req.params.clubId);
  const club = await pool.query('SELECT is_public FROM clubs WHERE id = $1', [clubId]);
  if (!club.rows[0]) throw new HttpError(404, 'Club not found');
  if (!club.rows[0].is_public) throw new HttpError(403, 'This club is private');
  await pool.query(
    `INSERT INTO club_members (club_id, user_id) VALUES ($1, $2)
     ON CONFLICT (club_id, user_id) DO NOTHING`,
    [clubId, req.user!.id],
  );
  res.status(201).json({ message: 'You joined the club' });
}));

router.get('/:clubId/members', authenticate, asyncHandler(async (req: AuthenticatedRequest, res) => {
  const clubId = uuid.parse(req.params.clubId);
  const membership = await pool.query(
    'SELECT 1 FROM club_members WHERE club_id = $1 AND user_id = $2',
    [clubId, req.user!.id],
  );
  if (!membership.rows[0]) throw new HttpError(403, 'Join this club to view members');
  const result = await pool.query(
    `SELECT u.id, u.name, u.email, cm.role, cm.joined_at AS "joinedAt"
     FROM club_members cm JOIN users u ON u.id = cm.user_id
     WHERE cm.club_id = $1 ORDER BY cm.joined_at`,
    [clubId],
  );
  res.json({ members: result.rows });
}));

export default router;

