CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE membership_role AS ENUM ('owner', 'moderator', 'member');
CREATE TYPE voting_status AS ENUM ('open', 'closed');

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(120) NOT NULL,
  email VARCHAR(255) NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE books (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  isbn VARCHAR(20),
  title VARCHAR(255) NOT NULL,
  author VARCHAR(255) NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  cover_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (title, author)
);

CREATE TABLE clubs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(160) NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  owner_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  current_book_id UUID REFERENCES books(id) ON DELETE SET NULL,
  is_public BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE club_members (
  club_id UUID NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role membership_role NOT NULL DEFAULT 'member',
  joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (club_id, user_id)
);

CREATE TABLE voting_rounds (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  club_id UUID NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
  title VARCHAR(180) NOT NULL,
  closes_at TIMESTAMPTZ NOT NULL,
  status voting_status NOT NULL DEFAULT 'open',
  winner_book_id UUID REFERENCES books(id) ON DELETE SET NULL,
  created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  closed_at TIMESTAMPTZ,
  CONSTRAINT closes_after_creation CHECK (closes_at > created_at)
);

CREATE UNIQUE INDEX one_open_round_per_club
  ON voting_rounds (club_id) WHERE status = 'open';

CREATE TABLE vote_candidates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  round_id UUID NOT NULL REFERENCES voting_rounds(id) ON DELETE CASCADE,
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  proposed_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  pitch TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (round_id, book_id),
  UNIQUE (round_id, id)
);

CREATE TABLE votes (
  round_id UUID NOT NULL,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  candidate_id UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (round_id, user_id),
  FOREIGN KEY (round_id, candidate_id)
    REFERENCES vote_candidates(round_id, id) ON DELETE CASCADE
);

CREATE TABLE discussion_threads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  club_id UUID NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  chapter_number INTEGER NOT NULL CHECK (chapter_number > 0),
  title VARCHAR(255) NOT NULL,
  created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX threads_club_book_chapter_idx
  ON discussion_threads (club_id, book_id, chapter_number);

CREATE TABLE posts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  thread_id UUID NOT NULL REFERENCES discussion_threads(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  body TEXT NOT NULL CHECK (char_length(trim(body)) > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX posts_thread_created_idx ON posts (thread_id, created_at);
CREATE INDEX rounds_closing_idx ON voting_rounds (status, closes_at);

CREATE TABLE vote_result_outbox (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  round_id UUID NOT NULL UNIQUE REFERENCES voting_rounds(id) ON DELETE CASCADE,
  recipients TEXT[] NOT NULL,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  sent_at TIMESTAMPTZ,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX vote_result_outbox_pending_idx
  ON vote_result_outbox (next_attempt_at) WHERE sent_at IS NULL;

INSERT INTO users (id, name, email, password_hash) VALUES
  ('11111111-1111-4111-8111-111111111111', 'Maya Chen', 'maya@bookclub.local', crypt('password123', gen_salt('bf', 10))),
  ('22222222-2222-4222-8222-222222222222', 'Theo James', 'theo@bookclub.local', crypt('password123', gen_salt('bf', 10))),
  ('33333333-3333-4333-8333-333333333333', 'Nora Patel', 'nora@bookclub.local', crypt('password123', gen_salt('bf', 10)));

INSERT INTO books (id, isbn, title, author, description, cover_url) VALUES
  ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1', '9780385547345', 'Tomorrow, and Tomorrow, and Tomorrow', 'Gabrielle Zevin', 'A novel about friendship, identity, and the worlds we build together.', 'https://covers.openlibrary.org/b/isbn/9780385547345-L.jpg'),
  ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2', '9780593593806', 'The Heaven & Earth Grocery Store', 'James McBride', 'A compassionate portrait of a small community and its hidden histories.', 'https://covers.openlibrary.org/b/isbn/9780593593806-L.jpg'),
  ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3', '9780593418484', 'Sea of Tranquility', 'Emily St. John Mandel', 'An elegant time-travel story spanning centuries and distant places.', 'https://covers.openlibrary.org/b/isbn/9780593418484-L.jpg'),
  ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa4', '9780525559474', 'The Midnight Library', 'Matt Haig', 'A moving exploration of regret, possibility, and what makes a life worth living.', 'https://covers.openlibrary.org/b/isbn/9780525559474-L.jpg'),
  ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa5', '9781635570304', 'Circe', 'Madeline Miller', 'A vivid reimagining of an immortal woman finding power in exile.', 'https://covers.openlibrary.org/b/isbn/9781635570304-L.jpg');

INSERT INTO clubs (id, name, description, owner_id, current_book_id) VALUES
  ('cccccccc-cccc-4ccc-8ccc-ccccccccccc1', 'Between the Lines', 'Contemporary fiction, strong coffee, and conversations that linger.', '11111111-1111-4111-8111-111111111111', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1'),
  ('cccccccc-cccc-4ccc-8ccc-ccccccccccc2', 'Speculative Sundays', 'Science fiction and fantasy for curious minds. We meet every other Sunday.', '22222222-2222-4222-8222-222222222222', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3');

INSERT INTO club_members (club_id, user_id, role) VALUES
  ('cccccccc-cccc-4ccc-8ccc-ccccccccccc1', '11111111-1111-4111-8111-111111111111', 'owner'),
  ('cccccccc-cccc-4ccc-8ccc-ccccccccccc1', '22222222-2222-4222-8222-222222222222', 'member'),
  ('cccccccc-cccc-4ccc-8ccc-ccccccccccc1', '33333333-3333-4333-8333-333333333333', 'member'),
  ('cccccccc-cccc-4ccc-8ccc-ccccccccccc2', '22222222-2222-4222-8222-222222222222', 'owner'),
  ('cccccccc-cccc-4ccc-8ccc-ccccccccccc2', '11111111-1111-4111-8111-111111111111', 'member');

INSERT INTO voting_rounds (id, club_id, title, closes_at, created_by) VALUES
  ('dddddddd-dddd-4ddd-8ddd-ddddddddddd1', 'cccccccc-cccc-4ccc-8ccc-ccccccccccc1', 'Our October read', NOW() + INTERVAL '10 days', '11111111-1111-4111-8111-111111111111'),
  ('dddddddd-dddd-4ddd-8ddd-ddddddddddd2', 'cccccccc-cccc-4ccc-8ccc-ccccccccccc2', 'Next speculative journey', NOW() + INTERVAL '7 days', '22222222-2222-4222-8222-222222222222');

INSERT INTO vote_candidates (id, round_id, book_id, proposed_by, pitch) VALUES
  ('eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee1', 'dddddddd-dddd-4ddd-8ddd-ddddddddddd1', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2', '22222222-2222-4222-8222-222222222222', 'Warm, mysterious, and perfect for a layered group conversation.'),
  ('eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee2', 'dddddddd-dddd-4ddd-8ddd-ddddddddddd1', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa4', '33333333-3333-4333-8333-333333333333', 'A very readable doorway into big questions about choice.'),
  ('eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee3', 'dddddddd-dddd-4ddd-8ddd-ddddddddddd2', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa5', '11111111-1111-4111-8111-111111111111', 'Mythic, beautifully written, and full of themes worth unpacking.'),
  ('eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee4', 'dddddddd-dddd-4ddd-8ddd-ddddddddddd2', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa4', '22222222-2222-4222-8222-222222222222', 'A high-concept premise with lots to debate.');

INSERT INTO votes (round_id, user_id, candidate_id) VALUES
  ('dddddddd-dddd-4ddd-8ddd-ddddddddddd1', '11111111-1111-4111-8111-111111111111', 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee1'),
  ('dddddddd-dddd-4ddd-8ddd-ddddddddddd1', '22222222-2222-4222-8222-222222222222', 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee1'),
  ('dddddddd-dddd-4ddd-8ddd-ddddddddddd1', '33333333-3333-4333-8333-333333333333', 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee2'),
  ('dddddddd-dddd-4ddd-8ddd-ddddddddddd2', '11111111-1111-4111-8111-111111111111', 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee3');

INSERT INTO discussion_threads (id, club_id, book_id, chapter_number, title, created_by) VALUES
  ('ffffffff-ffff-4fff-8fff-fffffffffff1', 'cccccccc-cccc-4ccc-8ccc-ccccccccccc1', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1', 3, 'Is collaboration ever truly equal?', '11111111-1111-4111-8111-111111111111'),
  ('ffffffff-ffff-4fff-8fff-fffffffffff2', 'cccccccc-cccc-4ccc-8ccc-ccccccccccc1', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1', 7, 'The meaning of the NPCs', '33333333-3333-4333-8333-333333333333'),
  ('ffffffff-ffff-4fff-8fff-fffffffffff3', 'cccccccc-cccc-4ccc-8ccc-ccccccccccc2', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3', 2, 'The moon colony as a mirror', '22222222-2222-4222-8222-222222222222');

INSERT INTO posts (thread_id, user_id, body, created_at) VALUES
  ('ffffffff-ffff-4fff-8fff-fffffffffff1', '11111111-1111-4111-8111-111111111111', 'Sam and Sadie keep trading the spotlight, but their power never feels quite balanced. Did anyone else notice how the game credits shift that?', NOW() - INTERVAL '2 days'),
  ('ffffffff-ffff-4fff-8fff-fffffffffff1', '22222222-2222-4222-8222-222222222222', 'Yes—the creative partnership feels sincere while the business partnership quietly tells a different story.', NOW() - INTERVAL '1 day'),
  ('ffffffff-ffff-4fff-8fff-fffffffffff2', '33333333-3333-4333-8333-333333333333', 'I read them as stand-ins for all the unnoticed people who make creative work possible.', NOW() - INTERVAL '5 hours');
