import { pool } from './db.js';
import { HttpError } from './http.js';

export async function requireMember(clubId: string, userId: string) {
  const result = await pool.query<{ role: string }>(
    'SELECT role FROM club_members WHERE club_id = $1 AND user_id = $2',
    [clubId, userId],
  );
  if (!result.rows[0]) throw new HttpError(403, 'Join this club to continue');
  return result.rows[0];
}

export async function requireModerator(clubId: string, userId: string) {
  const member = await requireMember(clubId, userId);
  if (!['owner', 'moderator'].includes(member.role)) {
    throw new HttpError(403, 'Club moderator access required');
  }
  return member;
}

