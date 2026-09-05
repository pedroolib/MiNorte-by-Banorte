-- T9 · 008_contacts_pk.sql — Directorio keyed por (empresa, RFC, nombre).
--
-- Por qué: los CFDIs a público general (XAXX) comparten RFC entre clientes
-- distintos; la llave natural pasa a incluir el nombre. Compatible con el
-- demo (RFCs únicos -> mismo comportamiento).
-- Cómo aplicar: SQL Editor -> Run. (Requiere 004_collections.sql.)

alter table public.customer_contacts
  drop constraint if exists customer_contacts_pkey;

alter table public.customer_contacts
  add constraint customer_contacts_pkey
  primary key (company_id, customer_rfc, customer_name);
