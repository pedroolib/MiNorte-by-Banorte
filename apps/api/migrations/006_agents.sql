-- T8 · 006_agents.sql — Conversaciones del Consultor + solicitudes de crédito.
--
-- Cómo aplicar: Supabase Dashboard → SQL Editor → New query →
-- pega este archivo completo → Run. (Requiere 001_core.sql.)
--
-- loan_applications es MOCK de contratación (spec #10): registra la
-- intención con términos snapshot; producción enchufaría Banorte real.

-- ============ conversations ============
create table if not exists public.conversations (
  id text primary key,                         -- uuid app
  company_id text not null references public.companies (id),
  titulo text not null default 'Conversación',
  created_at timestamptz not null default now()
);

-- ============ messages ============
create table if not exists public.messages (
  id text primary key,                         -- uuid app
  conversation_id text not null references public.conversations (id),
  role text not null check (role in ('usuario', 'asistente')),
  contenido text not null default '',
  tool_calls jsonb not null default '[]',
  created_at timestamptz not null default now()
);

create index if not exists idx_messages_conversation
  on public.messages (conversation_id, created_at);

-- ============ loan_applications (mock) ============
create table if not exists public.loan_applications (
  id text primary key,                         -- folio app
  company_id text not null references public.companies (id),
  option_id text not null,
  option_nombre text not null default '',
  amount numeric(14, 2) not null,
  months integer not null,
  tasa_anual numeric(7, 4) not null,
  pago_mensual numeric(14, 2) not null,
  costo_total numeric(14, 2) not null,
  cobertura numeric(12, 6),
  status text not null default 'solicitada_mock',
  terms jsonb not null default '{}',
  created_at timestamptz not null default now()
);

-- ============ RLS demo abierta (endurecer en TODO(auth)) ============
alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.loan_applications enable row level security;

drop policy if exists "demo_all" on public.conversations;
drop policy if exists "demo_all" on public.messages;
drop policy if exists "demo_all" on public.loan_applications;

create policy "demo_all" on public.conversations
  for all to anon, authenticated using (true) with check (true);
create policy "demo_all" on public.messages
  for all to anon, authenticated using (true) with check (true);
create policy "demo_all" on public.loan_applications
  for all to anon, authenticated using (true) with check (true);
