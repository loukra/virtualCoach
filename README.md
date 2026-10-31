# Virtual Coach

A personal AI cycling coach. It imports rides from Strava, tracks fitness and fatigue with the
Banister model (CTL / ATL / TSB), lets an LLM build a periodized plan (towards a race, or a
block of weeks to raise fitness, e.g. a winter on Zwift), and prescribes each day's workout from
the plan, the athlete's check-ins and the last week of training. Workouts go to Zwift as `.zwo`
files through the iPhone share sheet (AirDrop to the Mac). Built for my own use (and a training
partner), run on my own server.

## Training model

- **Two goals.** *Race*: base, build, peak, taper to an event date. *Build fitness*: N weeks of
  progressive load with recovery weeks and no race.
- **Flexible weeks** (`logic/sessions.py`). A plan week is a set of sessions, each with a
  suggested day. Whatever you ride completes the open session of that week that fits it best
  (a hard ride the quality session, a long ride the long ride, an easy one the easy day), on any
  day of the week. Missed sessions are not carried into the next week.
- **What to ride today** is chosen in code: today's session if it suits you, otherwise a key
  session that is overdue, never an intense one the day after a hard ride, a rest day only when
  the week still has room for the open sessions. You can always pick another session.
- **Check in any time** (energy, legs, motivation, a note). Low energy or legs force recovery;
  several low check-ins in a row, legs heavy for days or a load spike (ATL far above CTL) rule
  out hard sessions or force recovery before a single check-in would show it.
- **FTP tests** (`logic/ftp.py`) are placed by code (week 1, then every five weeks; a fitness
  block also ends with one; none in a race taper) and always ridden the same way: warmup, three
  openers, 20 minutes all out in free-ride mode (ERG off). The best 20-minute power of each ride
  is computed from the power stream; after a test the app suggests the new FTP (0.95 × 20-min
  power), and a ride that beats the current FTP clearly suggests raising it even without a test.

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
4. **Hard rules before the model.** Low mood, sore legs, very negative form or a run of low
   check-ins force a recovery session (`logic/sessions.py`); the model is told so and the
   guardrails enforce it. Which session is ridden today and the FTP test itself are decided in
   code, never by the model.
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
   the plan and the available time, does a 10-week race plan start near current fitness, build
   and taper, does a 12-week fitness plan keep its FTP tests, two quality sessions in most
   build weeks and a load that keeps growing? Optionally a second model grades plan fit, safety and clarity (`--judge`; only in the
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
.venv/bin/python -m evals.run_evals --plan --judge   # plus a race and a fitness plan, and a judge
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
| GET | `/ftp` | FTP history, FTP test results, suggested new FTP |
| PUT | `/ftp` | take over a new FTP (or confirm the old one, which dismisses the suggestion) |
| GET | `/journeys`, `/journeys/{id}` | goals and their plan status |
| GET | `/journeys/{id}/today` | today's suggested session and why, this week's sessions and state, check-in, warning signs, workout, form, FTP suggestion |
| GET | `/journeys/{id}/calendar` | the whole plan with each session's state, plus the rides in its range |
| DELETE | `/journeys/{id}` | hide a journey (data stays) |
| POST | `/connect-strava` | OAuth code from the app; token exchange and 90-day import in the background |
| POST | `/sync` | import new rides, recompute CTL/ATL/TSB |
| POST | `/check-in` | energy, legs, motivation, note (again later the same day replaces it) |
| POST | `/create-journey` | `goal_type` race (with `race_date`) or build (with `weeks`); plan generated in the background |
| POST | `/generate-workout` | today's workout for `plan_id` (default: the suggested session); cached per day, session and duration; `force` regenerates |
| GET | `/workouts/{journey_id}/{date}.zwo` | that day's workout as a Zwift file, named after the workout |

## Zwift

In the app, *Send to Zwift (.zwo)* opens the share sheet: AirDrop the file to the Mac, then move
it into `Documents/Zwift/Workouts/<your Zwift ID>/` (the folder with the number). Zwift lists it
under *Custom Workouts* the next time it starts. A ride on a day the app prescribed a workout
completes that workout's session. Otherwise a ride with "FTP" in its name (Zwift usually puts the
workout's name into the activity name) completes the plan's FTP test.

## Known limits

- Strava data reaches OpenAI. Strava's API agreement requires the user's explicit consent for
  sharing with third parties; both users here know and agree. Opening the app to more people
  would need a consent screen and a check of Strava's current AI terms first.
- Tokens are long-lived; revoke one with `manage.py new-token`.
- No Strava webhooks: the app syncs when it opens. Deauthorizing on Strava's side does not yet
  delete the imported data.
- Rides imported before the update have no 20-minute power; FTP suggestions start with new rides.
- Background jobs run inside the API process (FastAPI `BackgroundTasks`); a restart during plan
  generation leaves the journey in `creating`.
