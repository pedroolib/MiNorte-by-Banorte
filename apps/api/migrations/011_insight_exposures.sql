-- T8 · 011_insight_exposures.sql — Memoria de exposición del dashboard.
--
-- Qué tarjetas vio el usuario cada semana: base de novelty y
-- repetition_penalty del Composition Engine. clicked/resolved/dismissed
-- se llenan cuando el frontend los reporte; el registro al generar basta.
-- Cómo aplicar: SQL Editor -> Run. (Requiere 001_core.sql.)

create table if not exists public.insight_exposures (
  id text primary key,                            -- uuid app
  company_id text not null references public.companies (id),
  week_id text not null,                          -- 'YYYY-Www' ISO
  insight_kind text not null,
  insight_fingerprint text not null default '',   -- id del insight o tarjeta
  position integer not null default 0,            -- slot en el dashboard
  clicked boolean not null default false,
  resolved boolean not null default false,
  dismissed boolean not null default false,
  shown_at timestamptz not null default now()
);

create index if not exists idx_exposures_company_kind_shown
  on public.insight_exposures (company_id, insight_kind, shown_at);

create index if not exists idx_exposures_company_week
  on public.insight_exposures (company_id, week_id);

-- ============ RLS demo abierta (endurecer en TODO(auth)) ============
alter table public.insight_exposures enable row level security;

drop policy if exists "demo_all" on public.insight_exposures;

create policy "demo_all" on public.insight_exposures
  for all to anon, authenticated using (true) with check (true);
