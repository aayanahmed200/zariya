-- Zariya workspace persistence.
-- The app uses its signed Flask session to derive a pseudonymous owner_id.
-- Only the server-side Supabase secret/service-role key may access this table.
create table if not exists public.zariya_workspaces (
    owner_id text primary key check (owner_id ~ '^[a-f0-9]{64}$'),
    state jsonb not null default '{"sessions":[],"notes":[],"decks":[]}'::jsonb,
    updated_at timestamptz not null default now()
);

alter table public.zariya_workspaces enable row level security;

-- The browser never receives the privileged key. Keep direct client roles out.
revoke all on table public.zariya_workspaces from anon, authenticated;
grant select, insert, update, delete on table public.zariya_workspaces to service_role;

create index if not exists zariya_workspaces_updated_at_idx
    on public.zariya_workspaces (updated_at desc);
