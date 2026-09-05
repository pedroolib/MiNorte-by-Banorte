# MiNorte by Banorte — Estado del proyecto por tiers

> Para: el programador del ticket (T10/T11) y quien necesite contexto completo.
> Spec madre: `specs_de_minorte.md`. Contrato UI: `docs/ui-schema.md`.
> Principio #9 (no negociable): **el motor calcula, los agentes interpretan**.
> Stack: Next.js 14 + FastAPI + Supabase Postgres + OpenAI API (vendor cerrado)
> (`seed/private/` está gitignored: PDFs originales + `contacts.json` opcional).

Cómo correrlo: `docker compose up --build` (api :8000, web :3000) o
`make dev-api` + `pnpm --dir apps/web dev`. Verificación: `make test`
(65 tests backend), `pnpm --dir apps/web typecheck`, páginas crudas
`/debug` (volcado de datos) y `/cobranza` (cobranza funcional sin diseño).

---

## TIER 0 — HECHO y verificado (commits `b6f1ae5` → `26dfa29`, pusheado)

### Datos reales anonimizados (base de todo)
* **473 movimientos JUN–AGO 2026** (`seed/transactions.csv`) parseados de
  estados Banorte reales con parser propio validado (0 errores de cadena,
  depósitos exactos al centavo vs resúmenes). Empresa pagadora: 92% del
  ingreso es fondeo interno desde BBVA; historia real: caja 59 días → 20 → 4.
* **162 CFDI 4.0** (`seed/cfdis/emitido|recibido/*.xml`): 16 emitidos
  (11 cobrados + 5 CxC por **$76,550**) y 146 recibidos con IVA exacto.
  **4 gastos sin factura ($2,123)** dejados a propósito para el demo.
* Regenerables: `make seed`, `make cfdis` (deterministas).

### Motor determinístico (cero LLM)
* `app/financial/engine.py`: P&L, flujo, balance simplificado, métricas MoM,
  ISR, simuladores hiring/loan + `signals()` (~38 señales: crecimiento,
  rentabilidad, liquidez, fiscal, comercial, estructura).
* `app/financial/reconcile.py`: score `monto*0.5 + fecha*0.2 + comercio*0.3`
  (±15 días cross-mes), thresholds 0.85/0.60. Real: **157 auto, 0 review,
  4 unmatched**. CxC = emitido sin cobro.
* `app/financial/categorias.py`: taxonomía ~15 rubros PyME. CFDI manda
  (`ClaveProdServ`), banco por directorio+keywords, back-fill por conciliación.
  Cobertura banco **98.7%** (resto honesto en `por_clasificar`).
* Alertas **solo deterministas** (`sin_factura`, `cuentas_por_cobrar`); lo
  interpretativo lo decidirá el Analista (T8, tabla separada).

### Persistencia Supabase (migraciones `001`–`005`, aplicadas)
`companies`, `bank_accounts`, `transactions` (+`rubro`), `cfdis`
(+`clave_prodserv/unidad`), `transaction_cfdi_matches`,
`accounts_receivable`, `financial_snapshots` (+`payload.signals`),
`alerts`, `customer_contacts`, `collection_actions`. RLS demo abierta
(endurecer con auth después). Patrón: SQL en `apps/api/migrations/` →
pegar en SQL Editor → `make db-load` → `make compute --all` (idempotentes).

### API actual (FastAPI, `:8000`)
`GET /health`, `/api/summary`, `/api/cfdis`, `/api/alerts`, `/api/signals`,
`/api/receivables`, `/api/matches`, `/api/collections/draft`,
`GET+POST /api/collections/contacts`, `POST /api/collections/send`
(parcial por diseño, guardas confirm + 24h + force). Todo con fallback a
seed local si Supabase no responde.

### Cobranza T9 (verificada con envío REAL de Resend)
Directorio lazy (`company_id, customer_rfc`, email NULLable) → aviso
`falta_email` → alta inline → envío → `collection_actions`. `MailProvider`
abstraído (`log`|`resend`). `/cobranza` funcional sin diseño.

---

## TIER 1 — SIGUIENTE: Agentes + MCP (OpenAI, con key disponible)

1. `agents/llm.py`: wrapper delgado (chat + tools + JSON estricto, sin
   frameworks). Flagship 5.x razona, mini ejecuta loops.
2. MCP in-process (FastMCP): banking, fiscal, financial y operaciones no-browser
   sobre funciones existentes (lista en spec #20).
3. Consultor `POST /api/chat` + `conversations/messages` (migración `006`).
4. Analista: señales → `analyst_insights` (tabla separada, spec acordado).
5. Contador: narración del cierre (el cálculo ya existe).

## TIER 2 — Ticket + browser (TUYO)
Flujo spec §3.3 caso 1 + §19, con datos y contratos ya listos:
* **Entrada**: foto de ticket → `extract_receipt` (Vision, JSON estricto:
  total, fecha, comercio, RFC si visible) → match con `reconcile.score`
  existente → perfil fiscal en `seed/company.json` (RFC `CNM160812AB1`, etc.).
* **Browser** (Playwright, árbol de accesibilidad, acciones tipadas,
  **prohibido coordenadas**): navega el portal real de facturación →
  frenos obligatorios (CAPTCHA, auth inesperada, datos faltantes, límite de
  pasos, **confirmación humana antes de emitir**) → CFDI → `reconcile_cfdi`
  → alerta resuelta.
* **Tuyo crear**: migración `007` (`documents`, `invoice_requests` con ese
  patrón), tablas con RLS demo, tests con 1 ticket + 1 portal reales
  (prohibido portales mock en el flujo principal).
* **Prerrequisitos tuyos**: foto de ticket + portal objetivo + usar
  `OPENAI_API_KEY` del `.env`. No toques `engine/` ni scores; reutiliza
  schemas (`Transaction`, `Cfdi`, `Match`, `Receivable`).

## TIER 3 — Cierre (otros / después)
* Dashboard diseñado (otra persona, contra `docs/ui-schema.md`; IA
  compositora elige tarjetas desde señales+alertas+insights al final).
* Deploy (Vercel/Railway, cuentas pendientes) + ensayo demo.

## Pendientes transversales
* `SUPABASE_SERVICE_ROLE_KEY` (opcional; hoy basta la publicable).
* Endurecer RLS al meter auth. `analyst_insights` nace en T8.
* `GET /api/transactions` no existe a propósito (detalle en CSV/Supabase).
