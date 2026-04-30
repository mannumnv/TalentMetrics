<<<<<<< HEAD
# TalentMetrics
=======
# TalentMetrics

Runnable starter project for the HR Analytics System.

## Structure

```text
backend/     FastAPI API, batch logic, SQLAlchemy models
frontend/    React dashboard shell
Makefile     One-command setup and run helpers
docker-compose.yml  Optional local PostgreSQL
```

## Quick Start

From the project root:

```bash
cd /Users/manmohankumar/Documents/TalentMetrics
make setup
```

Start the full app with one command:

```bash
make app
```

This starts both services in the same terminal:

```text
Backend:  http://localhost:8000/docs
Frontend: http://localhost:5173
```

Press `CTRL+C` to stop both.

If you ever want to run them separately, use:

```bash
make backend
make frontend
```

## Useful Commands

```bash
make help       # show all commands
make setup      # install backend and frontend dependencies
make app        # run backend and frontend together
make backend    # run FastAPI on port 8000
make frontend   # run React on port 5173
make batch      # import sample_engineers.csv
make health     # check backend health
make db-up      # optional: start PostgreSQL Docker
make db-down    # optional: stop PostgreSQL Docker
```

The default local setup uses SQLite:

```text
backend/talentmetrics.db
```

PostgreSQL is optional for local development.

## Sample API Flow

Create engineer:

```bash
curl -X POST http://localhost:8000/api/v1/engineers \
  -H "Content-Type: application/json" \
  -d '{
    "ite_number": "ITE-2026-0001",
    "full_name": "Rahul Sharma",
    "email": "rahul@example.com",
    "total_experience_months": 10,
    "current_status": "Training",
    "date_of_joining": "2026-04-01",
    "primary_skill": "Java"
  }'
```

Change status:

```bash
curl -X POST http://localhost:8000/api/v1/engineers/ITE-2026-0001/status \
  -H "Content-Type: application/json" \
  -d '{
    "to_status": "In Japan (Bench)",
    "effective_from": "2026-05-01",
    "reason": "Arrived in Japan"
  }'
```

Upload Excel or CSV:

```bash
curl -X POST http://localhost:8000/api/v1/uploads/engineers \
  -F "file=@/Users/manmohankumar/Downloads/List.csv"
```

Supported upload columns include:

```text
ITE Number / ITE番号
Full Name / 名前
Date of Joining / 入社日
Status / ステータス
Japan Arrival Date / 来日日
Primary Skill / スキル / オフィス
Contract Start Date / 契約開始日
Contract End Date / 契約終了日
```

## Batch Job

Run daily batch manually:

```bash
make batch
```

Cron at 06:00:

```cron
0 6 * * * cd /Users/manmohankumar/Documents/TalentMetrics && make batch
```
>>>>>>> 269fb36 (Initial commit)
