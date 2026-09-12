-- T3 · 002_cfdis.sql — CFDIs (spec #14).
--
-- Cómo aplicar: Supabase Dashboard → SQL Editor → New query →
-- pega este archivo completo → Run.
-- (Requiere 001_core.sql por la FK a companies.)

create table if not exists public.cfdis (
  company_id text not null references public.companies (id),
  uuid text not null,                        -- Folio fiscal (TimbreFiscalDigital)
  tipo text not null check (tipo in ('emitido', 'recibido')),
  emisor_rfc text not null,
  emisor_nombre text not null default '',
  receptor_rfc text not null,
  receptor_nombre text not null default '',
  total numeric(14, 2) not null check (total > 0),
  subtotal numeric(14, 2) not null,
  iva numeric(14, 2) not null default 0,
  fecha_emision timestamptz not null,
  fecha_vencimiento timestamptz,
  concepto text not null default '',
  xml_path text,
  status text not null default 'vigente',
  serie text,
  folio text,
  metodo_pago text,
  forma_pago text,
  moneda text not null default 'MXN',
  uso_cfdi text,
  created_at timestamptz not null default now(),
  primary key (company_id, uuid)
);

create index if not exists idx_cfdis_company_tipo
  on public.cfdis (company_id, tipo);
create index if not exists idx_cfdis_company_fecha
  on public.cfdis (company_id, fecha_emision);

-- RLS demo abierta (endurecer en TODO(auth))
alter table public.cfdis enable row level security;

drop policy if exists "demo_all" on public.cfdis;

create policy "demo_all" on public.cfdis
  for all to anon, authenticated using (true) with check (true);
