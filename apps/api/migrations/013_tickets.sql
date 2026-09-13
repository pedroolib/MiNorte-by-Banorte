-- T-tickets · 013_tickets.sql — Documentos (fotos de ticket) y solicitudes
-- de factura (spec #3.3 caso 1, #14, #19).
--
-- Cómo aplicar: Supabase Dashboard → SQL Editor → New query →
-- pega este archivo completo → Run. (Requiere 001_core.sql.)

-- ============ documents ============
-- La foto subida + lo que Vision pudo leer. `extraction` nunca lleva
-- cifras inventadas (campo no legible = null, ver ReceiptExtraction).
create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  company_id text not null references public.companies (id),
  kind text not null default 'receipt' check (kind in ('receipt')),
  mime text not null default 'image/jpeg',
  storage_path text,
  extraction jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- ============ invoice_requests ============
-- Estado del flujo ticket -> match -> browser agent -> CFDI (spec #19).
-- `steps` es la bitácora del Browser Agent (para la UI: "sensación de que
-- los agentes están trabajando"). `payload` es lo que se le entrega al
-- agente (nunca datos inventados, ver operator/receipts.build_invoice_payload).
create table if not exists public.invoice_requests (
  id uuid primary key default gen_random_uuid(),
  company_id text not null references public.companies (id),
  document_id uuid not null references public.documents (id),
  transaction_id text,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'borrador'
    check (status in (
      'borrador', 'listo_para_portal', 'navegando',
      'esperando_confirmacion', 'bloqueada_captcha', 'bloqueada_auth',
      'bloqueada_datos_faltantes', 'bloqueada_limite_pasos',
      'cancelada', 'resuelta', 'fallida'
    )),
  steps jsonb not null default '[]'::jsonb,
  cfdi_uuid text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_invoice_requests_company
  on public.invoice_requests (company_id, status);

-- ============ RLS demo abierta (endurecer en TODO(auth)) ============
alter table public.documents enable row level security;
alter table public.invoice_requests enable row level security;

drop policy if exists "demo_all" on public.documents;
drop policy if exists "demo_all" on public.invoice_requests;

create policy "demo_all" on public.documents
  for all to anon, authenticated using (true) with check (true);
create policy "demo_all" on public.invoice_requests
  for all to anon, authenticated using (true) with check (true);
