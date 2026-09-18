import 'dotenv/config';
import nodemailer from 'nodemailer';
import pg from 'pg';

const { Pool } = pg;
const databaseUrl = process.env.DATABASE_URL ?? 'postgres://bookclub:bookclub@localhost:5432/bookclub';
const pollIntervalMs = Math.max(Number(process.env.POLL_INTERVAL_MS ?? 15000), 1000);
const fromAddress = process.env.EMAIL_FROM ?? 'BookClub <results@bookclub.local>';
const pool = new Pool({ connectionString: databaseUrl });

const transporter = process.env.SMTP_HOST
  ? nodemailer.createTransport({
      host: process.env.SMTP_HOST,
      port: Number(process.env.SMTP_PORT ?? 1025),
      secure: process.env.SMTP_SECURE === 'true',
      auth: process.env.SMTP_USER
        ? { user: process.env.SMTP_USER, pass: process.env.SMTP_PASSWORD ?? '' }
        : undefined,
    })
  : nodemailer.createTransport({ jsonTransport: true });

let stopping = false;

async function closeRound(roundId: string) {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const roundResult = await client.query(
      `SELECT vr.id, vr.club_id, vr.title, c.name AS club_name
       FROM voting_rounds vr JOIN clubs c ON c.id = vr.club_id
       WHERE vr.id = $1 AND vr.status = 'open' AND vr.closes_at <= NOW()
       FOR UPDATE OF vr SKIP LOCKED`,
      [roundId],
    );
    const round = roundResult.rows[0];
    if (!round) {
      await client.query('ROLLBACK');
      return;
    }

    const winnerResult = await client.query(
      `SELECT vc.book_id, b.title, b.author, COUNT(v.user_id)::int AS vote_count
       FROM vote_candidates vc
       JOIN books b ON b.id = vc.book_id
       LEFT JOIN votes v ON v.candidate_id = vc.id
       WHERE vc.round_id = $1
       GROUP BY vc.id, b.id
       ORDER BY vote_count DESC, vc.created_at ASC
       LIMIT 1`,
      [round.id],
    );
    const winner = winnerResult.rows[0] as
      | { book_id: string; title: string; author: string; vote_count: number }
      | undefined;

    await client.query(
      `UPDATE voting_rounds
       SET status = 'closed', winner_book_id = $2, closed_at = NOW()
       WHERE id = $1`,
      [round.id, winner?.book_id ?? null],
    );
    if (winner) {
      await client.query('UPDATE clubs SET current_book_id = $2 WHERE id = $1', [round.club_id, winner.book_id]);
    }

    const members = await client.query<{ email: string }>(
      `SELECT u.email FROM club_members cm JOIN users u ON u.id = cm.user_id WHERE cm.club_id = $1`,
      [round.club_id],
    );
    const recipients = members.rows.map((member) => member.email);
    const resultLine = winner
      ? `${winner.title} by ${winner.author} won with ${winner.vote_count} vote${winner.vote_count === 1 ? '' : 's'}.`
      : 'The round closed without any proposed books.';
    await client.query(
      `INSERT INTO vote_result_outbox (round_id, recipients, subject, body)
       VALUES ($1, $2, $3, $4) ON CONFLICT (round_id) DO NOTHING`,
      [
        round.id,
        recipients,
        `Voting results: ${round.title}`,
        `The “${round.title}” vote in ${round.club_name} is closed.\n\n${resultLine}\n\nHappy reading!`,
      ],
    );
    await client.query('COMMIT');
    console.log(`Closed voting round ${round.id}${winner ? `; winner: ${winner.title}` : '; no candidates'}`);
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
}

async function closeExpiredRounds() {
  const due = await pool.query<{ id: string }>(
    `SELECT id FROM voting_rounds WHERE status = 'open' AND closes_at <= NOW() ORDER BY closes_at LIMIT 25`,
  );
  for (const round of due.rows) await closeRound(round.id);
}

async function deliverPendingEmails() {
  const pending = await pool.query<{
    id: string;
    recipients: string[];
    subject: string;
    body: string;
    attempts: number;
  }>(
    `WITH claimable AS (
       SELECT id FROM vote_result_outbox
       WHERE sent_at IS NULL AND next_attempt_at <= NOW()
       ORDER BY created_at LIMIT 20
       FOR UPDATE SKIP LOCKED
     )
     UPDATE vote_result_outbox AS email
     SET next_attempt_at = NOW() + INTERVAL '5 minutes'
     FROM claimable
     WHERE email.id = claimable.id
     RETURNING email.id, email.recipients, email.subject, email.body, email.attempts`,
  );

  for (const email of pending.rows) {
    if (email.recipients.length === 0) {
      await pool.query('UPDATE vote_result_outbox SET sent_at = NOW() WHERE id = $1', [email.id]);
      continue;
    }
    try {
      await transporter.sendMail({
        from: fromAddress,
        to: email.recipients.join(', '),
        subject: email.subject,
        text: email.body,
      });
      await pool.query(
        'UPDATE vote_result_outbox SET sent_at = NOW(), attempts = attempts + 1, last_error = NULL WHERE id = $1',
        [email.id],
      );
      console.log(`Sent vote result email ${email.id} to ${email.recipients.length} member(s)`);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const retryMinutes = Math.min(2 ** Math.min(email.attempts, 6), 60);
      await pool.query(
        `UPDATE vote_result_outbox SET attempts = attempts + 1, last_error = $2,
         next_attempt_at = NOW() + ($3 * INTERVAL '1 minute') WHERE id = $1`,
        [email.id, message.slice(0, 2000), retryMinutes],
      );
      console.error(`Failed to send email ${email.id}; retrying in ${retryMinutes} minute(s):`, message);
    }
  }
}

async function tick() {
  try {
    await closeExpiredRounds();
    await deliverPendingEmails();
  } catch (error) {
    console.error('Worker cycle failed', error);
  }
}

async function run() {
  await pool.query('SELECT 1');
  console.log(`BookClub worker started (polling every ${pollIntervalMs}ms)`);
  while (!stopping) {
    await tick();
    await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
  }
  await pool.end();
}

process.on('SIGTERM', () => { stopping = true; });
process.on('SIGINT', () => { stopping = true; });

run().catch((error) => {
  console.error('Worker stopped unexpectedly', error);
  process.exit(1);
});
