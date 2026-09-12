-- T2 · 001_core.sql — Núcleo MiNorte (spec #14, subconjunto T2).
--
-- Cómo aplicar: Supabase Dashboard → tu proyecto → SQL Editor → New query →
-- pega este archivo completo → Run.
--
-- Crea: companies, bank_accounts, transactions.
-- (cfdis, receivables, snapshots, alerts… llegan con T3/T4/T5 en 002_*.sql)
--
-- RLS: habilitado con políticas abiertas SOLO para demo single-company sin
-- auth (TODO(auth): restringir por auth.uid() → company al meter login).

-- ============ companies ============
create table if not exists public.companies (
  id text primary key,                     -- 'company_001'
  rfc text not null,
  razon_social text not null,
  nombre_comercial text,
  moneda text not null default 'MXN',
  timezone text not null default 'America/Mexico_City',
  created_at timestamptz not null default now()
);

-- ============ bank_accounts ============
create table if not exists public.bank_accounts (
  company_id text not null references public.companies (id),
  id text not null,                         -- 'acc_eje_001'
  alias text not null,
  clabe text,
  moneda text not null default 'MXN',
  created_at timestamptz not null default now(),
  primary key (company_id, id)
);

-- ============ transactions ============
create table if not exists public.transactions (
  company_id text not null references public.companies (id),
  id text not null,                         -- 'txn_2026080001'
  account_id text not null,
  fecha timestamptz not null,
  descripcion text not null,
  comercio text not null default 'DESCONOCIDO',
  rfc text,
  tipo text not null check (tipo in ('ingreso', 'egreso')),
  monto numeric(14, 2) not null check (monto > 0),
  saldo numeric(14, 2),
  es_interno boolean not null default false,
  categoria text not null default 'otro',
  created_at timestamptz not null default now(),
  primary key (company_id, id)
);

create index if not exists idx_transactions_company_fecha
  on public.transactions (company_id, fecha);
create index if not exists idx_transactions_company_categoria
  on public.transactions (company_id, categoria);

-- ============ RLS demo abierta (endurecer en TODO(auth)) ============
alter table public.companies enable row level security;
alter table public.bank_accounts enable row level security;
alter table public.transactions enable row level security;

drop policy if exists "demo_all" on public.companies;
drop policy if exists "demo_all" on public.bank_accounts;
drop policy if exists "demo_all" on public.transactions;

create policy "demo_all" on public.companies
  for all to anon, authenticated using (true) with check (true);
create policy "demo_all" on public.bank_accounts
  for all to anon, authenticated using (true) with check (true);
create policy "demo_all" on public.transactions
  for all to anon, authenticated using (true) with check (true);
