import { Router } from 'express';
import { z } from 'zod';
import { authenticate } from '../auth.js';
import { pool } from '../db.js';
import { asyncHandler, HttpError } from '../http.js';
import { requireMember, requireModerator } from '../permissions.js';
import type { AuthenticatedRequest } from '../types.js';

const router = Router();
const uuid = z.string().uuid();

router.get('/clubs/:clubId/rounds', authenticate, asyncHandler(async (req: AuthenticatedRequest, res) => {
  const clubId = uuid.parse(req.params.clubId);
  await requireMember(clubId, req.user!.id);
  const result = await pool.query(
    `SELECT vr.id, vr.title, vr.closes_at AS "closesAt", vr.status,
       vr.winner_book_id AS "winnerBookId", vr.closed_at AS "closedAt",
       COALESCE(json_agg(json_build_object(
         'id', vc.id, 'pitch', vc.pitch, 'book', json_build_object(
           'id', b.id, 'title', b.title, 'author', b.author,
           'description', b.description, 'coverUrl', b.cover_url
         ),
         'proposedBy', proposer.name,
         'voteCount', (SELECT COUNT(*)::int FROM votes v WHERE v.candidate_id = vc.id)
       ) ORDER BY vc.created_at) FILTER (WHERE vc.id IS NOT NULL), '[]') AS candidates,
       (SELECT candidate_id FROM votes mine WHERE mine.round_id = vr.id AND mine.user_id = $2) AS "myVote"
     FROM voting_rounds vr
     LEFT JOIN vote_candidates vc ON vc.round_id = vr.id
     LEFT JOIN books b ON b.id = vc.book_id
     LEFT JOIN users proposer ON proposer.id = vc.proposed_by
     WHERE vr.club_id = $1
     GROUP BY vr.id
     ORDER BY CASE WHEN vr.status = 'open' THEN 0 ELSE 1 END, vr.created_at DESC`,
    [clubId, req.user!.id],
  );
  res.json({ rounds: result.rows });
}));

router.post('/clubs/:clubId/rounds', authenticate, asyncHandler(async (req: AuthenticatedRequest, res) => {
  const clubId = uuid.parse(req.params.clubId);
  await requireModerator(clubId, req.user!.id);
  const input = z.object({
    title: z.string().trim().min(3).max(180),
    closesAt: z.coerce.date().refine((date) => date.getTime() > Date.now(), 'Closing time must be in the future'),
  }).parse(req.body);
  const result = await pool.query(
    `INSERT INTO voting_rounds (club_id, title, closes_at, created_by)
     VALUES ($1, $2, $3, $4)
     RETURNING id, title, closes_at AS "closesAt", status`,
    [clubId, input.title, input.closesAt, req.user!.id],
  );
  res.status(201).json({ round: result.rows[0] });
}));

router.post('/rounds/:roundId/candidates', authenticate, asyncHandler(async (req: AuthenticatedRequest, res) => {
  const roundId = uuid.parse(req.params.roundId);
  const input = z.object({
    bookId: z.string().uuid(),
    pitch: z.string().trim().max(2000).optional().default(''),
  }).parse(req.body);
  const round = await pool.query(
    'SELECT club_id, status, closes_at FROM voting_rounds WHERE id = $1',
    [roundId],
  );
  if (!round.rows[0]) throw new HttpError(404, 'Voting round not found');
  await requireMember(round.rows[0].club_id, req.user!.id);
  if (round.rows[0].status !== 'open' || new Date(round.rows[0].closes_at) <= new Date()) {
    throw new HttpError(409, 'This voting round is closed');
  }
  const result = await pool.query(
    `INSERT INTO vote_candidates (round_id, book_id, proposed_by, pitch)
     VALUES ($1, $2, $3, $4)
     RETURNING id, book_id AS "bookId", pitch`,
    [roundId, input.bookId, req.user!.id, input.pitch],
  );
  res.status(201).json({ candidate: result.rows[0] });
}));

router.put('/rounds/:roundId/vote', authenticate, asyncHandler(async (req: AuthenticatedRequest, res) => {
  const roundId = uuid.parse(req.params.roundId);
  const { candidateId } = z.object({ candidateId: z.string().uuid() }).parse(req.body);
  const result = await pool.query(
    `SELECT vr.club_id, vr.status, vr.closes_at
     FROM voting_rounds vr
     JOIN vote_candidates vc ON vc.round_id = vr.id
     WHERE vr.id = $1 AND vc.id = $2`,
    [roundId, candidateId],
  );
  const round = result.rows[0];
  if (!round) throw new HttpError(404, 'Candidate not found in this round');
  await requireMember(round.club_id, req.user!.id);
  if (round.status !== 'open' || new Date(round.closes_at) <= new Date()) {
    throw new HttpError(409, 'This voting round is closed');
  }
  await pool.query(
    `INSERT INTO votes (round_id, user_id, candidate_id) VALUES ($1, $2, $3)
     ON CONFLICT (round_id, user_id) DO UPDATE
     SET candidate_id = EXCLUDED.candidate_id, updated_at = NOW()`,
    [roundId, req.user!.id, candidateId],
  );
  res.json({ message: 'Vote recorded', candidateId });
}));

export default router;

