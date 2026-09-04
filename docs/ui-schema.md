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

## 2. Catálogo actual (`apps/web/lib/ui-schema.ts`)

| `component` | `props` | Quién lo emite hoy |
|---|---|---|
| `receivables_resolution` | `{ total_pending: number, invoices: unknown[] }` | Alerta `cuentas_por_cobrar` (`GET /api/alerts` → `payload`) |
| `receipts_resolution` | `{ count: number, total: number }` | Alerta `sin_factura` (`GET /api/alerts` → `payload`) |
| `loan_comparison` | `{ amount: number }` | Reservado (Consultor T8) |
| `hiring_simulation` | `{ monthly_cost: number }` | Reservado (Consultor T8) |

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
* `GET /api/alerts?month=2026-08` — alertas con `payload.component`.
* `GET /api/receivables` — las 5 CxC con cliente, monto, vencimiento.
* `GET /api/matches?status=unmatched` — los 4 gastos sin factura.
* Detalle fila-por-fila: `seed/transactions.csv` + tablas Supabase.

## 6. Roadmap (no construir aún)

* `cash_runway` (días de caja: hoy 4), `tax_estimate`, `chat` del Consultor.
* Validación con zod + Structured Outputs cuando llegue la IA (T8).
