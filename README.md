# Flask API stack on Docker Compose

A REST API built with Flask and PostgreSQL, served behind an nginx reverse proxy,
packaged with a multi-stage Docker build and validated by GitHub Actions.

## Stack

| Layer    | Technology          |
| -------- | ------------------- |
| App      | Python 3.12 / Flask |
| Database | PostgreSQL 16       |
| Proxy    | nginx 1.27-alpine   |
| Runtime  | Docker + Compose    |
| CI       | GitHub Actions      |

## Architecture

```
curl / browser
      │
      ▼
  nginx :8080        ← the only port published to the host
      │
      ▼
  Flask app :5000    ← non-root (uid 1001), not published
      │
      ▼
  PostgreSQL :5432   ← internal network only, data in a named volume
```

Only nginx is reachable from outside. The application and the database have no
`ports` section at all — they communicate over the Compose network using service
names as DNS records.

## Quick start

```bash
cp .env.example .env      # set POSTGRES_PASSWORD
docker compose up -d
docker compose ps         # wait for services to become healthy
```

Verify:

```bash
curl localhost:8080/health

curl -X POST localhost:8080/api/items \
     -H "Content-Type: application/json" \
     -d '{"name": "buy coffee"}'

curl localhost:8080/api/items
curl -X PATCH localhost:8080/api/items/1
```

## API reference

| Method | Path             | Description                    |
| ------ | ---------------- | ------------------------------ |
| GET    | `/health`        | Liveness — process is running  |
| GET    | `/ready`         | Readiness — database reachable |
| GET    | `/api/items`     | List all items                 |
| POST   | `/api/items`     | Create an item `{name}`        |
| PATCH  | `/api/items/:id` | Toggle the `done` flag         |

## Design decisions

### Multi-stage build

The `builder` stage carries `gcc` and `libpq-dev` to compile C extensions; the
`runtime` stage receives only the installed packages and keeps `libpq5`.

This brings the final image to 218 MB, compared to 494 MB for the builder stage
and 1.63 GB for the initial version based on `python:latest`. A smaller image
means faster pulls on deploy and fewer packages showing up in vulnerability scans.

### Layer ordering

`COPY requirements.txt` is a separate step placed before `COPY . .` so that
editing application code does not invalidate the dependency layer. Without this
split, `pip install` re-runs on every single build.

### Non-root runtime user

The process runs as `appuser` with an explicit uid of 1001. The uid is pinned
rather than auto-assigned so that file ownership stays predictable when volumes
are mounted.

### Liveness and readiness are separate

`/health` does not touch the database; `/ready` does. Checking the database in a
liveness probe would cause an orchestrator to restart perfectly healthy
containers whenever the database is briefly unavailable — restarts that cannot
fix the underlying problem.

### Secrets via environment variables

`.env` is gitignored and only `.env.example` is committed. The password uses
`${POSTGRES_PASSWORD:?required}` rather than a default value: if the variable is
missing, the stack refuses to start instead of silently coming up with a weak
password.

### Dependencies wait for readiness, not just for start

`depends_on` uses `condition: service_healthy` instead of a plain service list.
The application additionally retries its initial connection, because a passing
healthcheck means Postgres accepts connections — not that it is fully ready to
serve the application's queries.

### nginx as the single entry point

Flask's built-in server is single-threaded and not intended for production use.
nginx also provides the place where TLS termination, rate limiting and load
balancing across replicas will live. The `X-Real-IP` and `X-Forwarded-For`
headers are forwarded so the application logs the actual client address rather
than the proxy's.

## CI

| Workflow       | Trigger            | Jobs                                              |
| -------------- | ------------------ | ------------------------------------------------- |
| `ci.yml`       | push / PR to main  | compose validation, image build, smoke test       |
| `security.yml` | push + weekly cron | Trivy image scan, SARIF upload to Security tab    |

Trivy matches package versions inside the image against public CVE databases.
Results are uploaded as SARIF rather than printed to the log, which lets GitHub
display findings in the Security tab with history and the ability to dismiss
false positives. The weekly schedule matters because new vulnerabilities are
disclosed against images that have not changed.

## Troubleshooting

```bash
docker compose ps -a                  # include stopped containers
docker compose logs -f app            # follow application logs
docker compose exec app sh            # shell into a running container
docker inspect <id> --format '{{.State.ExitCode}} {{.State.OOMKilled}}'
```

Common exit codes: `137` killed by the OOM killer, `127` command not found,
`126` file found but not executable.

## Local development

```bash
docker compose up -d --build          # rebuild after code changes
docker compose down                   # stop, keep the database volume
docker compose down -v                # stop and delete all data
```

## License

MIT
