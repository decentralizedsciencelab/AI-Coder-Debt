# TaskBoard

A kanban-style task management board with three columns: To Do, In Progress, and Done.

## Architecture

- **frontend/** — React single-page application
- **api/** — Express REST API with PostgreSQL
- **db/** — Database seed script

## Getting Started

```bash
docker-compose up
```

The frontend runs on port 3000 and the API on port 3001.

## API Endpoints

- `GET /api/tasks` — List all tasks
- `POST /api/tasks` — Create a new task
- `PATCH /api/tasks/:id` — Update a task
- `DELETE /api/tasks/:id` — Delete a task
