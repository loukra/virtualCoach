-- Virtual Coach schema. Reconstructed from the code, since the original project no longer exists.
--
-- Access model:
--   * The app (anon key + user session) only READS its own rows, enforced by Row Level Security.
--     The one exception: it may update its own profile during onboarding.
--   * The backend (service-role key) does all writes and bypasses RLS.
--   * Strava tokens are invisible to the app: RLS on, no policy, privileges revoked.

-- ---------------------------------------------------------------- profiles
create table public.profiles (
    id uuid primary key references auth.users (id) on delete cascade,
    goal text,
    ftp integer check (ftp between 50 and 600),
    weight_kg numeric(5, 1) check (weight_kg between 30 and 200),
    max_heart_rate integer check (max_heart_rate between 120 and 230),
    has_completed_onboarding boolean not null default false,
    strava_connected boolean not null default false,
    sync_status text not null default 'pending'
        check (sync_status in ('pending', 'syncing', 'completed', 'failed')),
    created_at timestamptz not null default now()
);

-- Every new account gets an empty profile row.
create function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
    insert into public.profiles (id) values (new.id);
    return new;
end;
$$;

create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------- strava
create table public.strava_connection (
    user_id uuid primary key references auth.users (id) on delete cascade,
    athlete_id bigint not null,
    access_token text not null,
    refresh_token text not null,
    expires_at bigint not null,
    updated_at timestamptz not null default now()
);

create table public.athlete_history (
    user_id uuid not null references auth.users (id) on delete cascade,
    valid_from date not null,
    ftp integer not null check (ftp between 50 and 600),
    primary key (user_id, valid_from)
);

create table public.activities (
    id bigint primary key, -- Strava activity id
    user_id uuid not null references auth.users (id) on delete cascade,
    start_date timestamptz not null,
    start_date_local timestamp not null, -- wall-clock time where the ride happened
    sport_type text,
    name text,
    duration_seconds integer,
    moving_time integer,
    tss integer,
    tss_source text check (tss_source in ('power', 'heart_rate', 'time')),
    average_watts numeric,
    weighted_average_watts integer,
    max_watts integer,
    variability_index numeric,
    average_heartrate numeric,
    max_heartrate integer,
    efficiency_factor numeric,
    elevation_gain integer,
    kilojoules numeric
);
create index activities_user_local_idx on public.activities (user_id, start_date_local);

create table public.daily_metrics (
    user_id uuid not null references auth.users (id) on delete cascade,
    date date not null,
    ctl numeric,
    atl numeric,
    tsb numeric,
    ramp_rate numeric,
    monotony numeric,
    strain numeric,
    primary key (user_id, date)
);

-- ---------------------------------------------------------------- plans
create table public.journeys (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    name text not null,
    start_date date not null,
    race_date date not null,
    status text not null default 'creating'
        check (status in ('creating', 'active', 'failed', 'archived')),
    error text,
    created_at timestamptz not null default now(),
    check (race_date >= start_date)
);
create index journeys_user_idx on public.journeys (user_id, created_at desc);

create table public.master_plan (
    id bigint generated always as identity primary key,
    journey_id uuid not null references public.journeys (id) on delete cascade,
    date date not null,
    day_number integer not null,
    phase text,
    planned_workout_type text not null,
    planned_duration_min integer not null default 0,
    planned_tss integer not null default 0,
    description text,
    unique (journey_id, date)
);

create table public.daily_checkins (
    id bigint generated always as identity primary key,
    user_id uuid not null references auth.users (id) on delete cascade,
    date date not null,
    feel_score smallint not null check (feel_score between 1 and 5),
    soreness_score smallint not null check (soreness_score between 1 and 5),
    notes text,
    unique (user_id, date)
);

create table public.daily_prescriptions (
    id bigint generated always as identity primary key,
    user_id uuid not null references auth.users (id) on delete cascade,
    journey_id uuid not null references public.journeys (id) on delete cascade,
    date date not null,
    workout_text text not null, -- markdown rendered by the backend
    workout_json jsonb, -- structured workout (logic.schemas.Workout), source of the .zwo export
    duration_min integer,
    estimated_tss integer,
    recovery_reason text, -- set when a hard rule forced a recovery session
    created_at timestamptz not null default now(),
    unique (journey_id, date)
);

-- ---------------------------------------------------------------- AI observability
create table public.ai_generations (
    id bigint generated always as identity primary key,
    user_id uuid references auth.users (id) on delete cascade,
    journey_id uuid references public.journeys (id) on delete set null,
    kind text not null, -- plan_macro | plan_block | workout
    model text not null,
    prompt_version text not null, -- prompt file name + content hash
    attempt integer not null,
    ok boolean not null,
    errors jsonb not null default '[]',
    latency_ms integer,
    input_tokens integer,
    output_tokens integer,
    created_at timestamptz not null default now()
);
create index ai_generations_created_idx on public.ai_generations (created_at desc);

-- ---------------------------------------------------------------- row level security
alter table public.profiles enable row level security;
alter table public.strava_connection enable row level security;
alter table public.athlete_history enable row level security;
alter table public.activities enable row level security;
alter table public.daily_metrics enable row level security;
alter table public.journeys enable row level security;
alter table public.master_plan enable row level security;
alter table public.daily_checkins enable row level security;
alter table public.daily_prescriptions enable row level security;
alter table public.ai_generations enable row level security;

revoke all on public.strava_connection from anon, authenticated;
-- The app may only fill in the onboarding answers; status fields belong to the backend.
revoke update on public.profiles from anon, authenticated;
grant update (goal, ftp, weight_kg, max_heart_rate, has_completed_onboarding)
    on public.profiles to authenticated;

create policy "own profile: read" on public.profiles
    for select to authenticated using ((select auth.uid()) = id);
create policy "own profile: onboarding update" on public.profiles
    for update to authenticated using ((select auth.uid()) = id) with check ((select auth.uid()) = id);

create policy "own rows: read" on public.athlete_history
    for select to authenticated using ((select auth.uid()) = user_id);
create policy "own rows: read" on public.activities
    for select to authenticated using ((select auth.uid()) = user_id);
create policy "own rows: read" on public.daily_metrics
    for select to authenticated using ((select auth.uid()) = user_id);
create policy "own rows: read" on public.journeys
    for select to authenticated using ((select auth.uid()) = user_id);
create policy "own rows: read" on public.daily_checkins
    for select to authenticated using ((select auth.uid()) = user_id);
create policy "own rows: read" on public.daily_prescriptions
    for select to authenticated using ((select auth.uid()) = user_id);
create policy "own rows: read" on public.ai_generations
    for select to authenticated using ((select auth.uid()) = user_id);

create policy "own journeys: read plan" on public.master_plan
    for select to authenticated using (
        exists (
            select 1 from public.journeys j
            where j.id = master_plan.journey_id and j.user_id = (select auth.uid())
        )
    );
