-- =====================================================================
-- Reclaim – database schema (Supabase PostgreSQL)
--
-- Run this file FIRST in the Supabase SQL Editor, then rls_policies.sql.
-- It is safe to re-run: every statement is idempotent.
--
-- Conventions
--   * UUID primary keys (gen_random_uuid()).
--   * Every user-owned table has user_id -> auth.users(id) ON DELETE CASCADE,
--     so deleting an account removes all of that person's data.
--   * All timestamps are timestamptz (stored in UTC, converted to the user's
--     timezone in the app).
--   * "Not tracked" is represented by the ABSENCE of an hourly_logs row.
--     Nothing in the database ever creates a "success" hour automatically.
-- =====================================================================

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------
-- Helper: keep updated_at current
-- ---------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------
-- 1. profiles – one row per auth user
-- ---------------------------------------------------------------------
create table if not exists public.profiles (
  id                      uuid primary key references auth.users(id) on delete cascade,
  display_name            text not null default '' check (char_length(display_name) <= 80),
  age                     smallint check (age between 13 and 120),
  timezone                text not null default 'UTC' check (char_length(timezone) <= 64),
  addiction_type          text check (addiction_type in ('smoking', 'alcohol', 'both')),
  why_quit                text check (char_length(why_quit) <= 2000),
  aspirations             text check (char_length(aspirations) <= 2000),
  motivators              text check (char_length(motivators) <= 2000),
  -- Hourly tracking window in local time: slots run from wake_hour to sleep_hour (exclusive).
  wake_hour               smallint not null default 7  check (wake_hour between 0 and 23),
  sleep_hour              smallint not null default 23 check (sleep_hour between 1 and 24),
  currency_symbol         text not null default '₹' check (char_length(currency_symbol) between 1 and 5),
  standard_drink_region   text not null default 'WHO' check (standard_drink_region in ('WHO', 'IN', 'US', 'UK', 'AU', 'CA', 'EU')),
  volume_unit             text not null default 'ml' check (volume_unit in ('ml', 'oz')),
  share_journal_with_ai   boolean not null default false,
  trusted_contact_name    text check (char_length(trusted_contact_name) <= 80),
  trusted_contact_phone   text check (trusted_contact_phone ~ '^[0-9+() -]{3,30}$'),
  onboarding_completed_at timestamptz,
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now(),
  constraint profiles_tracking_window check (sleep_hour > wake_hour)
);

-- ---------------------------------------------------------------------
-- 2. addiction_profiles – baseline + settings per addiction (max 1 each)
-- ---------------------------------------------------------------------
create table if not exists public.addiction_profiles (
  id                     uuid primary key default gen_random_uuid(),
  user_id                uuid not null references auth.users(id) on delete cascade,
  addiction_type         text not null check (addiction_type in ('smoking', 'alcohol')),
  is_active              boolean not null default true,
  tracking_start_date    date not null default current_date,
  quit_date              date,
  -- smoking baseline
  baseline_per_day       numeric(6,2) check (baseline_per_day between 0 and 200),
  cost_per_unit          numeric(10,2) check (cost_per_unit >= 0),
  -- alcohol baseline
  drinking_frequency     text check (drinking_frequency in ('daily', 'most_days', 'few_per_week', 'weekly', 'occasionally')),
  drinking_days_per_week numeric(3,1) check (drinking_days_per_week between 0 and 7),
  drinks_per_occasion    numeric(5,1) check (drinks_per_occasion between 0 and 100),
  beverage_type          text check (char_length(beverage_type) <= 40),
  spend_per_occasion     numeric(10,2) check (spend_per_occasion >= 0),
  -- safety screening result (alcohol): possible physical dependence
  dependence_risk        boolean not null default false,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),
  constraint addiction_profiles_one_per_type unique (user_id, addiction_type)
);

-- ---------------------------------------------------------------------
-- 3. recovery_goals
-- ---------------------------------------------------------------------
create table if not exists public.recovery_goals (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  addiction_type  text check (addiction_type in ('smoking', 'alcohol')),
  goal_type       text not null check (goal_type in ('quit', 'reduce', 'custom')),
  title           text not null check (char_length(title) between 1 and 200),
  target_per_day  numeric(6,2) check (target_per_day >= 0),
  target_date     date,
  is_active       boolean not null default true,
  achieved_at     timestamptz,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- 4. hourly_logs – THE core table. One row per tracked hour.
--    Absence of a row = "not tracked". Never auto-filled.
-- ---------------------------------------------------------------------
create table if not exists public.hourly_logs (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  addiction_type  text not null check (addiction_type in ('smoking', 'alcohol')),
  slot_start      timestamptz not null,
  slot_end        timestamptz not null,
  status          text not null check (status in ('success', 'craving_resisted', 'consumed')),
  notes           text check (char_length(notes) <= 1000),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint hourly_logs_one_hour check (slot_end = slot_start + interval '1 hour'),
  -- local hours start on a :00, :15, :30 or :45 UTC boundary depending on timezone offset
  constraint hourly_logs_aligned check (
    date_trunc('minute', slot_start) = slot_start
    and extract(minute from slot_start)::int % 15 = 0
  ),
  constraint hourly_logs_unique_slot unique (user_id, addiction_type, slot_start)
);

-- ---------------------------------------------------------------------
-- 5. consumption_logs – individual smoking / drinking events
--    (stored separately from hourly statuses)
-- ---------------------------------------------------------------------
create table if not exists public.consumption_logs (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  addiction_type  text not null check (addiction_type in ('smoking', 'alcohol')),
  occurred_at     timestamptz not null,
  quantity        numeric(6,2) not null check (quantity > 0 and quantity <= 200),
  -- alcohol-specific (null for smoking)
  beverage_type   text check (char_length(beverage_type) <= 40),
  volume_ml       numeric(7,1) check (volume_ml > 0 and volume_ml <= 5000),
  abv_percent     numeric(4,1) check (abv_percent >= 0 and abv_percent <= 100),
  standard_drinks numeric(6,2) check (standard_drinks >= 0),
  occasion        text check (char_length(occasion) <= 60),
  -- shared
  cost            numeric(10,2) check (cost >= 0),
  trigger         text check (char_length(trigger) <= 60),
  mood            text check (char_length(mood) <= 30),
  location        text check (char_length(location) <= 120),
  notes           text check (char_length(notes) <= 1000),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- 6. craving_logs
-- ---------------------------------------------------------------------
create table if not exists public.craving_logs (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references auth.users(id) on delete cascade,
  addiction_type   text not null check (addiction_type in ('smoking', 'alcohol')),
  occurred_at      timestamptz not null default now(),
  intensity        smallint not null check (intensity between 1 and 10),
  trigger          text check (char_length(trigger) <= 60),
  mood             text check (char_length(mood) <= 30),
  location         text check (char_length(location) <= 120),
  resisted         boolean not null,
  coping_strategy  text check (char_length(coping_strategy) <= 60),
  notes            text check (char_length(notes) <= 1000),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- 7. daily_logs – one wellbeing check-in per local date
-- ---------------------------------------------------------------------
create table if not exists public.daily_logs (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references auth.users(id) on delete cascade,
  log_date         date not null,
  mood             text check (char_length(mood) <= 30),
  sleep_hours      numeric(3,1) check (sleep_hours between 0 and 24),
  sleep_quality    smallint check (sleep_quality between 1 and 5),
  exercise_minutes smallint check (exercise_minutes between 0 and 1440),
  water_glasses    smallint check (water_glasses between 0 and 50),
  reflection       text check (char_length(reflection) <= 2000),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  constraint daily_logs_one_per_day unique (user_id, log_date)
);

-- ---------------------------------------------------------------------
-- 8. journal_entries – private, one per local date
-- ---------------------------------------------------------------------
create table if not exists public.journal_entries (
  id                    uuid primary key default gen_random_uuid(),
  user_id               uuid not null references auth.users(id) on delete cascade,
  entry_date            date not null,
  mood                  text check (char_length(mood) <= 30),
  day_summary           text check (char_length(day_summary) <= 5000),
  difficult_situations  text check (char_length(difficult_situations) <= 5000),
  went_well             text check (char_length(went_well) <= 5000),
  craving_strength      smallint check (craving_strength between 0 and 10),
  lessons               text check (char_length(lessons) <= 5000),
  tomorrow_focus        text check (char_length(tomorrow_focus) <= 5000),
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),
  constraint journal_entries_one_per_day unique (user_id, entry_date)
);

-- ---------------------------------------------------------------------
-- 9. achievements – shared catalogue (read-only for users)
-- ---------------------------------------------------------------------
create table if not exists public.achievements (
  id              uuid primary key default gen_random_uuid(),
  code            text not null unique,
  title           text not null,
  description     text not null,
  category        text not null check (category in ('milestone', 'craving', 'consistency', 'progress')),
  addiction_type  text check (addiction_type in ('smoking', 'alcohol')),
  threshold       numeric not null default 0,
  icon            text not null default '🏅',
  sort_order      int not null default 0,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- 10. user_achievements – unlocked achievements (kept forever, even after relapse)
-- ---------------------------------------------------------------------
create table if not exists public.user_achievements (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  achievement_id  uuid not null references public.achievements(id) on delete cascade,
  unlocked_at     timestamptz not null default now(),
  seen            boolean not null default false,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint user_achievements_once unique (user_id, achievement_id)
);

-- ---------------------------------------------------------------------
-- 11. savings_goals
-- ---------------------------------------------------------------------
create table if not exists public.savings_goals (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  title           text not null check (char_length(title) between 1 and 100),
  target_amount   numeric(12,2) not null check (target_amount > 0),
  icon            text not null default '🎯' check (char_length(icon) <= 8),
  is_completed    boolean not null default false,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- 12. notification_preferences – one row per user
-- ---------------------------------------------------------------------
create table if not exists public.notification_preferences (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null unique references auth.users(id) on delete cascade,
  hourly_reminder     boolean not null default true,
  morning_checkin     boolean not null default true,
  morning_time        time not null default '08:00',
  evening_reflection  boolean not null default true,
  evening_time        time not null default '21:00',
  daily_motivation    boolean not null default true,
  weekly_report       boolean not null default true,
  milestone_alerts    boolean not null default true,
  email_enabled       boolean not null default false,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- 13. ai_conversations / 14. ai_messages
-- ---------------------------------------------------------------------
create table if not exists public.ai_conversations (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  title       text not null default 'New conversation' check (char_length(title) <= 120),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table if not exists public.ai_messages (
  id               uuid primary key default gen_random_uuid(),
  conversation_id  uuid not null references public.ai_conversations(id) on delete cascade,
  user_id          uuid not null references auth.users(id) on delete cascade,
  role             text not null check (role in ('user', 'assistant')),
  content          text not null check (char_length(content) <= 20000),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- Upgrades for databases created by an earlier version of this file.
-- (CREATE TABLE IF NOT EXISTS never adds new columns to an existing table.)
-- ---------------------------------------------------------------------
-- Phase 2: trusted contact shortcut on the Craving Manager
alter table public.profiles add column if not exists trusted_contact_name text
  check (char_length(trusted_contact_name) <= 80);
alter table public.profiles add column if not exists trusted_contact_phone text
  check (trusted_contact_phone ~ '^[0-9+() -]{3,30}$');

-- ---------------------------------------------------------------------
-- Indexes (unique constraints above already create their own indexes)
-- ---------------------------------------------------------------------
create index if not exists idx_addiction_profiles_user   on public.addiction_profiles (user_id);
create index if not exists idx_recovery_goals_user       on public.recovery_goals (user_id, is_active);
create index if not exists idx_hourly_logs_user_time     on public.hourly_logs (user_id, slot_start);
create index if not exists idx_consumption_user_time     on public.consumption_logs (user_id, addiction_type, occurred_at desc);
create index if not exists idx_craving_user_time         on public.craving_logs (user_id, addiction_type, occurred_at desc);
create index if not exists idx_user_achievements_user    on public.user_achievements (user_id);
create index if not exists idx_savings_goals_user        on public.savings_goals (user_id);
create index if not exists idx_ai_conversations_user     on public.ai_conversations (user_id, updated_at desc);
create index if not exists idx_ai_messages_conversation  on public.ai_messages (conversation_id, created_at);
create index if not exists idx_ai_messages_user          on public.ai_messages (user_id);

-- ---------------------------------------------------------------------
-- updated_at triggers
-- ---------------------------------------------------------------------
do $$
declare
  t text;
begin
  foreach t in array array[
    'profiles', 'addiction_profiles', 'recovery_goals', 'hourly_logs',
    'consumption_logs', 'craving_logs', 'daily_logs', 'journal_entries',
    'achievements', 'user_achievements', 'savings_goals',
    'notification_preferences', 'ai_conversations', 'ai_messages'
  ]
  loop
    execute format('drop trigger if exists trg_%1$s_updated_at on public.%1$I', t);
    execute format(
      'create trigger trg_%1$s_updated_at before update on public.%1$I
         for each row execute function public.set_updated_at()', t);
  end loop;
end;
$$;

-- ---------------------------------------------------------------------
-- New-user bootstrap: create an empty profile + notification prefs
-- whenever someone signs up through Supabase Auth.
-- ---------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id) values (new.id) on conflict (id) do nothing;
  insert into public.notification_preferences (user_id) values (new.id) on conflict (user_id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------
-- Self-service account deletion.
-- Runs with definer rights so the app never needs the service-role key,
-- but it can only ever delete the CALLER's own auth user (auth.uid()).
-- All user data is removed through ON DELETE CASCADE.
-- ---------------------------------------------------------------------
create or replace function public.delete_my_account()
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  uid uuid := auth.uid();
begin
  if uid is null then
    raise exception 'Not authenticated';
  end if;
  delete from auth.users where id = uid;
end;
$$;

revoke all on function public.delete_my_account() from public;
revoke all on function public.delete_my_account() from anon;
grant execute on function public.delete_my_account() to authenticated;

-- ---------------------------------------------------------------------
-- Achievement catalogue (seed data – not user data)
-- ---------------------------------------------------------------------
insert into public.achievements (code, title, description, category, addiction_type, threshold, icon, sort_order) values
  ('smoke_free_1h',    'First smoke-free hour',  'You tracked your first smoke-free hour.',            'milestone', 'smoking', 1,    '🌱', 10),
  ('smoke_free_24h',   '24 hours smoke-free',    'A full day without smoking.',                        'milestone', 'smoking', 24,   '🌤️', 11),
  ('smoke_free_3d',    '3 days smoke-free',      'Three days without smoking.',                        'milestone', 'smoking', 72,   '🌿', 12),
  ('smoke_free_7d',    '1 week smoke-free',      'A whole week without smoking.',                      'milestone', 'smoking', 168,  '🍃', 13),
  ('smoke_free_14d',   '2 weeks smoke-free',     'Two weeks without smoking.',                         'milestone', 'smoking', 336,  '🌳', 14),
  ('smoke_free_30d',   '30 days smoke-free',     'One month without smoking.',                         'milestone', 'smoking', 720,  '🏔️', 15),
  ('smoke_free_60d',   '60 days smoke-free',     'Two months without smoking.',                        'milestone', 'smoking', 1440, '⛰️', 16),
  ('smoke_free_90d',   '90 days smoke-free',     'Three months without smoking.',                      'milestone', 'smoking', 2160, '🌄', 17),
  ('smoke_free_180d',  '180 days smoke-free',    'Six months without smoking.',                        'milestone', 'smoking', 4320, '🌅', 18),
  ('smoke_free_365d',  '1 year smoke-free',      'A full year without smoking.',                       'milestone', 'smoking', 8760, '🏆', 19),
  ('alcohol_free_1d',  'First alcohol-free day', 'Your first full alcohol-free day.',                  'milestone', 'alcohol', 24,   '🌱', 30),
  ('alcohol_free_3d',  '3 days alcohol-free',    'Three days without alcohol.',                        'milestone', 'alcohol', 72,   '🌿', 31),
  ('alcohol_free_7d',  '1 week alcohol-free',    'A whole week without alcohol.',                      'milestone', 'alcohol', 168,  '🍃', 32),
  ('alcohol_free_14d', '2 weeks alcohol-free',   'Two weeks without alcohol.',                         'milestone', 'alcohol', 336,  '🌳', 33),
  ('alcohol_free_30d', '30 days alcohol-free',   'One month without alcohol.',                         'milestone', 'alcohol', 720,  '🏔️', 34),
  ('alcohol_free_60d', '60 days alcohol-free',   'Two months without alcohol.',                        'milestone', 'alcohol', 1440, '⛰️', 35),
  ('alcohol_free_90d', '90 days alcohol-free',   'Three months without alcohol.',                      'milestone', 'alcohol', 2160, '🌄', 36),
  ('alcohol_free_180d','180 days alcohol-free',  'Six months without alcohol.',                        'milestone', 'alcohol', 4320, '🌅', 37),
  ('alcohol_free_365d','1 year alcohol-free',    'A full year without alcohol.',                       'milestone', 'alcohol', 8760, '🏆', 38),
  ('cravings_10',      '10 cravings resisted',   'You rode out ten cravings.',                         'craving',   null,      10,   '💪', 50),
  ('cravings_50',      '50 cravings resisted',   'Fifty cravings resisted – real strength.',           'craving',   null,      50,   '🦁', 51),
  ('reduced_week',     'First reduced week',     'A full week below your original baseline.',          'progress',  null,      7,    '📉', 60),
  ('best_week',        'Best week yet',          'Your best weekly progress so far.',                  'progress',  null,      0,    '⭐', 61),
  ('tracking_7d',      'Consistent tracker',     'You tracked at least one hour every day for 7 days.', 'consistency', null,   7,    '📅', 70)
on conflict (code) do nothing;
