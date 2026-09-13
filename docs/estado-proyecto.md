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
4. Analista ✅: `agents/analyst.py` (EXACTAMENTE 10 insights, una sola
   llamada). Regla de hierro: ningún dato sale del modelo — meses vía
   `get_months_with_data` (nueva tool MCP), valores de evidencia
   SOBRESCRITOS con `get_signals` antes de guardar; mes vacío → 422 sin
   gastar LLM. Insights con `family`/`financial_impact`/`actionability` +
   `anchor_analysis[4]` (solo comentarios; números los pone composición).
   Guardas: catálogo exacto, sin-None, kind único, veto a comparativos con
   1 mes, anti-duplicación de reservadas. Reintento combinado; si persiste,
   falla sin guardar. Orden critical→warning→info.
   Verificado en vivo vs motor: 0 discrepancias (piloto 2026-07).
   Motor: CxC se agrupa por RFC con fallback a nombre si es genérico
   (XAXX/XAXE) o vacío (`_entidad_cfdi`); RFC genérico nunca es llave.
5. Composition Engine ✅ + workspace ✅: `app/composition.py`
   (4 anchors con trend % en código + comentario, acciones condicionales
   con regla obligatoria, discovery con scoring del spec + diversidad
   máx 2/familia, `weekly_summary` al componer) + `GET /api/dashboard/gen`
   idempotente por semana + memoria `insight_exposures` +
   `dashboard_compositions` (migraciones 011/012 aplicadas).
   `/` es el workspace: weekly + consultant_view temporal (ask-bar,
   `POST /api/chat` devuelve `tarjetas` (consultant_view: cantidad libre
   sin `insight_text`, valores por `=ruta` MCP + `validar_cifras` verbatim +
   corrección determinista ±5% o reescritura; texto verificado igual) + deep_dive (`GET /api/drill`) +
   barra compacta (`GET /api/critical-bar`) + escenarios guardados
   (`POST|GET /api/scenarios`, migración 013 — aplicar en SQL Editor).
   `financial_anchor` en catálogo: 18.
   Diseñador ✅ endurecido: `PROPS_SCHEMAS` espejo de `ui-schema.ts`
   (18 componentes incl. financial_anchor, listas no vacías, extras
   permitidos), footnote ≤140 chars y sin tecnicismos (HHI, DSO, burn…),
   combinado con schemas de props en el prompt; si persiste, `LLMError`
   sin parcial. Variedad: mapa kind→componente + `footnote?` en 8
   componentes visuales (tipos + render + fixtures + doc) + tope 2
   `insight_text` por diseño + garantía 1:1 insight→tarjeta (faltantes al
   reintento). Modelos: loops de tools usan `OPENAI_TOOL_MODEL`
   (mini; los reasoning nuevos rechazan function tools) y la elección
   de tarjetas usa flagship (`chat_json` sin tools sí lo acepta);
   `chat_json(..., strict=False)` para schemas con props libres.
   Verificado: astra genera títulos accionables y variedad real
   (hero/donut/bars/action_card); footnote aún sin uso espontáneo. Reservadas SIEMPRE deterministas (`reserved_cards`):
   `tax_summary` (nueva señal `isr_estimado`), `receipts_resolution` y
   `receivables_resolution` (payloads de alertas); el Diseñador las tiene
   prohibidas y el Analista avisado de no duplicar sus totales.
   `POST /api/analyst/run` idempotente + `GET /api/analyst/insights`
   (tabla `010_analyst_insights.sql` — aplicar en SQL Editor).
5. Diseñador ✅: `agents/designer.py` (insights → tarjetas del catálogo
   congelado, validación determinista). Descubre por `metric_catalog` +
   `get_metric` (+ endpoint `GET /api/metric`); nombre inexistente devuelve
   el catálogo, nunca null. Mapper determinista adelgazado a lo mecánico
   (`sin_factura`, `cuentas_por_cobrar`); resto al Diseñador con fallback
   `insight_text`.
6. Contador: narración del cierre (el cálculo ya existe).

## TIER 2 — Ticket + browser (HECHO, branch `feature/tickets-engine`)
Engine + endpoints + Browser Agent real implementados y probados (146
tests backend, incl. `test_receipts.py` con Playwright real contra una
página local); falta correrlo en vivo contra un portal y comercio reales
(requiere `OPENAI_API_KEY` real en `.env`, que este entorno no tenía) y
el pulido visual de `/tickets` (hoy es crudo, como `/cobranza`).

* `app/integrations/invoicing/vision.py`: `extract_receipt` (Vision, JSON
  estricto: comercio/RFC/total/fecha/folio, campo no legible = null).
* `app/operator/receipts.py`: `match_candidates` reutiliza tal cual
  `reconcile.amount_score/date_score/merchant_score` (no se tocó el
  motor); `build_invoice_payload` nunca inventa datos; `reconcile_cfdi`
  parsea el XML real devuelto por el portal con el parser SAT existente.
* `app/browser/agent.py` + `actions.py`: Browser Agent con Playwright
  (accesibilidad real: rol/label/tipo, **cero coordenadas**), un tool-call
  a OpenAI por paso, límite de pasos, frenos por CAPTCHA/auth inesperada/
  dato faltante, y **nunca autoconfirma** una acción irreversible
  (heurística por keyword + `type=submit`): se detiene en
  `esperando_confirmacion` hasta `POST /api/tickets/{id}/confirm`.
* `POST /api/tickets/upload`, `POST /api/tickets`, `GET /api/tickets(/{id})`,
  `POST /api/tickets/{id}/{start,confirm,cancel,reconcile}` — mismo patrón
  503-sin-Supabase que el resto de la API.
* Migración `013_tickets.sql` (`documents`, `invoice_requests`, RLS demo).
* MCP: `extract_receipt`, `match_receipt_to_transaction`,
  `get_fiscal_profile`, `prepare_invoice_request` (el envío/reconciliación
  reales exigen confirmación humana en la UI, no viven en el loop de tools).
* `/tickets`: cámara real del dispositivo (`getUserMedia`, con fallback
  `<input capture>`) -> match -> bitácora del agente -> aprobar/rechazar.

Pendiente original de referencia (spec §3.3 caso 1 + §19):
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
* Endurecer RLS al meter auth. `analyst_insights` nace aplicada en
  Supabase con `migrations/010_analyst_insights.sql` (pendiente aplicar).
* `GET /api/transactions` no existe a propósito (detalle en CSV/Supabase).

## Modelos IA (todo gpt-6-astra)
* Tool-calling vía `/v1/responses` (`OPENAI_TOOLS_API=responses`,
  `reasoning.effort=low`): astra rechaza function tools en
  chat/completions a cualquier effort ('none' tampoco lo acepta).
  `OPENAI_TOOL_MODEL` elige el modelo del loop.
* `chat()` con fallback automático (reasoning_effort/temperature) por si
  cambias de modelo. Verificado en vivo todo-astra: $98,500.00 exactos,
  2 tarjetas (hero + bars), 0 discrepancias.

## Proyecciones (motor + tool + regla)
* `engine.project_next_month`: promedio últimos ≤3 meses con datos (misma
  base que signals), confianza alta/media/baja + supuestos + base_meses.
  1 mes = run-rate declarado; mes vacío = sin_base (nunca inventa).
* Tool MCP `project_next_month` (+ server): ÚNICA vía para hablar de futuro.
  Consultor: sin llamarla prohibido proyectar; al darla declara método,
  confianza y supuestos, todo marcado estimado.
* Verificado en vivo: julio→agosto con base feb+jul (el piloto creció a
  2 meses: 142 txns feb + 221 jul), -$15,266.57 confianza media + 3 tarjetas.
* Ojo: `GET /api/summary` (snapshot) vs `signals()` (live) difieren
  (utilidad jul 39,252.50 vs 47,994.28): convenciones distintas
  (operativo-sin-internos vs motor). Proyecciones usan signals (live).
  Pendiente unificar o documentar la diferencia.
