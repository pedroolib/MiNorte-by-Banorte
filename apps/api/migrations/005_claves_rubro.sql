-- T6 · 005_claves_rubro.sql — Claves SAT en CFDIs + rubro en movimientos.
--
-- Cómo aplicar: Supabase Dashboard → SQL Editor → New query →
-- pega este archivo completo → Run. (Requiere 001/002.)

alter table public.cfdis
  add column if not exists clave_prodserv text,
  add column if not exists clave_unidad text;

alter table public.transactions
  add column if not exists rubro text not null default 'por_clasificar';

create index if not exists idx_transactions_rubro
  on public.transactions (company_id, rubro);
