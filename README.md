# BankingDB — Docker Compose Deployment

## Project structure

```
bankingdb/
├── docker-compose.yml      # PostgreSQL 16 + pgAdmin services
├── deploy_bankingdb.py     # Deploy script (schema + seed)
├── pgadmin_servers.json    # pgAdmin auto-configured server entry
└── init/                   # (optional) place *.sql files here for
                            #  auto-execution on first container start
```

## Quick start

```bash
pip install psycopg2-binary
python deploy_bankingdb.py
```

## CLI flags

| Command | Action |
|---------|--------|
| `python deploy_bankingdb.py`            | Full deploy: compose up + schema + seed |
| `python deploy_bankingdb.py --reset`    | Wipe volumes + redeploy from scratch    |
| `python deploy_bankingdb.py --stop`     | docker compose down (keeps data)        |
| `python deploy_bankingdb.py --stop --volumes` | docker compose down -v (deletes data) |
| `python deploy_bankingdb.py --schema-only`    | Skip compose; re-run schema + seed on existing container |

## Connection details

| Setting  | Value |
|----------|-------|
| Host     | localhost |
| Port     | 5433 |
| Database | bankingdb |
| User     | bankadmin |
| Password | BankDB$ecure123 |

psql: `psql -h localhost -p 5433 -U bankadmin bankingdb`

## pgAdmin

Open http://localhost:5050 — login: `admin@example.com` / `admin`
The BankingDB server is pre-configured; enter the password `BankDB$ecure123` when prompted.
