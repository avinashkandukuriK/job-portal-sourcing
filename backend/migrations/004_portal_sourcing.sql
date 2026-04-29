-- =============================================================================
-- 004_portal_sourcing.sql
-- Workforce portal automation run tracking and candidate source provenance.
-- Idempotent: safe to run repeatedly after 003_core_schema.sql.
-- =============================================================================

create table if not exists candidate_sources (
    id uuid primary key default uuidv7(),
    candidate_id uuid not null references candidates(id) on delete cascade,
    source_type text not null default 'workforce_portal',
    source_name text not null,
    source_state text,
    source_url text,
    capture_method text not null default 'automated_portal',
    contact_visibility text not null default 'visible_in_employer_portal',
    consent_note text,
    first_seen_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_candidate_sources_candidate on candidate_sources (candidate_id);
create index if not exists idx_candidate_sources_source on candidate_sources (source_name, source_state);

create table if not exists candidate_activity (
    id uuid primary key default uuidv7(),
    candidate_id uuid not null references candidates(id) on delete cascade,
    activity_type text not null,
    portal_run_id uuid,
    job_order_id uuid references job_orders(id) on delete set null,
    note text,
    created_by text,
    created_at timestamptz not null default now()
);
create index if not exists idx_candidate_activity_candidate on candidate_activity (candidate_id, created_at desc);

create table if not exists portal_runs (
    id uuid primary key default uuidv7(),
    portal_id text not null,
    portal_name text not null,
    state text not null,
    raw_jd_text text not null,
    parsed_jd jsonb not null default '{}'::jsonb,
    search_terms text[] not null default '{}',
    status text not null default 'running'
        check (status in ('not_ready','running','completed','failed')),
    candidates_found integer not null default 0,
    candidates_saved integer not null default 0,
    candidates_skipped integer not null default 0,
    warnings text[] not null default '{}',
    error_message text,
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_portal_runs_state on portal_runs (state, created_at desc);
create index if not exists idx_portal_runs_status on portal_runs (status);

create table if not exists portal_run_candidates (
    id uuid primary key default uuidv7(),
    portal_run_id uuid not null references portal_runs(id) on delete cascade,
    candidate_id uuid references candidates(id) on delete set null,
    source_profile_url text,
    candidate_snapshot jsonb not null default '{}'::jsonb,
    saved boolean not null default false,
    skipped_reason text,
    created_at timestamptz not null default now()
);
create index if not exists idx_portal_run_candidates_run on portal_run_candidates (portal_run_id);
create index if not exists idx_portal_run_candidates_candidate on portal_run_candidates (candidate_id);

do $$
declare
    t text;
    tables text[] := array['candidate_sources','portal_runs'];
begin
    foreach t in array tables loop
        execute format('drop trigger if exists trg_set_updated_at_%I on %I', t, t);
        execute format(
            'create trigger trg_set_updated_at_%I before update on %I
             for each row execute function set_updated_at()', t, t
        );
    end loop;
end $$;
