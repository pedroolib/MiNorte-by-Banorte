-- T8 · 013_consultant_ui.sql — Tarjetas por turno + escenarios guardados.
--
-- messages.tarjetas: UISchemas generadas por el Diseñador para responder
-- en el consultant_view (máx 3; [] si no hubo tools). Viajan con el historial.
-- saved_scenarios: simulaciones guardadas desde una conversación
-- (evaluar_gasto). Origen propio: NO se mezclan con analyst_insights.
-- Cómo aplicar: SQL Editor -> Run. (Requiere 006_agents.sql.)

alter table public.messages
  add column if not exists tarjetas jsonb not null default '[]';

create table if not exists public.saved_scenarios (
  id text primary key,                            -- uuid app
  company_id text not null references public.companies (id),
  conversation_id text references public.conversations (id),
  titulo text not null default '',
  detalle text not null default '',
  cifras jsonb not null default '{}',             -- desembolso, mensualidad, cobertura…
  created_at timestamptz not null default now()
);

create index if not exists idx_scenarios_company
  on public.saved_scenarios (company_id, created_at);

-- ============ RLS demo abierta (endurecer en TODO(auth)) ============
alter table public.saved_scenarios enable row level security;

drop policy if exists "demo_all" on public.saved_scenarios;

create policy "demo_all" on public.saved_scenarios
  for all to anon, authenticated using (true) with check (true);
