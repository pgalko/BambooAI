-- Intervals.icu keys kept per athlete (2026-10-30, docs/DATASETS_DESIGN.md §17; patch 0249; amended in 0254).
-- Run once in the Supabase SQL editor of each hosted project BEFORE the app with 0249 is started there:
-- the app reads the two new columns on every key call, and without them it sees no key at all.
-- Safe to run again: a project migrated with the first version of this file (which left the uniqueness on
-- auth0_id in place, so a second athlete's key was refused - 2026-10-30, dev) is finished by a second run.
-- The self-hosted edition needs nothing: its SQLite file upgrades itself on the first start.
--
-- One row per coach and athlete: athlete_id is the id Intervals.icu gives the key's owner, athlete_name their
-- name. The row each coach has today keeps its key as the one "pending" row (athlete_id ''), which the app
-- names at the coach's next load (or when the Settings dialog lists it and Intervals.icu answers).

alter table public.intervals_integration add column if not exists athlete_id text not null default '';
alter table public.intervals_integration add column if not exists athlete_name text default '';

-- the old uniqueness - one row per coach, whether keyed by bamboo_user_id or by auth0_id, and whether made as a
-- constraint or as a unique index - goes; the one uniqueness left is (bamboo_user_id, athlete_id), made below
do $$
declare c record;
begin
  for c in
    select con.conname
    from pg_constraint con
    where con.conrelid = 'public.intervals_integration'::regclass and con.contype = 'u'
      and (select array_agg(att.attname::text order by att.attnum)
           from pg_attribute att where att.attrelid = con.conrelid and att.attnum = any(con.conkey))
          in (array['bamboo_user_id'], array['auth0_id'])
  loop
    execute format('alter table public.intervals_integration drop constraint %I', c.conname);
  end loop;
  for c in
    select i.indexname
    from pg_indexes i
    where i.schemaname = 'public' and i.tablename = 'intervals_integration'
      and i.indexdef ilike 'create unique index%' and (i.indexdef ~* '\(bamboo_user_id\)' or i.indexdef ~* '\(auth0_id\)')
  loop
    execute format('drop index if exists public.%I', c.indexname);
  end loop;
end $$;

create unique index if not exists intervals_integration_user_athlete
  on public.intervals_integration (bamboo_user_id, athlete_id);

-- what it looks like after: the one unique index left, then every coach's rows (a row per athlete; '' = not named yet)
select indexname, indexdef from pg_indexes where schemaname = 'public' and tablename = 'intervals_integration' and indexdef ilike 'create unique index%';
select bamboo_user_id, athlete_id, athlete_name, created_at, last_used_at from public.intervals_integration order by bamboo_user_id, athlete_id;
