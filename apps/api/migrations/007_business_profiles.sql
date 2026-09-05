-- T8 · 007_business_profiles.sql — Perfil del negocio + lugar en CFDIs.
--
-- Cómo aplicar: Supabase Dashboard → SQL Editor → New query →
-- pega este archivo completo → Run. (Requiere 001_core.sql.)

create table if not exists public.business_profiles (
  company_id text primary key references public.companies (id),
  giro text not null default '',
  ciudad text not null default '',
  estado text not null default '',
  cp text not null default '',
  tamanio text not null default '',
  empleados integer,
  modelo text not null default 'mixto'
    check (modelo in ('b2b', 'b2c', 'mixto')),
  notas text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.cfdis
  add column if not exists lugar_expedicion text;

-- ============ RLS demo abierta (endurecer en TODO(auth)) ============
alter table public.business_profiles enable row level security;

drop policy if exists "demo_all" on public.business_profiles;

create policy "demo_all" on public.business_profiles
  for all to anon, authenticated using (true) with check (true);
