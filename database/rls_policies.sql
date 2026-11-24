-- =====================================================================
-- Reclaim – Row Level Security policies
--
-- Run AFTER schema.sql. Safe to re-run.
--
-- Rule: every signed-in user can read and write ONLY their own rows.
-- The anon role (not signed in) gets no access to any user data.
-- (select auth.uid()) is wrapped in a sub-select so Postgres evaluates
-- it once per query instead of once per row (Supabase recommendation).
-- =====================================================================

-- ---------------------------------------------------------------------
-- profiles: the row id IS the user id
-- ---------------------------------------------------------------------
alter table public.profiles enable row level security;

drop policy if exists "profiles_select_own" on public.profiles;
drop policy if exists "profiles_insert_own" on public.profiles;
drop policy if exists "profiles_update_own" on public.profiles;
drop policy if exists "profiles_delete_own" on public.profiles;

create policy "profiles_select_own" on public.profiles
  for select to authenticated using (id = (select auth.uid()));
create policy "profiles_insert_own" on public.profiles
  for insert to authenticated with check (id = (select auth.uid()));
create policy "profiles_update_own" on public.profiles
  for update to authenticated
  using (id = (select auth.uid())) with check (id = (select auth.uid()));
create policy "profiles_delete_own" on public.profiles
  for delete to authenticated using (id = (select auth.uid()));

-- ---------------------------------------------------------------------
-- All tables with a user_id column: identical owner-only policies
-- ---------------------------------------------------------------------
do $$
declare
  t text;
begin
  foreach t in array array[
    'addiction_profiles', 'recovery_goals', 'hourly_logs', 'consumption_logs',
    'craving_logs', 'daily_logs', 'journal_entries', 'user_achievements',
    'savings_goals', 'notification_preferences', 'ai_conversations'
  ]
  loop
    execute format('alter table public.%I enable row level security', t);

    execute format('drop policy if exists "%1$s_select_own" on public.%1$I', t);
    execute format('drop policy if exists "%1$s_insert_own" on public.%1$I', t);
    execute format('drop policy if exists "%1$s_update_own" on public.%1$I', t);
    execute format('drop policy if exists "%1$s_delete_own" on public.%1$I', t);

    execute format(
      'create policy "%1$s_select_own" on public.%1$I
         for select to authenticated using (user_id = (select auth.uid()))', t);
    execute format(
      'create policy "%1$s_insert_own" on public.%1$I
         for insert to authenticated with check (user_id = (select auth.uid()))', t);
    execute format(
      'create policy "%1$s_update_own" on public.%1$I
         for update to authenticated
         using (user_id = (select auth.uid()))
         with check (user_id = (select auth.uid()))', t);
    execute format(
      'create policy "%1$s_delete_own" on public.%1$I
         for delete to authenticated using (user_id = (select auth.uid()))', t);
  end loop;
end;
$$;

-- ---------------------------------------------------------------------
-- ai_messages: owner-only, AND the parent conversation must also be yours
-- ---------------------------------------------------------------------
alter table public.ai_messages enable row level security;

drop policy if exists "ai_messages_select_own" on public.ai_messages;
drop policy if exists "ai_messages_insert_own" on public.ai_messages;
drop policy if exists "ai_messages_update_own" on public.ai_messages;
drop policy if exists "ai_messages_delete_own" on public.ai_messages;

create policy "ai_messages_select_own" on public.ai_messages
  for select to authenticated using (user_id = (select auth.uid()));
create policy "ai_messages_insert_own" on public.ai_messages
  for insert to authenticated with check (
    user_id = (select auth.uid())
    and exists (
      select 1 from public.ai_conversations c
      where c.id = conversation_id and c.user_id = (select auth.uid())
    )
  );
create policy "ai_messages_update_own" on public.ai_messages
  for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "ai_messages_delete_own" on public.ai_messages
  for delete to authenticated using (user_id = (select auth.uid()));

-- ---------------------------------------------------------------------
-- achievements: read-only catalogue for signed-in users.
-- No insert/update/delete policies => users cannot modify it.
-- ---------------------------------------------------------------------
alter table public.achievements enable row level security;

drop policy if exists "achievements_read_all" on public.achievements;
create policy "achievements_read_all" on public.achievements
  for select to authenticated using (true);
