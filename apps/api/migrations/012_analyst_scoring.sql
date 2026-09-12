-- T8 · 012_analyst_scoring.sql — Campos de scoring + comentarios de anclas.
--
-- family / financial_impact / actionability alimentan el scoring del
-- Composition Engine. analyst_anchors guarda los comentarios del Analista
-- para las 4 métricas principales (los números los pone la composición).
-- Cómo aplicar: SQL Editor -> Run. (Requiere 010_analyst_insights.sql.)

alter table public.analyst_insights
  add column if not exists family text not null default 'operations',
  add column if not exists financial_impact text not null default 'low'
    check (financial_impact in ('high', 'medium', 'low')),
  add column if not exists actionability text not null default 'low'
    check (actionability in ('high', 'medium', 'low'));

create table if not exists public.analyst_anchors (
  company_id text not null references public.companies (id),
  month text not null,                            -- 'YYYY-MM'
  metric text not null
    check (metric in ('revenue', 'profit', 'cash', 'estimated_tax')),
  comment text not null default '',
  created_at timestamptz not null default now(),
  unique (company_id, month, metric)
);

create table if not exists public.dashboard_compositions (
  company_id text not null references public.companies (id),
  week_id text not null,                          -- 'YYYY-Www' ISO
  month text not null,                            -- mes analizado
  payload jsonb not null default '{}',            -- JSON final del dashboard
  created_at timestamptz not null default now(),
  unique (company_id, week_id)
);

-- ============ RLS demo abierta (endurecer en TODO(auth)) ============
alter table public.analyst_anchors enable row level security;

drop policy if exists "demo_all" on public.analyst_anchors;

create policy "demo_all" on public.analyst_anchors
  for all to anon, authenticated using (true) with check (true);

alter table public.dashboard_compositions enable row level security;

drop policy if exists "demo_all" on public.dashboard_compositions;

create policy "demo_all" on public.dashboard_compositions
  for all to anon, authenticated using (true) with check (true);
