# Finance Tracker

A personal-finance platform built as a monorepo: a **React/Vite web app**, an
**Expo React Native mobile app**, and a **FastAPI modular-monolith API** backed
by PostgreSQL — shipped together with Docker Compose (nginx proxies `/v1` to the
API).

| Component | Path | Stack |
|---|---|---|
| Web | [`fin-front/`](./fin-front) | React 18, Vite, TypeScript, Tailwind, Vitest |
| Mobile | [`fin-mobile/`](./fin-mobile) | Expo, React Native, React Navigation |
| API | [`fin-backend/`](./fin-backend) | FastAPI, async SQLAlchemy 2.0, Alembic, Pydantic, Postgres |

## Architecture

The backend is a **modular monolith**: thin `v1` routers delegate to a
service-per-module, which uses a repository-per-module over async SQLAlchemy
models. Domain modules live under `fin-backend/app/modules/`
(`accounts`, `transactions`, `budgets`, `goals`).

```
HTTP → router (app/api/v1) → service (app/modules/*/service.py)
     → repository (app/modules/*/repository.py) → model (app/models)
```

Cross-cutting concerns:

- **Request IDs** — every request carries an `X-Request-Id` (generated or echoed).
- **Structured logging** — JSON logs with per-request context and latency (`app/observability`).
- **Problem+JSON** — errors follow [RFC 7807](https://datatracker.ietf.org/doc/html/rfc7807).
- **CSRF protection** — token required on authenticated mutating requests.
- **Login throttling** — per-email failure rate limiting.
- **Idempotency** — `Idempotency-Key` support for transaction creation.

See [`docs/architecture-review.md`](./docs/architecture-review.md) and the
[ADRs](./docs/adr/) for deeper context, and [`docs/phases/`](./docs/phases) for
the production-hardening roadmap.

## Quick start (Docker)

```bash
# Build and run Postgres + API + web
docker compose up --build

# First run (or after pulling new migrations): apply the schema
docker compose run --rm api poetry run alembic upgrade head
```

Then open <http://localhost:8080>.

## Local development

### Backend (`fin-backend`)

```bash
cd fin-backend
poetry install --with dev
poetry run alembic upgrade head        # requires a running Postgres
poetry run uvicorn app.main:app --reload
```

Run the checks:

```bash
poetry run ruff check app tests        # lint
poetry run pytest                      # tests + coverage gate
```

### Web (`fin-front`)

```bash
npm install
npm run web                            # dev server
npm run web:build                      # production build
```

### Mobile (`fin-mobile`)

```bash
npm run mobile                         # Expo dev server
```

## Configuration

The API reads configuration from environment variables (see
[`fin-backend/.env.example`](./fin-backend/.env.example)):

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | `staging`/`production` enforce a strong `SECRET_KEY` |
| `SECRET_KEY` | `change-me` | Must be ≥32 chars and non-placeholder outside development |
| `DATABASE_URL` | local Postgres | async (`postgresql+asyncpg://…`) |
| `CORS_ORIGINS` | localhost | comma-separated allowlist |
| `LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR`/`CRITICAL` |

## Continuous integration

GitHub Actions run on every push and pull request to `main`:

- **CI** ([`ci.yml`](./.github/workflows/ci.yml)) — web lint/test/build, mobile
  typecheck, API ruff + pytest (with a coverage floor), and a Docker Compose build.
- **CodeQL** ([`codeql.yml`](./.github/workflows/codeql.yml)) — static security
  analysis for Python and JavaScript/TypeScript, plus a weekly scheduled scan.
- **Dependabot** keeps dependencies patched.

## Contributing & security

- Contribution workflow: [`CONTRIBUTING.md`](./CONTRIBUTING.md)
- Vulnerability disclosure: [`SECURITY.md`](./SECURITY.md)
- Change history: [`CHANGELOG.md`](./CHANGELOG.md)

## License

Licensed under the [Apache License 2.0](./LICENSE).
