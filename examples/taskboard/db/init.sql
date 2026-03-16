CREATE TABLE IF NOT EXISTS tasks (
  id SERIAL PRIMARY KEY,
  title VARCHAR(255) NOT NULL,
  description TEXT,
  status VARCHAR(20) NOT NULL DEFAULT 'todo',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO tasks (title, description, status) VALUES
  ('Set up CI pipeline', 'Configure GitHub Actions for automated testing', 'todo'),
  ('Design landing page', 'Create wireframes and mockups', 'in_progress'),
  ('Write API docs', 'Document all REST endpoints', 'done');
