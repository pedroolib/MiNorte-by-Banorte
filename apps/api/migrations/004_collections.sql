-- T9 · 004_collections.sql — Directorio de clientes y cobranza (spec #15-16).
--
-- Cómo aplicar: Supabase Dashboard → SQL Editor → New query →
-- pega este archivo completo → Run. (Requiere 001_core.sql.)
--
-- customer_contacts PK (company_id, customer_rfc): el RFC es la llave que
-- sale del CFDI. Email NULLable: el directorio se llena por importación,
-- alta manual o captura en el flujo de envío (bootstrap perezoso).

-- ============ customer_contacts (spec #16) ============
create table if not exists public.customer_contacts (
  company_id text not null references public.companies (id),
  customer_rfc text not null,
  customer_name text not null default '',
  email text,                                  -- NULL = aún no capturado
  phone text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (company_id, customer_rfc)
);

-- ============ collection_actions (spec #15) ============
create table if not exists public.collection_actions (
  id bigserial primary key,
  company_id text not null references public.companies (id),
  receivable_id text not null,
  action_type text not null default 'email',
  recipient text not null default '',
  subject text not null default '',
  status text not null default 'queued'
    check (status in ('queued', 'sent', 'failed', 'skipped')),
  detail text not null default '',
  sent_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists idx_collection_receivable
  on public.collection_actions (company_id, receivable_id);

-- ============ RLS demo abierta (endurecer en TODO(auth)) ============
alter table public.customer_contacts enable row level security;
alter table public.collection_actions enable row level security;

drop policy if exists "demo_all" on public.customer_contacts;
drop policy if exists "demo_all" on public.collection_actions;

create policy "demo_all" on public.customer_contacts
  for all to anon, authenticated using (true) with check (true);
create policy "demo_all" on public.collection_actions
  for all to anon, authenticated using (true) with check (true);
