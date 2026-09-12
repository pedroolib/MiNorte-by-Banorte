-- T4/T5 · 003_financial.sql — Matches, CxC, snapshots y alertas (spec #14-15).
--
-- Cómo aplicar: Supabase Dashboard → SQL Editor → New query →
-- pega este archivo completo → Run. (Requiere 001_core.sql y 002_cfdis.sql.)

-- ============ transaction_cfdi_matches ============
create table if not exists public.transaction_cfdi_matches (
  company_id text not null references public.companies (id),
  transaction_id text not null,
  cfdi_uuid text,                              -- NULL si unmatched
  score numeric(5, 4) not null default 0,
  amount_score numeric(5, 4) not null default 0,
  date_score numeric(5, 4) not null default 0,
  merchant_score numeric(5, 4) not null default 0,
  status text not null check (status in ('auto', 'review', 'unmatched')),
  created_at timestamptz not null default now(),
  primary key (company_id, transaction_id)
);

-- ============ accounts_receivable (spec #15) ============
create table if not exists public.accounts_receivable (
  id text not null,                            -- 'ar_<uuid8>' determinista
  company_id text not null references public.companies (id),
  cfdi_id text not null,                       -- uuid del emitido
  customer_name text not null default '',
  customer_rfc text not null default '',
  amount numeric(14, 2) not null,
  amount_paid numeric(14, 2) not null default 0,
  amount_pending numeric(14, 2) not null,
  issued_at timestamptz not null,
  due_date timestamptz,
  status text not null default 'open'
    check (status in ('open', 'partially_paid', 'paid', 'overdue')),
  last_reminder_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (company_id, id)
);

-- ============ financial_snapshots ============
create table if not exists public.financial_snapshots (
  company_id text not null references public.companies (id),
  month text not null,                         -- '2026-08'
  ventas numeric(14, 2) not null,
  gastos numeric(14, 2) not null,
  utilidad numeric(14, 2) not null,
  margen numeric(9, 6) not null,
  efectivo numeric(14, 2) not null,
  impuesto_estimado numeric(14, 2) not null,
  cxc_total numeric(14, 2) not null default 0,
  sin_cfdi_count integer not null default 0,
  sin_cfdi_total numeric(14, 2) not null default 0,
  flujo_neto numeric(14, 2) not null,
  payload jsonb not null default '{}',         -- métricas MoM, categorías…
  created_at timestamptz not null default now(),
  primary key (company_id, month)
);

-- ============ alerts ============
create table if not exists public.alerts (
  id text not null,                            -- '2026-08_sin_factura'
  company_id text not null references public.companies (id),
  month text not null,
  rule text not null,
  severity text not null check (severity in ('info', 'warning', 'critical')),
  titulo text not null,
  detalle text not null default '',
  total numeric(14, 2),
  estado text not null default 'abierta'
    check (estado in ('abierta', 'resuelta', 'descartada')),
  payload jsonb not null default '{}',         -- pista UI generativa (T8)
  created_at timestamptz not null default now(),
  primary key (company_id, id)
);

create index if not exists idx_alerts_company_month
  on public.alerts (company_id, month);

-- ============ RLS demo abierta (endurecer en TODO(auth)) ============
alter table public.transaction_cfdi_matches enable row level security;
alter table public.accounts_receivable enable row level security;
alter table public.financial_snapshots enable row level security;
alter table public.alerts enable row level security;

drop policy if exists "demo_all" on public.transaction_cfdi_matches;
drop policy if exists "demo_all" on public.accounts_receivable;
drop policy if exists "demo_all" on public.financial_snapshots;
drop policy if exists "demo_all" on public.alerts;

create policy "demo_all" on public.transaction_cfdi_matches
  for all to anon, authenticated using (true) with check (true);
create policy "demo_all" on public.accounts_receivable
  for all to anon, authenticated using (true) with check (true);
create policy "demo_all" on public.financial_snapshots
  for all to anon, authenticated using (true) with check (true);
create policy "demo_all" on public.alerts
  for all to anon, authenticated using (true) with check (true);
