-- Adapter on/off persistence.
-- Backs the SupabaseToggleStore. Falls back to a JSON file in dev.

create table if not exists adapter_toggles (
    name text primary key,
    state text not null default 'enabled'
        check (state in ('enabled', 'disabled', 'paused', 'auto_disabled')),
    reason text,
    set_by text,
    set_at timestamptz not null default now(),
    paused_until timestamptz,
    consecutive_failures int not null default 0,
    last_failure_at timestamptz
);

create index if not exists idx_adapter_toggles_state on adapter_toggles (state);
create index if not exists idx_adapter_toggles_paused_until on adapter_toggles (paused_until)
    where state = 'paused';

-- Enable RLS but allow service-role full access (the backend uses the service key)
alter table adapter_toggles enable row level security;

-- Audit trail: append-only history of every toggle change. Optional but cheap.
create table if not exists adapter_toggle_history (
    id bigserial primary key,
    name text not null,
    state text not null,
    reason text,
    set_by text,
    set_at timestamptz not null default now(),
    paused_until timestamptz
);

create index if not exists idx_adapter_toggle_history_name on adapter_toggle_history (name, set_at desc);

-- Trigger to record every change
create or replace function record_adapter_toggle_change() returns trigger as $$
begin
    insert into adapter_toggle_history (name, state, reason, set_by, paused_until)
    values (NEW.name, NEW.state, NEW.reason, NEW.set_by, NEW.paused_until);
    return NEW;
end;
$$ language plpgsql;

drop trigger if exists trg_adapter_toggle_history on adapter_toggles;
create trigger trg_adapter_toggle_history
after insert or update on adapter_toggles
for each row execute function record_adapter_toggle_change();
