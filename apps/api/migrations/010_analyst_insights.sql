-- T8 · 010_analyst_insights.sql — Insights rankeados del Analista.
--
-- El Analista interpreta signals() + alertas deterministas y emite hasta
-- ~6 insights con evidencia obligatoria (toda cifra cita su fuente).
-- El Diseñador consume esta tabla para elegir tarjetas.
-- Escritura idempotente por (company_id, month): correr de nuevo reemplaza.
-- Cómo aplicar: SQL Editor -> Run. (Requiere 001_core.sql.)

create table if not exists public.analyst_insights (
  id text primary key,                            -- uuid app
  company_id text not null references public.companies (id),
  month text not null,                            -- 'YYYY-MM'
  kind text not null,                             -- señal o regla origen
  severity text not null
    check (severity in ('info', 'warning', 'critical')),
  titulo text not null default '',
  detalle text not null default '',
  evidencia jsonb not null default '[]',          -- [{señal, valor, unidad}]
  created_at timestamptz not null default now(),
  unique (company_id, month, kind)
);

create index if not exists idx_insights_company_month
  on public.analyst_insights (company_id, month, severity);

-- ============ RLS demo abierta (endurecer en TODO(auth)) ============
alter table public.analyst_insights enable row level security;

drop policy if exists "demo_all" on public.analyst_insights;

create policy "demo_all" on public.analyst_insights
  for all to anon, authenticated using (true) with check (true);
