-- T9 · 009_txn_source.sql — Origen del movimiento (Banorte vs BBVA).
--
-- La regla de conciliación depende de la fuente (RFC vs nombre), así que
-- debe persistirse, no inferirse. Default conserva demo existente.
-- Cómo aplicar: SQL Editor -> Run.

alter table public.transactions
  add column if not exists source text not null default 'banorte_mock';
