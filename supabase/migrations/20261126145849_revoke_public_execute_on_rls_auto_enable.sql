-- Keep the DDL event-trigger helper unavailable through the exposed Data API.
revoke execute on function public.rls_auto_enable() from PUBLIC, anon, authenticated;
