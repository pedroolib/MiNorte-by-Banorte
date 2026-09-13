# Contrato UI generativa — MiNorte (spec #22)

Para la persona de diseño/frontend. La IA compositora llega al final (T8+);
este documento define el contrato para trabajar en paralelo desde hoy.

## 1. La regla de oro

```text
LLM → JSON (UISchema) → Component Registry → React
```

El modelo **nunca** devuelve JSX. Devuelve un JSON con `component` + `props`,
y `components/registry.tsx` decide qué componente React renderizar.
Si el `component` no existe en el registry, se muestra fallback, nunca crashea.

## 2. Catálogo (congelado: doc = tipos = registry = fixtures)

| `component` | `props` | Fuente |
|---|---|---|
| `data_table` | `{ title: string; columns: string[]; rows: (string \| number)[][]; footnote?: string }` | Listados (clientes, facturas, movimientos). Números se formatean es-MX; strings tal cual. |
| `financial_anchor` | `{ metric: string; label: string; value: number \| string \| null; trend: { direction: "up" \| "down" \| "flat"; percentage: number } \| null; analyst_comment: string }` | `GET /api/dashboard/gen` → `anchors[]` (número del motor + comentario del Analista). |
| `receivables_resolution` | `{ count: number; total: string }` | Alerta `cuentas_por_cobrar` → payload. Atajo curado del flujo de cobranza (layout fijo). |
| `receipts_resolution` | `{ count: number; total: string }` | Alerta `sin_factura` → payload. Atajo curado del flujo de facturas (layout fijo). |
| `action_card` | `{ eyebrow: string; title: string; body: string; value: string; action_label: string; tone?: string; icon?: string }` | Cualquier alerta (titulo + detalle + total). CTA genérica; las resolution son sus atajos curados. `icon` (receipt, wallet, flame, piggy-bank, trending-down, file-warning, landmark, bell) pinta el panel visual lateral; lo elige el Diseñador de la allowlist. |
| `hero_number` | `{ label: string; sublabel: string; value: string; delta?: string; tone?: string }` | Summary + signals (valor ya formateado). |
| `multi_ring` | `{ items: { label: string; value: number }[]; footnote?: string }` | signals (porcentajes 0–100). |
| `bars_total` | `{ title: string; total: string; values: number[]; labels: string[]; footnote?: string }` | Serie mensual + total. |
| `progress_list` | `{ title: string; items: { label: string; percent: number }[]; footnote?: string }` | Receivables por cliente / presupuesto. |
| `donut_total` | `{ title: string; center_value: string; center_label: string; segments: { label: string; value: number }[]; footnote?: string }` | Efectivo + CxC (o deducible/no-deducible). |
| `entity_cluster` | `{ title: string; subtitle: string; items: { name: string }[]; action_label?: string; footnote?: string }` | Top clientes (iniciales, sin fotos). |
| `waterfall` | `{ title: string; bars: { label: string; value: number }[]; footnote?: string }` | Ventas − rubros = utilidad. |
| `insight_text` | `{ title: string; body: string; tone?: string; evidence?: string[] }` | `analyst_insights` (T8): texto + evidencia. |
| `metric_trend` | `{ label: string; value: string; change: string; values: number[]; tone?: string; footnote?: string }` | signals (métrica + delta + serie). Una tarjeta, N métricas. |
| `transactions_list` | `{ items: [{ id: string; merchant: string; category: string; date: string; amount: string; type: "ingreso" \| "egreso" }] }` | Movimientos (drill-down/evidencia). |
| `timeline_list` | `{ items: [{ id: string; customer_name: string; due_date: string \| null; issued_at: string; amount_pending: string; status: string }] }` | CxC ordenadas: ¿a quién cobro ahora? |
| `tax_summary` | `{ isr_estimado: string; iva_neto: string; pct_deducible: number }` | Trío fiscal (ISR sin IVA al lado engaña). |
| `time_series` | `{ title: string; points: { label: string; income: number; expenses: number }[]; series: "income" \| "expenses" \| "both"; period_label?: string; footnote?: string }` | `DashboardDailyPoint[]`. Sin selectores en v1 (el compositor pide otra tarjeta con distintas props). |
| `banorte_best_loans` | `{ amount: string; options: { id: string; nombre: string; tasa_anual: string; pago_mensual: string; costo_total: string; plazo_meses: number }[]; top_ids: string[]; rationale?: string }` | Tool `banorte_compare_loans` (opciones) + **top_ids y rationale los elige el Analista**. |

(Totales viajan como string porque son `Decimal` serializados; convertir
con `Number()` antes de formatear. `/cards` = galería con fixtures de cada
entrada; `/` = vista final curada. La galería NO es el UI final.)

`footnote?` (en los 8 visuales marcados): pie opcional de 1 frase con la
interpretación del dato. Render: párrafo gris sutil (`text-xs
text-neutral-500`, margen superior) al pie de la tarjeta. El Diseñador lo
manda cuando el número solo no se explica; si falta, no se reserva espacio.

## 3. Payloads reales de ejemplo (datos actuales del seed)

```json
{ "component": "receivables_resolution",
  "props": { "count": 5, "total": "76550.00" } }
```

```json
{ "component": "receipts_resolution",
  "props": { "count": 4, "total": "2123.00" } }
```

```json
{ "component": "donut_total",
  "props": { "title": "Efectivo vs por cobrar",
             "center_value": "$77,844.68", "center_label": "Liquidez total",
             "segments": [{ "label": "Efectivo", "value": 1294.68 },
                          { "label": "Por cobrar", "value": 76550.0 }],
             "footnote": "El 98% de la liquidez está por cobrar, no en caja." } }
```

(Ojo: los totales viajan como string porque son `Decimal` serializados;
convertir con `Number()` antes de formatear. Los visuales aceptan números
o strings numéricos: el render ya coacciona con `num()`.)

## 4. Reglas para diseñar componentes

1. **Props = datos, no copy.** Los textos finales (`titulo`, `detalle` de la
   alerta) los reescribirá la IA; no quemes frases en el componente.
   El componente solo estructura: números, botón Resolver, estados.
2. **Estados obligatorios** por componente: loading / con datos / vacío / error.
3. **El botón Resolver** es acción, no navegación: en el futuro dispara el
   Operator Agent (T9/T10). Por ahora puede ser visual.
4. **Números en es-MX, moneda MXN**, fechas ISO `America/Mexico_City`.
5. Para agregar un componente: créalo en `components/registry.tsx`,
   regístralo en `REGISTRY` y extiende el tipo `UISchema` en `lib/ui-schema.ts`.

## 5. Fuentes de datos (ver todo crudo en `/debug`)

* `GET /api/summary` — métricas del mes.
* `GET /api/alerts?month=2026-08` — alertas **deterministas** con `payload.component`.
* `GET /api/signals?month=2026-08` — señales numéricas (abajo), es lo que
  la IA recibe para decidir qué tarjetas mostrar.
* `GET /api/receivables` — las 5 CxC con cliente, monto, vencimiento.
* `GET /api/matches?status=unmatched` — los 4 gastos sin factura.
* Detalle fila-por-fila: `seed/transactions.csv` + tablas Supabase.

### Catálogo `signals()` (contrato para el Analista T8)

Base: `ventas`, `gastos`, `utilidad`, `tiene_datos`, `n_movimientos`.
Crecimiento: `crec_ventas`, `crec_gastos`, `brecha_pp`,
`ticket_promedio/mediano_ingreso`, `clientes_activos_mes`,
`clientes_nuevos_mes`, `hhi_ingresos` (0–1).
Rentabilidad: `margen`, `margen_previo`, `margen_delta_pp`,
`margen_operativo_excl_comisiones`, `burn_multiple`, `regla_40`,
`operating_leverage` (None sin base).
Liquidez: `burn_mensual`, `efectivo`, `runway_dias`,
`cobertura_gastos_fijos`, `racha_signo` + `racha_meses`,
`volatilidad_flujo`, `dso_dias`.
Fiscal: `iva_trasladado`, `iva_acreditable`, `iva_neto`, `isr_estimado`,
`pct_gasto_deducible`, `brecha_pagos_provision`.
Comercial: `cxc_total`, `cxc_count`, `cxc_antiguedad_promedio_dias`,
`cxc_pct_vencida` ("hoy" = fin de mes), `cxc_top_cliente` (por RFC, con
fallback a nombre si el RFC es genérico XAXX/XAXE o vacío).
Estructura: `gasto_por_categoria`, `gasto_por_rubro` (por rubro: `total`,
`n_negocios`, `top1{nombre,total}`, `top1_share`, `hint_drill`),
`margen_bruto_proxy`, `fondeo_interno`, `ratio_fondeo_interno`,
`hhi_gasto_proveedores`, `masa_salarial_estimada`.
Todo Decimal como string en JSON; `None` donde no hay base.

Investigación progresiva (herramientas del Consultor): Nivel 0 = signals
con hints; Nivel 1 = `get_merchants(rubro?, min_total?, limit?)`;
Nivel 2 = `get_merchant_detail(nombre)` (serie mensual + recurrencia).
Comercios se agrupan por NOMBRE (entidad); los RFCs se reservan para
joins de contacto.

Nota de arquitectura: las tarjetas finales las elige el Diseñador
(`app/agents/designer.py`) a partir de insights rankeados. Flujo:
Analista (qué importa) → mapper determinista (solo `sin_factura` y
`cuentas_por_cobrar`, lo mecánico) → Diseñador (solo lo ambiguo, con
`metric_catalog` + `get_metric`, fallback `insight_text`).

El Diseñador nunca inventa cifras: resuelve por nombre exacto del
catálogo (`metric_catalog()` en motor, `GET /api/metric` en API);
nombre inexistente devuelve el catálogo, no null.

## 6. Dashboard generativo (`GET /api/dashboard/gen`)

El endpoint devuelve el JSON listo para renderizar (sin página aún).
Parámetros: `month=YYYY-MM` (default: último con datos), `week=YYYY-Www`
(default: semana actual). Idempotente por semana: si ya existe, la devuelve
sin gastar LLM.

```json
{ "month": "2026-07", "week_id": "2026-W41",
  "anchors": [ ... 4 ... ],
  "actions": [ ... 0-3 ... ],
  "discovery": [ ... 2-5 ... ],
  "summary": "2-3 frases que conectan lo visible" }
```

### 6.1 Anchors (siempre 4, con comentario)

Cada anchor trae número del motor + comentario del Analista:

```json
{ "metric": "revenue", "label": "Ventas", "value": 524769.98,
  "trend": null,
  "analyst_comment": "Los cobros del taller están distribuidos de forma desigual..." }
```

`metric` es uno de `revenue` (ventas), `profit` (utilidad), `cash`
(efectivo), `estimated_tax` (isr_estimado). `value` es número o null.
`trend` es `{"direction": "up"|"down"|"flat", "percentage": 8.0}` calculado
en código mes-vs-mes, o `null` honesto si no hay mes previo (piloto: 1 mes).
Se renderiza con el componente `financial_anchor` del catálogo (label +
valor grande + `Badge` de trend + comentario como subtexto).

### 6.2 Actions (0–3) y discovery (2–5)

- `actions`: `receipts_resolution` / `receivables_resolution` SOLO si hay
  algo que resolver (vienen de alertas deterministas; nunca las pide el
  modelo) + hasta completar 3 con hallazgos críticos accionables. Si hay
  pendientes, al menos 1 entra siempre.
- `discovery`: tarjetas del Diseñador que rotan semanalmente (novedad y
  penalización por repetición con memoria `insight_exposures`). Máximo 2
  por familia; máximo 2 `insight_text` por diseño; 1 tarjeta por insight.
- `tax_summary` NO aparece como tarjeta: sus números viven en el anchor
  `estimated_tax`.
- Toda tarjeta trae `insight_id` (trazabilidad al insight que la originó)
  y `rationale` (por qué se eligió ese componente). `tone` usa
  `positive` | `watch` | `urgent` | `neutral`.
- `summary`: lo genera el sistema con las tarjetas visibles como contexto;
  solo conecta lo visible, sin cifras nuevas.

Ejemplo real (piloto julio, semana W41): 4 anchors + `receipts_resolution`
(46, $111,300.13) + `receivables_resolution` (5, $98,500) + 1 action_card
+ 4 discovery (donut_total, bars_total, multi_ring, hero_number… según la
semana). Sin problemas: 4 anchors + 4–5 discovery, sin placeholders ni
tarjetas vacías.

## 7. Roadmap (estado real)

* Hecho (T8): Analista (10 insights + anchors con evidencia), Diseñador
  (1:1 con validación y reintento), Composition Engine
  (`GET /api/dashboard/gen`), Consultor (`/chat`), cobranza (T9).
* Pendiente frontend: selector de semana/mes en la UI (hoy siempre semana
  actual) + auth/RLS + deploy + más meses de datos del piloto.
* Hecho frontend: `/` renderiza `GET /api/dashboard/gen` con `DynamicUI`
  (anchors + acciones + discovery + summary, sin filtros); `financial_anchor`
  en tipos + registry + fixtures + esta tabla (catálogo: 18).
* Pendiente general: auth/RLS, deploy, más meses de datos del piloto.
