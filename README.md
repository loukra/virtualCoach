# Virtual Coach

A personal AI cycling coach. It imports rides from Strava, tracks fitness and fatigue with the
Banister model (CTL / ATL / TSB), lets an LLM build a periodized plan towards a race, and
prescribes each day's workout from the plan, the athlete's check-in and the last week of
training. Built for one athlete (me), run on my own server.

```
mobile/    Expo / React Native app (Supabase auth, reads its data directly via RLS)
backend/   FastAPI service: Strava sync, training math, AI plan and workout generation
supabase/  Database schema and Row Level Security as a migration
```

## How the AI part works

The model never produces anything the app uses unchecked.

1. **Structured outputs.** Plans and workouts are Pydantic schemas (`logic/schemas.py`) filled
   via OpenAI Structured Outputs, not free text that gets parsed.
2. **Deterministic guardrails** (`logic/guardrails.py`). Every answer is checked in code: weekly
   load ramp, recovery weeks, taper, rest days, physically possible TSS, workout length within
   the available time, power targets as fractions of FTP, sustainable efforts, heart-rate caps.
3. **Repair loop** (`logic/ai.py`). Violations go back to the model as a precise list; after
   `AI_MAX_ATTEMPTS` the generation fails visibly instead of storing a bad plan.
4. **Hard rules before the model.** Low mood, sore legs or very negative form force a recovery
   session (`logic/coach.py`); the model is told so and the guardrails enforce it.
5. **Staged plan generation** (`logic/ai_planner.py`). One call for the weekly structure, then
   the days in four-week blocks checked against the weekly targets, so long plans never hit the
   output limit.
6. **Numbers from code.** Watts, duration, TSS and the Zwift `.zwo` export are computed from the
   structured workout (`logic/workout_math.py`), not written by the model.
7. **Observability.** Every attempt lands in `ai_generations`: model, prompt version (file name
   plus content hash), tokens, latency, violations.
8. **Evals** (`backend/evals`). Fixed athlete scenarios, including a prompt-injection attempt,
   run against the real model; the report shows pass rate and first-answer validity.

Data minimization: ride names are not sent to the model, responses are not stored at OpenAI
(`store=False`), and the athlete's free text is passed as quoted data.

## Setup

### 1. Supabase

1. Create a project, then apply the schema: `supabase db push` with the Supabase CLI, or paste
   `supabase/migrations/*.sql` into the SQL editor.
2. Create your account (sign up once in the app or in the dashboard), then **disable sign-ups**
   (Authentication > Sign In / Providers) and put your user id into `ALLOWED_USER_IDS`.

### 2. Strava

Create an API application at <https://www.strava.com/settings/api>. New applications are limited
to one connected athlete, which is exactly this use case. Set the *Authorization Callback Domain*
to the host of the redirect URI the app uses (`virtualcoach://strava` in a development build,
`exp://<your-ip>:8081/--/strava` in Expo Go).

### 3. Backend

```bash
cd backend
cp .env.example .env          # fill in
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn main:app --reload --host 0.0.0.0
```

Production: `docker compose up -d --build` on the server, behind a reverse proxy with HTTPS
(for example Caddy: `coach.example.com { reverse_proxy 127.0.0.1:8000 }`).

### 4. App

```bash
cd mobile
cp .env.example .env          # backend URL, Supabase URL + anon key, Strava client id
npm install && npx expo start
```

## Tests and evals

```bash
cd backend
.venv/bin/ruff check . && .venv/bin/pytest -q     # offline, no API keys needed
.venv/bin/python -m evals.run_evals               # real model, needs OPENAI_API_KEY, a few cents
.venv/bin/python -m evals.run_evals --plan        # plus a 10-week plan
```

CI runs lint and tests on every push and checks that the app bundles (catching import casing
errors that only show on Linux).

## API

All endpoints except `/` and `/health` require `Authorization: Bearer <Supabase access token>`;
the user is taken from the token.

| Method | Path | Purpose |
|---|---|---|
| POST | `/connect-strava` | OAuth code from the app; token exchange and 90-day import in the background |
| POST | `/sync` | import new rides, recompute CTL/ATL/TSB |
| POST | `/check-in` | today's mood and leg scores |
| POST | `/create-journey` | create a goal and generate its plan in the background |
| POST | `/generate-workout` | today's workout (cached per day and duration; `force` regenerates) |
| GET | `/workouts/{journey_id}/{date}.zwo` | that day's workout as a Zwift file |

## Known limits

- Strava data reaches OpenAI. Strava's API agreement requires the user's explicit consent for
  sharing with third parties; as the only user, I consent. Opening the app to others would need
  a consent screen and a check of Strava's current AI terms first.
- No Strava webhooks: the app syncs when it opens. Deauthorizing on Strava's side does not yet
  delete the imported data.
- Background jobs run inside the API process (FastAPI `BackgroundTasks`); a restart during plan
  generation leaves the journey in `creating`.
