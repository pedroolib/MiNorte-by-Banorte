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
| `receivables_resolution` | `{ count: number; total: string }` | Alerta `cuentas_por_cobrar` → payload. Atajo curado del flujo de cobranza (layout fijo). |
| `receipts_resolution` | `{ count: number; total: string }` | Alerta `sin_factura` → payload. Atajo curado del flujo de facturas (layout fijo). |
| `action_card` | `{ eyebrow: string; title: string; body: string; value: string; action_label: string; tone?: string }` | Cualquier alerta (titulo + detalle + total). CTA genérica; las resolution son sus atajos curados. |
| `hero_number` | `{ label: string; sublabel: string; value: string; delta?: string; tone?: string }` | Summary + signals (valor ya formateado). |
| `multi_ring` | `{ items: { label: string; value: number }[] }` | signals (porcentajes 0–100). |
| `bars_total` | `{ title: string; total: string; values: number[]; labels: string[] }` | Serie mensual + total. |
| `progress_list` | `{ title: string; items: { label: string; percent: number }[] }` | Receivables por cliente / presupuesto. |
| `donut_total` | `{ title: string; center_value: string; center_label: string; segments: { label: string; value: number }[] }` | Efectivo + CxC (o deducible/no-deducible). |
| `entity_cluster` | `{ title: string; subtitle: string; items: { name: string }[]; action_label?: string }` | Top clientes (iniciales, sin fotos). |
| `waterfall` | `{ title: string; bars: { label: string; value: number }[] }` | Ventas − rubros = utilidad. |
| `insight_text` | `{ title: string; body: string; tone?: string; evidence?: string[] }` | `analyst_insights` (T8): texto + evidencia. |
| `metric_trend` | `{ label: string; value: string; change: string; values: number[]; tone?: string }` | signals (métrica + delta + serie). Una tarjeta, N métricas. |
| `transactions_list` | `{ items: [{ id: string; merchant: string; category: string; date: string; amount: string; type: "ingreso" \| "egreso" }] }` | Movimientos (drill-down/evidencia). |
| `timeline_list` | `{ items: [{ id: string; customer_name: string; due_date: string \| null; issued_at: string; amount_pending: string; status: string }] }` | CxC ordenadas: ¿a quién cobro ahora? |
| `tax_summary` | `{ isr_estimado: string; iva_neto: string; pct_deducible: number }` | Trío fiscal (ISR sin IVA al lado engaña). |
| `time_series` | `{ title: string; points: { label: string; income: number; expenses: number }[]; series: "income" \| "expenses" \| "both"; period_label?: string }` | `DashboardDailyPoint[]`. Sin selectores en v1 (el compositor pide otra tarjeta con distintas props). |
| `banorte_best_loans` | `{ amount: string; options: { id: string; nombre: string; tasa_anual: string; pago_mensual: string; costo_total: string; plazo_meses: number }[]; top_ids: string[]; rationale?: string }` | Tool `banorte_compare_loans` (opciones) + **top_ids y rationale los elige el Analista**. |

(Totales viajan como string porque son `Decimal` serializados; convertir
con `Number()` antes de formatear. `/cards` = galería con fixtures de cada
entrada; `/` = vista final curada. La galería NO es el UI final.)

## 3. Payloads reales de ejemplo (datos actuales del seed)

```json
{ "component": "receivables_resolution",
  "props": { "count": 5, "total": "76550.00" } }
```

```json
{ "component": "receipts_resolution",
  "props": { "count": 4, "total": "2123.00" } }
```

(Ojo: los totales viajan como string porque son `Decimal` serializados;
convertir con `Number()` antes de formatear.)

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

Crecimiento: `crec_ventas`, `crec_gastos`, `brecha_pp`,
`ticket_promedio/mediano_ingreso`, `clientes_activos_mes`,
`clientes_nuevos_mes`, `hhi_ingresos` (0–1).
Rentabilidad: `margen`, `margen_previo`, `margen_delta_pp`,
`margen_operativo_excl_comisiones`, `burn_multiple`, `regla_40`,
`operating_leverage` (None sin base).
Liquidez: `burn_mensual`, `efectivo`, `runway_dias`,
`cobertura_gastos_fijos`, `racha_signo` + `racha_meses`,
`volatilidad_flujo`, `dso_dias`.
Fiscal: `iva_trasladado`, `iva_acreditable`, `iva_neto`,
`pct_gasto_deducible`, `brecha_pagos_provision`.
Comercial: `cxc_total`, `cxc_count`, `cxc_antiguedad_promedio_dias`,
`cxc_pct_vencida` ("hoy" = fin de mes), `cxc_top_cliente`.
Estructura: `gasto_por_categoria`, `gasto_por_rubro` (por rubro: `total`,
`n_negocios`, `top1{nombre,total}`, `top1_share`, `hint_drill`),
`fondeo_interno`, `ratio_fondeo_interno`, `hhi_gasto_proveedores`,
`masa_salarial_estimada`.
Todo Decimal como string en JSON; `None` donde no hay base.

Investigación progresiva (herramientas del Consultor): Nivel 0 = signals
con hints; Nivel 1 = `get_merchants(rubro?, min_total?, limit?)`;
Nivel 2 = `get_merchant_detail(nombre)` (serie mensual + recurrencia).
Comercios se agrupan por NOMBRE (entidad); los RFCs se reservan para
joins de contacto.

Nota de arquitectura: las tarjetas finales las elige la IA compositora a
partir de señales + alertas + su interpretación (tabla separada
`analyst_insights` en T8). Este catálogo define los componentes disponibles,
no cuáles se muestran.

## 6. Roadmap (no construir aún)

* `cash_runway` (días de caja: hoy 4), `tax_estimate`, `chat` del Consultor.
* Validación con zod + Structured Outputs cuando llegue la IA (T8).
