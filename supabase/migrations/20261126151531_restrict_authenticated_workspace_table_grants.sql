-- Supabase default privileges can include extra grants for authenticated.
-- Restrict this table to the only operations its client adapter requires.
revoke all on table public.zariya_user_workspaces from PUBLIC, anon, authenticated;
grant select, insert, update on table public.zariya_user_workspaces to authenticated;
