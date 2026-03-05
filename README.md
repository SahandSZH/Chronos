# Stay On Track Backend (FastAPI + Neon Postgres)

Backend API for a personal productivity app with:

- JWT authentication
- Daily task view (home page)
- Forgotten tasks view (past incomplete tasks)
- Calendar month/day views
- One-time and recurring tasks (daily/weekly)
- Google Calendar OAuth connection and per-day sync

## 1. Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env` from `.env.example` and fill values:

- `DATABASE_URL`: Neon Postgres URL
- `JWT_SECRET_KEY`: long random secret
- Optional Google keys for calendar sync

## 2. Run

```bash
python main.py
```

API docs:

- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

## 3. Core Endpoints

### Auth

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login` (form-data: `username`, `password`)
- `POST /api/v1/auth/login-json` (JSON body)
- `GET /api/v1/auth/me`

### Tasks

- `GET /api/v1/tasks/today`
- `GET /api/v1/tasks/day/{target_date}`
- `GET /api/v1/tasks/forgotten`
- `POST /api/v1/tasks/`
- `GET /api/v1/tasks/{task_id}`
- `PATCH /api/v1/tasks/{task_id}`
- `DELETE /api/v1/tasks/{task_id}`
- `POST /api/v1/tasks/{task_id}/completion`

### Calendar

- `GET /api/v1/calendar/month`
- `GET /api/v1/calendar/day/{target_date}`

### Google Calendar

- `GET /api/v1/google/status`
- `GET /api/v1/google/auth-url`
- `GET /api/v1/google/callback`
- `POST /api/v1/google/sync/day?date=YYYY-MM-DD`

## 4. Recurring Task Rules

- `repeat_type=none`: occurs only on `start_date`
- `repeat_type=daily`: repeats every `repeat_interval` days
- `repeat_type=weekly`: repeats on `repeat_weekdays` (`0=Mon ... 6=Sun`) every `repeat_interval` weeks
- `end_date` is optional and stops recurrence when set

## 5. Notes for Frontend (Lovable)

- Use bearer token from login in `Authorization: Bearer <token>`
- Home page can call `GET /api/v1/tasks/today`
- Forgotten page can call `GET /api/v1/tasks/forgotten`
- Calendar page can call `GET /api/v1/calendar/month` and `/day/{date}`
- Task detail page can call `GET /api/v1/tasks/{task_id}?date=YYYY-MM-DD`

## 6. Deploy on Render

This repo is ready for Render deployment via GitHub:

- `render.yaml` is included
- Start command uses Render's `$PORT`
- `.python-version` pins Python `3.11.9`

### Steps

1. Push this repo to GitHub.
2. In Render, create a **Blueprint** (or **Web Service**) from this repository.
3. Set required environment variables:
   - `DATABASE_URL` (Neon connection string with SSL)
   - `CORS_ORIGINS` (your frontend domain, comma-separated if multiple)
4. Optional for Google Calendar:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REDIRECT_URI` (must match your Render backend callback URL)
5. Deploy.

Health check endpoint:

- `GET /health`
