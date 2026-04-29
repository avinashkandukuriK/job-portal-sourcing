-- =============================================================================
-- 003_core_schema.sql
-- Core schema for the blue-collar candidate sourcing app.
-- Idempotent: safe to run repeatedly.
--
-- Design decisions locked in this migration:
--   * UUID v7 primary keys (sortable, distributed-friendly, safe in URLs)
--   * JSONB for flexible candidate skills + a normalized skills_taxonomy lookup
--   * Compliance modeled as current-state row + immutable compliance_history
--   * Files held in Supabase Storage; documents table stores metadata + path
--   * Universal created_at / updated_at on every table; updated_at auto-bumped
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Extensions
-- -----------------------------------------------------------------------------
create extension if not exists pgcrypto;
create extension if not exists pg_trgm;          -- fuzzy text search on names
create extension if not exists btree_gin;        -- composite GIN indexes
-- (PostGIS is intentionally NOT required — radius search uses lat/lng + earth distance)

-- -----------------------------------------------------------------------------
-- UUID v7 generator (sortable by time)
-- -----------------------------------------------------------------------------
create or replace function uuidv7() returns uuid
language plpgsql
volatile as $$
declare
    v_unix_t bigint := (extract(epoch from clock_timestamp()) * 1000)::bigint;
    v_bytes bytea := decode(lpad(to_hex(v_unix_t), 12, '0'), 'hex')
                     || gen_random_bytes(10);
begin
    -- version = 7 (high nibble of byte 6)
    v_bytes := set_byte(v_bytes, 6, ((get_byte(v_bytes, 6) & 15) | 112));
    -- variant = RFC 4122 (high bits of byte 8)
    v_bytes := set_byte(v_bytes, 8, ((get_byte(v_bytes, 8) & 63) | 128));
    return encode(v_bytes, 'hex')::uuid;
end;
$$;

-- -----------------------------------------------------------------------------
-- Universal updated_at trigger
-- -----------------------------------------------------------------------------
create or replace function set_updated_at() returns trigger
language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

-- =============================================================================
-- Lookup / taxonomy tables
-- =============================================================================

create table if not exists skills_taxonomy (
    id uuid primary key default uuidv7(),
    canonical_name text not null unique,
    aliases text[] not null default '{}',          -- "fork-lift", "fork lift", "Forklift Op"
    category text,                                 -- 'cert', 'equipment', 'soft', 'language', ...
    description text,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_skills_taxonomy_category on skills_taxonomy (category);
create index if not exists idx_skills_taxonomy_aliases_gin on skills_taxonomy using gin (aliases);

create table if not exists certs_taxonomy (
    id uuid primary key default uuidv7(),
    canonical_name text not null unique,           -- 'Forklift (Class IV)', 'OSHA-10', 'CDL Class A'
    aliases text[] not null default '{}',
    issuing_body text,                             -- 'OSHA', 'DOT', 'state', etc
    typical_validity_years numeric,                -- forklift ≈ 3, OSHA-10 lifetime, CDL medical 2
    description text,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_certs_taxonomy_aliases_gin on certs_taxonomy using gin (aliases);

-- =============================================================================
-- Users (lightweight — replace with Supabase auth.users link when auth lands)
-- =============================================================================

create table if not exists users (
    id uuid primary key default uuidv7(),
    email text not null unique,
    name text,
    role text not null default 'recruiter'
        check (role in ('admin', 'recruiter', 'viewer')),
    is_active boolean not null default true,
    last_login_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_users_email on users (email);

-- =============================================================================
-- Clients + contacts
-- =============================================================================

create table if not exists clients (
    id uuid primary key default uuidv7(),
    name text not null,
    industry text,
    website text,
    notes text,
    preferences jsonb not null default '{}'::jsonb,  -- 'no_felonies': true, 'min_drug_panel': 4, ...
    last_order_at timestamptz,
    archived_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_clients_name_trgm on clients using gin (name gin_trgm_ops);
create index if not exists idx_clients_active on clients (created_at) where archived_at is null;

create table if not exists client_contacts (
    id uuid primary key default uuidv7(),
    client_id uuid not null references clients(id) on delete cascade,
    name text not null,
    title text,
    email text,
    phone text,
    is_primary boolean not null default false,
    last_contacted_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_client_contacts_client on client_contacts (client_id);

-- =============================================================================
-- Candidates  (the master record)
-- =============================================================================

create table if not exists candidates (
    id uuid primary key default uuidv7(),

    -- Identity
    name text not null,
    email text,
    phone text,
    alt_phone text,
    profile_urls jsonb not null default '[]'::jsonb,    -- [{kind:'linkedin', url:'...'}, ...]

    -- Profile
    headline text,
    current_title text,
    current_company text,

    -- Location (US-focused; lat/lng for radius search)
    location text,
    city text,
    state text,                                          -- 2-letter US state
    zip text,
    country text default 'US',
    latitude numeric(9,6),
    longitude numeric(9,6),

    -- Skills + experience
    skills jsonb not null default '[]'::jsonb,           -- ["forklift","OSHA-10"]
    skills_normalized text[] not null default '{}',      -- canonical ids for fast filtering
    years_experience numeric,
    desired_pay_rate numeric,
    pay_rate_unit text default 'hourly'
        check (pay_rate_unit in ('hourly', 'weekly', 'salary')),

    -- Availability
    availability_status text default 'unknown'
        check (availability_status in ('available', 'placed', 'unavailable', 'unknown')),
    available_from date,
    available_until date,

    -- Sourcing provenance
    source text,                                         -- adapter name
    source_id text,                                      -- native id from source
    profile_url text,

    -- Compliance shortcuts (mirrors of compliance_statuses for fast filtering)
    last_drug_test_at date,
    last_background_check_at date,

    -- Communication preferences / TCPA
    sms_consent_given_at timestamptz,
    email_consent_given_at timestamptz,
    do_not_contact_until timestamptz,

    -- Timeline
    first_sourced_at timestamptz not null default now(),
    last_contacted_at timestamptz,
    last_active_at timestamptz,

    -- Soft delete
    archived_at timestamptz,

    -- Search vector (auto-populated by trigger below)
    search_vector tsvector,

    -- Free-form extras
    raw jsonb not null default '{}'::jsonb,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- Dedupe: a (source, source_id) pair should be unique per source
create unique index if not exists ux_candidates_source_pair
    on candidates (source, source_id) where source_id is not null;

create index if not exists idx_candidates_phone on candidates (phone) where phone is not null;
create index if not exists idx_candidates_email on candidates (lower(email)) where email is not null;
create index if not exists idx_candidates_state on candidates (state);
create index if not exists idx_candidates_zip on candidates (zip);
create index if not exists idx_candidates_skills_gin on candidates using gin (skills jsonb_path_ops);
create index if not exists idx_candidates_skills_norm_gin on candidates using gin (skills_normalized);
create index if not exists idx_candidates_name_trgm on candidates using gin (name gin_trgm_ops);
create index if not exists idx_candidates_search_vector on candidates using gin (search_vector);
create index if not exists idx_candidates_last_contacted on candidates (last_contacted_at);
create index if not exists idx_candidates_dnc on candidates (do_not_contact_until)
    where do_not_contact_until is not null;
create index if not exists idx_candidates_geo on candidates (latitude, longitude)
    where latitude is not null and longitude is not null;
create index if not exists idx_candidates_active on candidates (created_at) where archived_at is null;

-- search_vector auto-population
create or replace function candidates_set_search_vector() returns trigger
language plpgsql as $$
begin
    new.search_vector :=
        setweight(to_tsvector('english', coalesce(new.name, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(new.headline, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(new.current_title, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(new.current_company, '')), 'C') ||
        setweight(to_tsvector('english', coalesce(new.location, '')), 'C') ||
        setweight(to_tsvector('english', array_to_string(new.skills_normalized, ' ')), 'A');
    return new;
end;
$$;
drop trigger if exists trg_candidates_search_vector on candidates;
create trigger trg_candidates_search_vector
before insert or update on candidates
for each row execute function candidates_set_search_vector();

-- =============================================================================
-- Opt-out registry (TCPA legal requirement)
-- =============================================================================

create table if not exists opt_outs (
    id uuid primary key default uuidv7(),
    channel text not null check (channel in ('sms', 'email', 'all')),
    value text not null,                              -- normalized phone (E.164) or lowercased email
    candidate_id uuid references candidates(id) on delete set null,
    reason text,
    opted_out_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (channel, value)
);
create index if not exists idx_opt_outs_value on opt_outs (value);

-- =============================================================================
-- Job orders (parsed JDs from clients)
-- =============================================================================

create table if not exists job_orders (
    id uuid primary key default uuidv7(),
    client_id uuid references clients(id) on delete set null,
    client_contact_id uuid references client_contacts(id) on delete set null,
    owner_user_id uuid references users(id) on delete set null,

    title text not null,
    title_variants text[] not null default '{}',
    raw_jd_text text,
    parsed_jd jsonb not null default '{}'::jsonb,           -- ParsedJD model

    required_skills text[] not null default '{}',
    nice_to_have_skills text[] not null default '{}',
    required_certs text[] not null default '{}',
    seniority text,
    min_years_experience numeric,
    max_years_experience numeric,

    -- Location
    location text,
    city text,
    state text,
    zip text,
    latitude numeric(9,6),
    longitude numeric(9,6),
    radius_miles numeric default 25,
    remote_ok boolean not null default false,

    -- Commercial terms
    pay_rate numeric,
    bill_rate numeric,
    pay_rate_unit text default 'hourly',
    temps_needed integer not null default 1,
    conversion_hours integer,
    shift text,
    dress_code text,

    -- Compliance requirements specific to this order
    requires_i9 boolean not null default true,
    requires_everify boolean not null default true,
    requires_drug_test boolean not null default false,
    drug_test_panel integer,                                -- 4, 5, 10
    requires_background_check boolean not null default false,
    background_check_levels text[] not null default '{}',   -- ['federal','county']
    requires_nda boolean not null default false,
    other_compliance jsonb not null default '{}'::jsonb,

    status text not null default 'open'
        check (status in ('draft','open','on_hold','filled','cancelled','expired')),

    fill_deadline date,
    start_date date,
    posted_at timestamptz,
    closed_at timestamptz,
    expires_at timestamptz,

    archived_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_job_orders_status on job_orders (status);
create index if not exists idx_job_orders_client on job_orders (client_id);
create index if not exists idx_job_orders_owner on job_orders (owner_user_id);
create index if not exists idx_job_orders_deadline on job_orders (fill_deadline) where status = 'open';
create index if not exists idx_job_orders_skills_gin on job_orders using gin (required_skills);

-- =============================================================================
-- Documents (file metadata; bytes live in Supabase Storage)
-- =============================================================================

create table if not exists documents (
    id uuid primary key default uuidv7(),
    candidate_id uuid references candidates(id) on delete cascade,
    placement_id uuid,                              -- FK added below after placements exists
    job_order_id uuid references job_orders(id) on delete set null,
    kind text not null check (kind in (
        'resume','cover_letter','i9','drug_test','background_check',
        'cert','license','nda','schedule_c','ehs_training','other'
    )),
    storage_path text not null,                     -- bucket path
    file_name text,
    mime_type text,
    file_size_bytes bigint,
    sha256 text,
    uploaded_by_user_id uuid references users(id) on delete set null,
    uploaded_at timestamptz not null default now(),
    expires_at timestamptz,
    verified_at timestamptz,
    verified_by_user_id uuid references users(id) on delete set null,
    deleted_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_documents_candidate on documents (candidate_id);
create index if not exists idx_documents_placement on documents (placement_id);
create index if not exists idx_documents_kind on documents (kind);
create index if not exists idx_documents_expires on documents (expires_at) where expires_at is not null;

-- =============================================================================
-- Certifications (per candidate)
-- =============================================================================

create table if not exists certifications (
    id uuid primary key default uuidv7(),
    candidate_id uuid not null references candidates(id) on delete cascade,
    cert_taxonomy_id uuid references certs_taxonomy(id) on delete set null,
    name text not null,                             -- 'Forklift (Class IV)' (denormalized for portability)
    issuing_body text,
    cert_number text,
    document_id uuid references documents(id) on delete set null,
    issued_at date,
    expires_at date,
    verified_at timestamptz,
    verified_by_user_id uuid references users(id) on delete set null,
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_certifications_candidate on certifications (candidate_id);
create index if not exists idx_certifications_expires on certifications (expires_at) where expires_at is not null;

-- =============================================================================
-- Placements (a candidate working on a job order)
-- =============================================================================

create table if not exists placements (
    id uuid primary key default uuidv7(),
    candidate_id uuid not null references candidates(id) on delete restrict,
    job_order_id uuid not null references job_orders(id) on delete restrict,
    owner_user_id uuid references users(id) on delete set null,

    status text not null default 'submitted'
        check (status in (
            'submitted','interview','offered','accepted','started',
            'completed','converted','terminated','no_show','rejected'
        )),

    pay_rate numeric,
    bill_rate numeric,
    margin_pct numeric generated always as (
        case when bill_rate > 0 and pay_rate is not null
             then round((bill_rate - pay_rate) / bill_rate * 100, 2)
             else null end
    ) stored,

    submitted_at timestamptz,
    interview_at timestamptz,
    offered_at timestamptz,
    accepted_at timestamptz,
    start_date date,
    end_date date,

    -- Conversion tracking
    conversion_eligible_at date,
    converted_at timestamptz,
    terminated_at timestamptz,
    termination_reason text,

    -- Per-placement compliance signoffs (in addition to compliance_statuses)
    nda_signed_at timestamptz,
    schedule_c_signed_at timestamptz,
    ehs_completed_at timestamptz,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_placements_candidate on placements (candidate_id);
create index if not exists idx_placements_order on placements (job_order_id);
create index if not exists idx_placements_status on placements (status);
create index if not exists idx_placements_start on placements (start_date);
create index if not exists idx_placements_end on placements (end_date);

-- now we can wire documents.placement_id back
alter table documents
    drop constraint if exists fk_documents_placement,
    add constraint fk_documents_placement
        foreign key (placement_id) references placements(id) on delete set null;

-- =============================================================================
-- Compliance status (current state) + history (immutable trail)
-- =============================================================================

create table if not exists compliance_statuses (
    id uuid primary key default uuidv7(),
    candidate_id uuid not null references candidates(id) on delete cascade,
    placement_id uuid references placements(id) on delete cascade,

    i9_status text default 'pending'
        check (i9_status in ('pending','completed','expired','na')),
    i9_completed_at timestamptz,

    everify_status text default 'pending'
        check (everify_status in ('pending','authorized','tentative_nonconfirmation','final_nonconfirmation','na')),
    everify_run_at timestamptz,
    everify_case_number text,

    drug_test_status text default 'pending'
        check (drug_test_status in ('pending','passed','failed','expired','na')),
    drug_test_panel integer,
    drug_test_completed_at timestamptz,

    background_check_status text default 'pending'
        check (background_check_status in ('pending','clear','flagged','disqualified','na')),
    background_check_completed_at timestamptz,

    nda_signed_at timestamptz,
    schedule_c_signed_at timestamptz,
    ehs_training_completed_at timestamptz,

    notes text,
    next_review_due_at timestamptz,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    unique (candidate_id, placement_id)
);
create index if not exists idx_compliance_candidate on compliance_statuses (candidate_id);
create index if not exists idx_compliance_placement on compliance_statuses (placement_id);
create index if not exists idx_compliance_review_due on compliance_statuses (next_review_due_at)
    where next_review_due_at is not null;

create table if not exists compliance_history (
    id bigserial primary key,
    compliance_status_id uuid not null references compliance_statuses(id) on delete cascade,
    candidate_id uuid not null,
    placement_id uuid,
    field text not null,                    -- which field changed: 'i9_status', 'drug_test_status', etc
    old_value text,
    new_value text,
    changed_by_user_id uuid references users(id) on delete set null,
    changed_at timestamptz not null default now()
);
create index if not exists idx_compliance_history_status on compliance_history (compliance_status_id);
create index if not exists idx_compliance_history_candidate on compliance_history (candidate_id, changed_at desc);

-- =============================================================================
-- Searches (every search run) + per-adapter telemetry + per-candidate results
-- =============================================================================

create table if not exists searches (
    id uuid primary key default uuidv7(),
    job_order_id uuid references job_orders(id) on delete set null,
    user_id uuid references users(id) on delete set null,
    raw_jd_text text,
    parsed_jd jsonb not null default '{}'::jsonb,
    mode text not null default 'internal_external'
        check (mode in ('internal','external','internal_external')),
    selected_adapters text[] not null default '{}',     -- adapter names actually run
    candidate_count integer not null default 0,
    total_cost_usd numeric not null default 0,
    completed_at timestamptz,
    duration_ms integer,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_searches_order on searches (job_order_id, created_at desc);
create index if not exists idx_searches_user on searches (user_id, created_at desc);

create table if not exists adapter_run_log (
    id uuid primary key default uuidv7(),
    search_id uuid not null references searches(id) on delete cascade,
    adapter_name text not null,
    candidates_returned integer not null default 0,
    duration_ms integer,
    cost_usd numeric not null default 0,
    rate_limited boolean not null default false,
    error_message text,
    created_at timestamptz not null default now()
);
create index if not exists idx_adapter_run_log_search on adapter_run_log (search_id);
create index if not exists idx_adapter_run_log_adapter on adapter_run_log (adapter_name, created_at desc);

create table if not exists search_results (
    id uuid primary key default uuidv7(),
    search_id uuid not null references searches(id) on delete cascade,
    candidate_id uuid not null references candidates(id) on delete cascade,
    adapter_name text not null,
    score numeric not null,
    score_breakdown jsonb not null default '{}'::jsonb,
    reasoning text,
    rank integer,
    created_at timestamptz not null default now(),
    unique (search_id, candidate_id, adapter_name)
);
create index if not exists idx_search_results_search on search_results (search_id, score desc);
create index if not exists idx_search_results_candidate on search_results (candidate_id, created_at desc);

-- =============================================================================
-- Saved searches (auto-rerun)
-- =============================================================================

create table if not exists saved_searches (
    id uuid primary key default uuidv7(),
    user_id uuid references users(id) on delete cascade,
    name text not null,
    job_order_id uuid references job_orders(id) on delete set null,
    parsed_jd jsonb not null default '{}'::jsonb,
    selected_adapters text[] not null default '{}',
    cadence_minutes integer,                            -- null = manual only
    last_run_at timestamptz,
    next_run_at timestamptz,
    paused_until timestamptz,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_saved_searches_user on saved_searches (user_id);
create index if not exists idx_saved_searches_next_run on saved_searches (next_run_at)
    where is_active and next_run_at is not null;

-- =============================================================================
-- Inbound applications + outbound job postings
-- =============================================================================

create table if not exists applications (
    id uuid primary key default uuidv7(),
    job_order_id uuid references job_orders(id) on delete set null,
    candidate_id uuid references candidates(id) on delete set null,
    name text,
    email text,
    phone text,
    resume_document_id uuid references documents(id) on delete set null,
    raw_form_data jsonb not null default '{}'::jsonb,
    parsed_at timestamptz,
    received_at timestamptz not null default now(),
    consent_given_at timestamptz,
    consent_text text,
    source_ip text,
    user_agent text,
    status text not null default 'received'
        check (status in ('received','parsed','matched','rejected','duplicate')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_applications_order on applications (job_order_id);
create index if not exists idx_applications_candidate on applications (candidate_id);
create index if not exists idx_applications_phone on applications (phone);
create index if not exists idx_applications_email on applications (lower(email));

create table if not exists job_postings (
    id uuid primary key default uuidv7(),
    job_order_id uuid not null references job_orders(id) on delete cascade,
    board_name text not null,                         -- 'indeed_free','jobget','craigslist','snagajob',...
    external_id text,
    posting_url text,
    cost_usd numeric not null default 0,
    status text not null default 'pending'
        check (status in ('pending','live','expired','removed','failed')),
    posted_at timestamptz,
    expires_at timestamptz,
    removed_at timestamptz,
    last_synced_at timestamptz,
    error_message text,
    application_count integer not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_job_postings_order on job_postings (job_order_id);
create index if not exists idx_job_postings_status on job_postings (status);

-- =============================================================================
-- Pipeline (kanban) + Submissions (package sent to client)
-- =============================================================================

create table if not exists pipeline_entries (
    id uuid primary key default uuidv7(),
    job_order_id uuid not null references job_orders(id) on delete cascade,
    candidate_id uuid not null references candidates(id) on delete cascade,
    owner_user_id uuid references users(id) on delete set null,
    stage text not null default 'new'
        check (stage in (
            'new','contacted','screened','submitted','interview',
            'offer','placed','started','converted','rejected','withdrawn'
        )),
    score numeric,
    rank integer,
    stage_changed_at timestamptz not null default now(),
    submitted_at timestamptz,
    interview_at timestamptz,
    offered_at timestamptz,
    placed_at timestamptz,
    closed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (job_order_id, candidate_id)
);
create index if not exists idx_pipeline_order on pipeline_entries (job_order_id, stage);
create index if not exists idx_pipeline_candidate on pipeline_entries (candidate_id);
create index if not exists idx_pipeline_stale on pipeline_entries (stage_changed_at);

create table if not exists submissions (
    id uuid primary key default uuidv7(),
    pipeline_entry_id uuid references pipeline_entries(id) on delete cascade,
    job_order_id uuid not null references job_orders(id) on delete cascade,
    candidate_id uuid not null references candidates(id) on delete cascade,
    submitted_by_user_id uuid references users(id) on delete set null,
    sent_to_email text,
    package_document_id uuid references documents(id) on delete set null,
    notes text,
    sent_at timestamptz not null default now(),
    viewed_at timestamptz,
    client_feedback text,
    client_feedback_at timestamptz,
    decision text check (decision in ('interview','reject','hold','hire',null)),
    decision_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_submissions_order on submissions (job_order_id);
create index if not exists idx_submissions_candidate on submissions (candidate_id);

-- =============================================================================
-- Communication log (email + SMS, inbound + outbound)
-- =============================================================================

create table if not exists communication_log (
    id uuid primary key default uuidv7(),
    candidate_id uuid not null references candidates(id) on delete cascade,
    job_order_id uuid references job_orders(id) on delete set null,
    user_id uuid references users(id) on delete set null,
    channel text not null check (channel in ('email','sms','call','note')),
    direction text not null check (direction in ('outbound','inbound')),
    to_address text,
    from_address text,
    subject text,
    body text,
    template_id uuid,                                 -- references email/sms templates
    sequence_id uuid,                                 -- references outreach_sequences
    sequence_step_id uuid,                            -- references outreach_sequence_steps
    provider_message_id text,
    status text not null default 'sent'
        check (status in ('queued','sent','delivered','read','replied','bounced','failed','opted_out')),
    sent_at timestamptz,
    received_at timestamptz,
    read_at timestamptz,
    replied_at timestamptz,
    bounced_at timestamptz,
    error_message text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_comm_candidate on communication_log (candidate_id, created_at desc);
create index if not exists idx_comm_order on communication_log (job_order_id);
create index if not exists idx_comm_status on communication_log (status);

-- =============================================================================
-- Notes (recruiter free-text)
-- =============================================================================

create table if not exists notes (
    id uuid primary key default uuidv7(),
    candidate_id uuid references candidates(id) on delete cascade,
    job_order_id uuid references job_orders(id) on delete cascade,
    placement_id uuid references placements(id) on delete cascade,
    user_id uuid references users(id) on delete set null,
    body text not null,
    pinned boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (
        (candidate_id is not null)::int +
        (job_order_id is not null)::int +
        (placement_id is not null)::int >= 1
    )
);
create index if not exists idx_notes_candidate on notes (candidate_id, created_at desc);
create index if not exists idx_notes_order on notes (job_order_id, created_at desc);

-- =============================================================================
-- Tags
-- =============================================================================

create table if not exists tags (
    id uuid primary key default uuidv7(),
    name text not null unique,
    color text,
    description text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists candidate_tags (
    candidate_id uuid not null references candidates(id) on delete cascade,
    tag_id uuid not null references tags(id) on delete cascade,
    applied_by_user_id uuid references users(id) on delete set null,
    applied_at timestamptz not null default now(),
    expires_at timestamptz,
    primary key (candidate_id, tag_id)
);
create index if not exists idx_candidate_tags_tag on candidate_tags (tag_id);

-- =============================================================================
-- Outreach templates + sequences
-- =============================================================================

create table if not exists email_templates (
    id uuid primary key default uuidv7(),
    name text not null,
    subject text not null,
    body text not null,
    role_type text,                              -- which role taxonomy this is tuned for
    is_active boolean not null default true,
    created_by_user_id uuid references users(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists sms_templates (
    id uuid primary key default uuidv7(),
    name text not null,
    body text not null,
    role_type text,
    is_active boolean not null default true,
    created_by_user_id uuid references users(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists outreach_sequences (
    id uuid primary key default uuidv7(),
    name text not null,
    role_type text,
    job_order_id uuid references job_orders(id) on delete set null,
    is_active boolean not null default true,
    created_by_user_id uuid references users(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists outreach_sequence_steps (
    id uuid primary key default uuidv7(),
    sequence_id uuid not null references outreach_sequences(id) on delete cascade,
    step_order integer not null,
    day_offset integer not null,                 -- days since sequence start
    channel text not null check (channel in ('email','sms')),
    email_template_id uuid references email_templates(id) on delete set null,
    sms_template_id uuid references sms_templates(id) on delete set null,
    branch_on_reply text default 'stop'
        check (branch_on_reply in ('stop','continue','jump_to_step')),
    jump_to_step_order integer,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (sequence_id, step_order)
);

-- per-candidate enrollment in a sequence
create table if not exists outreach_enrollments (
    id uuid primary key default uuidv7(),
    sequence_id uuid not null references outreach_sequences(id) on delete cascade,
    candidate_id uuid not null references candidates(id) on delete cascade,
    job_order_id uuid references job_orders(id) on delete set null,
    started_at timestamptz not null default now(),
    next_send_at timestamptz,
    completed_at timestamptz,
    paused_until timestamptz,
    last_step_order integer not null default 0,
    state text not null default 'active'
        check (state in ('active','paused','completed','stopped','replied')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (sequence_id, candidate_id)
);
create index if not exists idx_outreach_enroll_next_send on outreach_enrollments (next_send_at)
    where state = 'active' and next_send_at is not null;

-- =============================================================================
-- Cost ledger (paid-adapter spend, for ROI reporting)
-- =============================================================================

create table if not exists cost_ledger (
    id uuid primary key default uuidv7(),
    occurred_at timestamptz not null default now(),
    adapter_name text not null,
    search_id uuid references searches(id) on delete set null,
    candidate_id uuid references candidates(id) on delete set null,
    job_order_id uuid references job_orders(id) on delete set null,
    placement_id uuid references placements(id) on delete set null,
    amount_usd numeric not null,
    units numeric,                               -- e.g. credits consumed
    unit_kind text,                              -- 'credits','calls','contacts'
    description text,
    created_at timestamptz not null default now()
);
create index if not exists idx_cost_ledger_occurred on cost_ledger (occurred_at desc);
create index if not exists idx_cost_ledger_adapter on cost_ledger (adapter_name, occurred_at desc);
create index if not exists idx_cost_ledger_placement on cost_ledger (placement_id);

-- =============================================================================
-- Wire updated_at triggers on every mutable table
-- =============================================================================

do $$
declare
    t text;
    tables text[] := array[
        'skills_taxonomy','certs_taxonomy','users',
        'clients','client_contacts','candidates','opt_outs','job_orders',
        'documents','certifications','placements','compliance_statuses',
        'searches','saved_searches','applications','job_postings',
        'pipeline_entries','submissions','communication_log','notes',
        'tags','email_templates','sms_templates',
        'outreach_sequences','outreach_sequence_steps','outreach_enrollments'
    ];
begin
    foreach t in array tables loop
        execute format('drop trigger if exists trg_set_updated_at_%I on %I', t, t);
        execute format(
            'create trigger trg_set_updated_at_%I before update on %I
             for each row execute function set_updated_at()', t, t
        );
    end loop;
end $$;

-- =============================================================================
-- Compliance history trigger — write to compliance_history on every change
-- =============================================================================

create or replace function record_compliance_change() returns trigger
language plpgsql as $$
declare
    fields text[] := array[
        'i9_status','everify_status','drug_test_status','background_check_status'
    ];
    f text;
    old_v text;
    new_v text;
begin
    foreach f in array fields loop
        execute format('select ($1).%I::text, ($2).%I::text', f, f)
            into old_v, new_v using OLD, NEW;
        if old_v is distinct from new_v then
            insert into compliance_history(
                compliance_status_id, candidate_id, placement_id,
                field, old_value, new_value
            ) values (NEW.id, NEW.candidate_id, NEW.placement_id, f, old_v, new_v);
        end if;
    end loop;
    return NEW;
end;
$$;

drop trigger if exists trg_compliance_history on compliance_statuses;
create trigger trg_compliance_history
after update on compliance_statuses
for each row execute function record_compliance_change();

-- =============================================================================
-- Done.
-- =============================================================================
