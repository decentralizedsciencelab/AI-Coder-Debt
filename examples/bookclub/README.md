# BookClub

BookClub is a complete reading-group platform for creating clubs, proposing and voting on books, and holding spoiler-safe chapter discussions. It includes a React SPA, an Express REST API, PostgreSQL schema and demo data, and a durable background worker that closes ballots and emails members.

## Run the application

Requirements: Docker Desktop or Docker Engine with Compose v2.

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Web app: http://localhost:3000
- REST API health: http://localhost:4000/health
- Captured development email: http://localhost:8025

Demo credentials:

```text
maya@bookclub.local
password123
```

Theo (`theo@bookclub.local`) and Nora (`nora@bookclub.local`) use the same demo password. The database initializes automatically on its first run.

To rebuild the database from the seed after changing `database/init.sql`:

```bash
docker compose down -v
docker compose up --build
```

## Architecture

```text
Browser → frontend (Nginx + React) → api (Express) → PostgreSQL
                                                ↗
                         worker (poll + outbox) ┘ → SMTP / Mailpit
```

- `frontend/`: React 18, TypeScript, Vite, responsive UI, Nginx runtime and `/api` reverse proxy.
- `backend/`: Express/TypeScript REST API with JWT authentication, Zod validation, authorization, parameterized SQL, and transaction boundaries.
- `worker/`: independent Node process. It locks due voting rounds, selects the winner deterministically, updates the club's current book, and writes a result message to a transactional outbox. Email retries use exponential backoff.
- `database/`: PostgreSQL 16 schema, indexes, constraints, and realistic seed data.

Each application component has its own Dockerfile. Runtime configuration is passed only through environment variables; see `.env.example`.

## REST API

All request and response bodies use JSON. Authenticated routes expect `Authorization: Bearer <token>`.

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/api/auth/register` | Create an account |
| POST | `/api/auth/login` | Sign in and receive a JWT |
| GET | `/api/auth/me` | Read the current user |
| GET/POST | `/api/clubs` | Browse or create clubs |
| GET | `/api/clubs/:clubId` | Club details and current read |
| POST | `/api/clubs/:clubId/join` | Join a public club |
| GET | `/api/clubs/:clubId/members` | List club members |
| GET/POST | `/api/books` | Browse or add library books |
| GET/POST | `/api/clubs/:clubId/rounds` | List or open voting rounds |
| POST | `/api/rounds/:roundId/candidates` | Propose a book |
| PUT | `/api/rounds/:roundId/vote` | Create or change a ballot |
| GET/POST | `/api/clubs/:clubId/threads` | Browse or create chapter threads |
| GET | `/api/threads/:threadId` | Read a thread and its posts |
| POST | `/api/threads/:threadId/posts` | Reply to a thread |

Only owners and moderators can open a voting round. Members can propose books, vote, and post. Private club content is protected at the API layer.

## Local development without containerized Node

Start PostgreSQL and Mailpit with Docker, then run each Node component:

```bash
docker compose up database mailpit

cd backend && npm install && npm run dev
cd frontend && npm install && npm run dev
cd worker && npm install && npm run dev
```

The local defaults connect to PostgreSQL on port 5432. When using a custom configuration, set `DATABASE_URL` for the API and worker, and `VITE_API_URL` for the frontend.

## Production notes

- Replace `JWT_SECRET`, database credentials, and SMTP values.
- Terminate TLS at a reverse proxy or load balancer.
- Set `CORS_ORIGIN` to the deployed frontend origin (comma-separated origins are supported).
- The included Mailpit service is for development. Point `SMTP_HOST` at a transactional email provider in production and omit Mailpit from the deployment.
- Back up the named PostgreSQL volume and run schema changes through versioned migrations for ongoing production evolution.

