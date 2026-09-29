# AI Smart Room

AI Smart Room is a two-week university IoT + AI project. An ESP32 reads room sensors and sends telemetry to a small backend. Phase 2 adds PostgreSQL persistence while keeping the existing telemetry API compatible with the ESP32.

## Architecture

```text
ESP32 Node32S + DHT11
        |
        | HTTP JSON telemetry
        v
FastAPI backend
        |
        +-- deterministic temperature recommendation
        +-- SQLAlchemy 2.x / Alembic
        v
    PostgreSQL
```

The backend exposes these endpoints:

- `GET /health` checks that the service is running.
- `POST /api/v1/readings` validates, classifies, and stores an ESP32 reading.
- `GET /api/v1/readings/latest` returns the newest persisted reading.
- `GET /api/v1/readings?limit=10` returns recent readings for future charts.

The `co2` field remains nullable for compatibility with readings that do not contain an SCD40 value. Later phases add the React dashboard and an optional Groq assessment.

## Local setup

From the project root, create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell, activate it with:

```powershell
.venv\Scripts\Activate.ps1
```

Install the backend dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

## Run the API

Start Uvicorn from the project root:

```bash
uvicorn backend.app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`. Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

## Example requests

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

Submit a reading:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/readings \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "smart-room-01",
    "temperature": 26.9,
    "humidity": 57.0,
    "co2": null,
    "fan_on": false
  }'
```

Get the latest reading:

```bash
curl http://127.0.0.1:8000/api/v1/readings/latest
```

Room status is resolved in the backend. A valid `status` sent by the ESP32 is authoritative, so the API and dashboard match the physical LED. Older clients may omit `status`; in that case the fallback is:

- `HOT` when CO2 is at least 1500 ppm, temperature is at least 30°C, or humidity is at least 85%
- otherwise `MODERATE` when CO2 is at least 1000 ppm, temperature is at least 28°C, or humidity is at least 70%
- otherwise `GOOD`

Recommendations are generated from the actual available measurements and identify the elevated environmental factors. A null CO2 value is ignored by fallback status resolution. No database migration is needed for this status-resolution update because `sensor_readings` already stores `status` and `recommendation`.

## Phase 2: PostgreSQL persistence

### PostgreSQL prerequisite

Install PostgreSQL on macOS with Homebrew, then start the service:

```bash
brew install postgresql
brew services start postgresql
```

Create the project database. If your local PostgreSQL user is different, use `createdb -U <your-postgres-user> ai_smart_room` instead:

```bash
createdb ai_smart_room
```

### Environment setup

Copy the example environment file and edit `DATABASE_URL` with your local PostgreSQL username and password. The `.env` file is ignored by Git:

```bash
cp .env.example .env
```

Example:

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:your_password@localhost:5432/ai_smart_room
```

Do not put real credentials in `.env.example` or commit `.env`.

### Install dependencies and run migrations

Activate the virtual environment and install the updated dependencies:

```bash
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
```

Run Alembic explicitly from the `backend` directory:

```bash
cd backend
alembic upgrade head
cd ..
```

The migration creates the `sensor_readings` table and its indexes. The application does not run migrations automatically at startup.

### Start FastAPI

From the project root:

```bash
uvicorn backend.app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

To verify database connectivity, run `alembic current` from `backend` after configuring `.env`, then submit a reading and request the latest row:

```bash
cd backend
alembic current
cd ..
curl http://127.0.0.1:8000/health
```

`/health` is intentionally a lightweight service check. The migration command and reading endpoints verify PostgreSQL connectivity.

### Phase 2 curl examples

Submit a reading:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/readings \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "smart-room-01",
    "temperature": 24.6,
    "humidity": 53.0,
    "co2": null,
    "fan_on": false
  }'
```

Get the latest persisted reading:

```bash
curl http://127.0.0.1:8000/api/v1/readings/latest
```

Get up to 10 persisted readings, newest first:

```bash
curl "http://127.0.0.1:8000/api/v1/readings?limit=10"
```

## Phase 3: Frontend dashboard

The Phase 3 frontend is a React + Vite + TypeScript dashboard. It uses Recharts for temperature, humidity, and CO₂ history charts and remains read-only: fan control still belongs to the physical button and ESP32 firmware.

### Frontend setup

Make sure Node.js and npm are installed, then install the frontend dependencies:

```bash
cd frontend
npm install
cp .env.example .env
```

The local environment file contains the backend URL used by the dashboard:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

No frontend secrets are required. Do not commit a real `.env` file.

### Start both applications

In one terminal, start PostgreSQL and the backend as described above, then run FastAPI from the project root:

```bash
source .venv/bin/activate
uvicorn backend.app.main:app --reload
```

In a second terminal, start the Vite development server:

```bash
cd frontend
npm run dev
```

The local URLs are:

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`

The dashboard requests the latest reading and up to 50 history items immediately on load, then polls both endpoints approximately every five seconds. A single cleaned-up interval is used, in-flight refreshes are not stacked, and a failed refresh leaves the last valid data visible with a connection warning. History is returned newest-first by the backend and copied into chronological order for chart display. Null CO₂ values remain null and are shown as `Waiting for sensor` rather than being replaced with a fabricated value.

## Backend AI environmental assessment

`POST /api/v1/ai/assessment` reads the latest 12 persisted readings for the requested device. The frontend only needs to send a device ID and at least one temporary sensitivity. The backend calculates recent averages and trends, then asks Groq for concise Thai guidance. The persisted status remains authoritative; the endpoint does not write readings, preferences, or fan state. No database migration is required.

Supported sensitivity values are `heat_sensitive`, `cold_sensitive`, `high_humidity_sensitive`, `dry_air_sensitive`, `poor_ventilation_sensitive`, and `respiratory_sensitive`. These describe environmental preferences and do not collect medical history. The API returns 422 for an empty or unsupported list, and 404 if the device has no persisted readings.

Example request:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/ai/assessment \
  -H "Content-Type: application/json" \
  -d '{"device_id":"smart-room-01","sensitivities":["heat_sensitive","poor_ventilation_sensitive"]}'
```

The response contains `success`, `source` (`groq` or `fallback`), `device_id`, `profile`, `environment` (`temperature`, `humidity`, nullable `co2`, `status`), `assessment` (`suitability`, `title`, `summary`, `reasons`, `recommendations`), and a Thai `disclaimer`. Suitability is one of `SUITABLE`, `CAUTION`, or `NOT_SUITABLE`; explanatory text is Thai. A missing key, timeout, provider error, or invalid output produces the same schema with `source: "fallback"`. The Groq request has a six-second timeout and no automatic retries.

The Thai assessment speaks directly to the user about the measured values and selected sensitivities, with practical suggestions. It does not present CO₂ as dust or PM, and does not use monitoring-system phrasing. Only CO₂, temperature, and humidity are measured.

Set these variables in the root `.env` (or the existing `backend/.env`) after copying `.env.example`:

```dotenv
GROQ_API_KEY=your_key_here
GROQ_MODEL=openai/gpt-oss-20b
```

`GROQ_API_KEY` is optional for local fallback testing. `GROQ_MODEL` defaults to `openai/gpt-oss-20b` when absent. Keep real credentials only in a gitignored `.env` or the deployment environment. Install backend dependencies with `python -m pip install -r backend/requirements.txt`. The compatible official Groq SDK version range supports the project's Python 3.9 environment.

Run the backend tests without a Groq key or network call:

```bash
python -m unittest discover -s backend/tests -v
```
