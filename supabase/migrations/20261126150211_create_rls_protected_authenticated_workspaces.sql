-- Authenticated Zariya workspaces are isolated by the Supabase Auth user id.
create table if not exists public.zariya_user_workspaces (
    user_id uuid primary key references auth.users(id) on delete cascade,
    state jsonb not null default '{"sessions":[],"notes":[],"decks":[]}'::jsonb,
    updated_at timestamptz not null default now()
);

alter table public.zariya_user_workspaces enable row level security;

revoke all on table public.zariya_user_workspaces from public, anon;
grant select, insert, update on table public.zariya_user_workspaces to authenticated;

drop policy if exists "Users read their own Zariya workspace" on public.zariya_user_workspaces;
create policy "Users read their own Zariya workspace"
    on public.zariya_user_workspaces for select to authenticated
    using ((select auth.uid()) = user_id);

drop policy if exists "Users create their own Zariya workspace" on public.zariya_user_workspaces;
create policy "Users create their own Zariya workspace"
    on public.zariya_user_workspaces for insert to authenticated
    with check ((select auth.uid()) = user_id);

drop policy if exists "Users update their own Zariya workspace" on public.zariya_user_workspaces;
create policy "Users update their own Zariya workspace"
    on public.zariya_user_workspaces for update to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

create index if not exists zariya_user_workspaces_updated_at_idx
    on public.zariya_user_workspaces (updated_at desc);
