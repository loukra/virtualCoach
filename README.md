# Virtual Coach

A personal AI cycling coach. It imports rides from Strava, tracks fitness and fatigue with the
Banister model (CTL / ATL / TSB), lets an LLM build a periodized plan towards a race, and
prescribes each day's workout from the plan, the athlete's check-in and the last week of
training. Built for my own use (and a training partner), run on my own server.

```
mobile/    Expo / React Native app; talks only to the backend
backend/   FastAPI service: SQLite storage, Strava sync, training math, AI plan and workout generation
```

Each athlete gets a personal access token (`manage.py add-athlete`). The backend stores only
its hash and scopes every query to the token's athlete, so two people can share one server
without seeing each other's data. Everything lives in one SQLite file, so there is no
database service to run or to pay for.

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
   run against the real model. Beyond the guardrails they check coaching intent
   (`evals/checks.py`): does the main set match the planned session type, is the load right for
   the plan and the available time, does a 10-week plan start near current fitness, build and
   taper? Optionally a second model grades plan fit, safety and clarity (`--judge`; only in the
   evals, never in the app). `--runs N` repeats each scenario because answers vary; every run
   saves a JSON report with models and prompt versions and prints the change to the previous one.

Data minimization: ride names are not sent to the model, responses are not stored at OpenAI
(`store=False`), and the athlete's free text is passed as quoted data.

## Setup

### 1. Strava

Create an API application at <https://www.strava.com/settings/api>. Set the *Authorization
Callback Domain* to the host of the redirect URI the app uses (`virtualcoach://strava` in a
development build, `exp://<your-ip>:8081/--/strava` in Expo Go). A new Strava application
starts with room for a single connected athlete; for a second person, check the athlete
capacity on the API settings page and ask Strava to raise it.

### 2. Backend

```bash
cd backend
cp .env.example .env          # OpenAI key, Strava client id and secret
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn main:app --reload --host 0.0.0.0
```

The database (`data/coach.db`) and its tables are created on start. Then add the athletes;
each command prints a token once, which goes into the app's sign-in screen:

```bash
.venv/bin/python -m manage add-athlete "Louis"
.venv/bin/python -m manage list
.venv/bin/python -m manage new-token "Louis"   # lost or leaked token: the old one stops working
```

Production: `docker compose up -d --build` on the server, behind a reverse proxy with HTTPS
(for example Caddy: `coach.example.com { reverse_proxy 127.0.0.1:8000 }`), then
`docker compose exec backend python -m manage add-athlete "Louis"`. The database sits in the
`coach-data` volume; `docker-compose.yml` shows how to take a consistent backup.

### 3. App

```bash
cd mobile
cp .env.example .env          # backend URL, Strava client id (nothing secret)
npm install && npx expo start
```

Sign in with the token, fill in the profile, connect Strava, then create a journey.

## Tests and evals

```bash
cd backend
.venv/bin/ruff check . && .venv/bin/pytest -q     # offline, no API keys needed
.venv/bin/python -m evals.run_evals               # real model, needs OPENAI_API_KEY, a few cents
.venv/bin/python -m evals.run_evals --runs 3      # each scenario three times, with pass rates
.venv/bin/python -m evals.run_evals --plan --judge   # plus a 10-week plan and a judge model
```

CI runs lint and tests on every push and checks that the app bundles (catching import casing
errors that only show on Linux).

## API

All endpoints except `/` and `/health` require `Authorization: Bearer <athlete token>`;
the athlete is taken from the token, request bodies never carry an id.

| Method | Path | Purpose |
|---|---|---|
| GET | `/me` | profile, Strava and sync state |
| PUT | `/profile` | goal, FTP, max heart rate, weight |
| GET | `/metrics?days=90` | daily CTL / ATL / TSB |
| GET | `/journeys`, `/journeys/{id}` | goals and their plan status |
| GET | `/journeys/{id}/today` | today's planned day, check-in, workout and form |
| GET | `/journeys/{id}/calendar` | the whole plan plus the rides done in its range |
| DELETE | `/journeys/{id}` | hide a journey (data stays) |
| POST | `/connect-strava` | OAuth code from the app; token exchange and 90-day import in the background |
| POST | `/sync` | import new rides, recompute CTL/ATL/TSB |
| POST | `/check-in` | today's mood and leg scores |
| POST | `/create-journey` | create a goal and generate its plan in the background |
| POST | `/generate-workout` | today's workout (cached per day and duration; `force` regenerates) |
| GET | `/workouts/{journey_id}/{date}.zwo` | that day's workout as a Zwift file |

## Known limits

- Strava data reaches OpenAI. Strava's API agreement requires the user's explicit consent for
  sharing with third parties; both users here know and agree. Opening the app to more people
  would need a consent screen and a check of Strava's current AI terms first.
- Tokens are long-lived; revoke one with `manage.py new-token`.
- No Strava webhooks: the app syncs when it opens. Deauthorizing on Strava's side does not yet
  delete the imported data.
- Background jobs run inside the API process (FastAPI `BackgroundTasks`); a restart during plan
  generation leaves the journey in `creating`.
