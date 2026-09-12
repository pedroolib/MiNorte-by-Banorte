"use client";

import React from "react";

/**
 * Catálogo de tarjetas MiNorte (presentacionales, sin datos quemados).
 * Cada una recibe SOLO props tipadas en `lib/ui-schema.ts`.
 * Reglas: números es-MX, moneda MXN, estados loading/vacío/error los maneja
 * el composer (aquí: guardas mínimas "Sin datos").
 */

const fmtInt = new Intl.NumberFormat("es-MX", { maximumFractionDigits: 0 });
const fmtMoney0 = new Intl.NumberFormat("es-MX", {
  style: "currency",
  currency: "MXN",
  maximumFractionDigits: 0,
});
const num = (v: unknown) => Number(v ?? 0);
const money = (v: unknown) => fmtMoney0.format(num(v));

function Empty({ what }: { what: string }) {
  return <p className="text-sm text-neutral-500">Sin datos de {what}.</p>;
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

/* ---------------- hero_number ---------------- */

export function HeroNumber({
  label,
  sublabel,
  value,
  delta,
  tone = "neutral",
}: {
  label: string;
  sublabel: string;
  value: string;
  delta?: string;
  tone?: "positive" | "negative" | "neutral";
}) {
  const deltaColor =
    tone === "positive"
      ? "text-green-600"
      : tone === "negative"
        ? "text-red-600"
        : "text-neutral-500";
  return (
    <div className="rounded-xl border bg-white p-5">
      <p className="text-sm font-medium text-neutral-900">{label}</p>
      <p className="text-xs text-neutral-500">{sublabel}</p>
      <p className="mt-3 text-4xl font-bold tracking-tight">{value}</p>
      {delta ? <p className={`mt-2 text-sm font-semibold ${deltaColor}`}>{delta}</p> : null}
    </div>
  );
}

/* ---------------- multi_ring ---------------- */

export function MultiRing({ items, footnote }: { items: { label: string; value: number }[]; footnote?: string }) {
  if (!items.length) return <Empty what="indicadores" />;
  const colors = ["#16a34a", "#7c3aed", "#eb0029", "#d97706"];
  const R = 54;
  return (
    <div className="rounded-xl border bg-white p-5">
      <div className="flex items-center justify-center gap-6">
        <svg width="140" height="140" viewBox="0 0 140 140" role="img" aria-label="Indicadores">
          {items.slice(0, 3).map((item, i) => {
            const r = R - i * 18;
            return (
              <circle
                key={`t-${item.label}`}
                cx="70"
                cy="70"
                r={r}
                fill="none"
                stroke="#eef0f2"
                strokeWidth="10"
              />
            );
          })}
          {items.slice(0, 3).map((item, i) => {
            const r = R - i * 18;
            const c = 2 * Math.PI * r;
            const frac = Math.max(0, Math.min(1, num(item.value) / 100));
            return (
              <circle
                key={item.label}
                cx="70"
                cy="70"
                r={r}
                fill="none"
                stroke={colors[i % colors.length]}
                strokeWidth="10"
                strokeLinecap="round"
                strokeDasharray={`${frac * c} ${c}`}
                transform="rotate(-90 70 70)"
              />
            );
          })}
          <text x="70" y="66" textAnchor="middle" fontSize="20" fontWeight="800">
            {Math.round(num(items[0]?.value))}%
          </text>
          <text x="70" y="84" textAnchor="middle" fontSize="10" fill="#697079">
            {items[0]?.label}
          </text>
        </svg>
        <ul className="space-y-2 text-sm">
          {items.map((item, i) => (
            <li key={item.label} className="flex items-center gap-2">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: colors[i % colors.length] }}
              />
              <span className="text-neutral-500">{item.label}</span>
              <strong>{Math.round(num(item.value))}%</strong>
            </li>
          ))}
        </ul>
      </div>
      {footnote ? <p className="mt-3 text-xs text-neutral-500">{footnote}</p> : null}
    </div>
  );
}

/* ---------------- bars_total ---------------- */

export function BarsTotal({
  title,
  total,
  values,
  labels,
  footnote,
}: {
  title: string;
  total: string;
  values: number[];
  labels: string[];
  footnote?: string;
}) {
  if (!values.length) return <Empty what="periodos" />;
  const max = Math.max(...values.map(num), 1);
  return (
    <div className="rounded-xl border bg-white p-5">
      <p className="text-sm text-neutral-500">{title}</p>
      <p className="text-3xl font-bold tracking-tight">{total}</p>
      <div className="mt-4 flex h-28 items-end gap-2">
        {values.map((v, i) => (
          <div key={labels[i] ?? i} className="flex flex-1 flex-col items-center gap-1">
            <div
              className={`w-full rounded ${i === values.length - 1 ? "bg-violet-700" : "bg-violet-200"}`}
              style={{ height: `${Math.max(6, (num(v) / max) * 100)}%` }}
            />
            <span className="text-[10px] text-neutral-500">{labels[i] ?? ""}</span>
          </div>
        ))}
      </div>
      {footnote ? <p className="mt-3 text-xs text-neutral-500">{footnote}</p> : null}
    </div>
  );
}

/* ---------------- progress_list ---------------- */

export function ProgressList({
  title,
  items,
  footnote,
}: {
  title: string;
  items: { label: string; percent: number }[];
  footnote?: string;
}) {
  if (!items.length) return <Empty what="partidas" />;
  return (
    <div className="rounded-xl border bg-white p-5">
      <p className="text-sm font-medium text-neutral-900">{title}</p>
      <div className="mt-3 space-y-3">
        {items.map((item) => {
          const pct = Math.max(0, Math.min(100, num(item.percent)));
          return (
            <div key={item.label}>
              <div className="flex justify-between text-xs">
                <span className="font-medium">{item.label}</span>
                <span className="text-violet-700">{Math.round(pct)}%</span>
              </div>
              <div className="mt-1 h-1.5 rounded bg-neutral-100">
                <div className="h-1.5 rounded bg-violet-700" style={{ width: `${pct}%` }} />
              </div>
            </div>
          );
        })}
      </div>
      {footnote ? <p className="mt-3 text-xs text-neutral-500">{footnote}</p> : null}
    </div>
  );
}

/* ---------------- donut_total ---------------- */

export function DonutTotal({
  title,
  center_value,
  center_label,
  segments,
  footnote,
}: {
  title: string;
  center_value: string;
  center_label: string;
  segments: { label: string; value: number }[];
  footnote?: string;
}) {
  const total = segments.reduce((s, x) => s + num(x.value), 0);
  if (!segments.length || total <= 0) return <Empty what="segmentos" />;
  const colors = ["#f59e0b", "#d9dde1", "#34383e", "#9da4ac"];
  let cursor = 0;
  const stops = segments
    .map((s, i) => {
      const start = cursor;
      cursor += (num(s.value) / total) * 100;
      return `${colors[i % colors.length]} ${start}% ${cursor}%`;
    })
    .join(",");
  return (
    <div className="rounded-xl border bg-white p-5">
      <p className="text-sm font-medium text-neutral-900">{title}</p>
      <div className="mt-3 flex items-center gap-5">
        <div
          className="grid h-28 w-28 place-items-center rounded-full"
          style={{ background: `conic-gradient(${stops})` }}
        >
          <div className="grid h-16 w-16 place-items-center rounded-full bg-white text-center">
            <div>
              <p className="text-sm font-bold">{center_value}</p>
              <p className="text-[10px] text-neutral-500">{center_label}</p>
            </div>
          </div>
        </div>
        <ul className="space-y-2 text-xs">
          {segments.map((s, i) => (
            <li key={s.label} className="flex items-center gap-2">
              <span
                className="inline-block h-2 w-2 rounded-sm"
                style={{ background: colors[i % colors.length] }}
              />
              <span className="text-neutral-500">{s.label}:</span>
              <strong>{money(s.value)}</strong>
            </li>
          ))}
        </ul>
      </div>
      {footnote ? <p className="mt-3 text-xs text-neutral-500">{footnote}</p> : null}
    </div>
  );
}

/* ---------------- entity_cluster ---------------- */

export function EntityCluster({
  title,
  subtitle,
  items,
  action_label,
  footnote,
}: {
  title: string;
  subtitle: string;
  items: { name: string }[];
  action_label?: string;
  footnote?: string;
}) {
  if (!items.length) return <Empty what="entidades" />;
  const shown = items.slice(0, 4);
  const rest = items.length - shown.length;
  return (
    <div className="rounded-xl border bg-white p-5 text-center">
      <div className="flex items-center justify-center">
        {shown.map((item, i) => (
          <span
            key={item.name}
            title={item.name}
            className={`grid h-10 w-10 place-items-center rounded-full border-2 border-white text-xs font-bold ${
              i === 1 ? "h-14 w-14 bg-violet-100 text-violet-800" : "bg-neutral-100 text-neutral-700"
            } ${i > 0 ? "-ml-3" : ""}`}
          >
            {initials(item.name)}
          </span>
        ))}
        {rest > 0 && (
          <span className="-ml-3 grid h-10 w-10 place-items-center rounded-full border-2 border-white bg-violet-100 text-xs font-bold text-violet-800">
            +{rest}
          </span>
        )}
      </div>
      <p className="mt-3 text-sm font-medium">{title}</p>
      <p className="text-xs text-neutral-500">{subtitle}</p>
      {action_label ? (
        <button className="mt-3 rounded-lg border px-3 py-1 text-xs font-semibold">
          {action_label}
        </button>
      ) : null}
      {footnote ? <p className="mt-3 text-xs text-neutral-500">{footnote}</p> : null}
    </div>
  );
}

/* ---------------- action_card ---------------- */

export function ActionCard({
  eyebrow,
  title,
  body,
  value,
  action_label,
  tone = "neutral",
}: {
  eyebrow: string;
  title: string;
  body: string;
  value: string;
  action_label: string;
  tone?: "urgent" | "watch" | "neutral";
}) {
  const dark = tone === "urgent" ? "bg-red-950 text-white" : tone === "watch" ? "bg-amber-950 text-white" : "bg-white";
  return (
    <div className={`rounded-xl border p-5 ${dark}`}>
      <p className="text-[10px] font-bold uppercase tracking-widest opacity-70">{eyebrow}</p>
      <h2 className="mt-1 text-lg font-bold">{title}</h2>
      <p className="mt-1 text-3xl font-extrabold">{value}</p>
      <p className="mt-2 text-sm opacity-80">{body}</p>
      <button className="mt-4 w-full rounded-lg bg-red-600 px-3 py-2 text-sm font-bold text-white">
        {action_label}
      </button>
    </div>
  );
}

/* ---------------- time_series ---------------- */

function smoothPath(pts: { x: number; y: number }[]) {
  if (pts.length < 2) return "";
  if (pts.length === 2) return `M${pts[0].x},${pts[0].y} L${pts[1].x},${pts[1].y}`;
  let d = `M${pts[0].x},${pts[0].y}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(pts.length - 1, i + 2)];
    const c1x = p1.x + (p2.x - p0.x) / 6;
    const c1y = p1.y + (p2.y - p0.y) / 6;
    const c2x = p2.x - (p3.x - p1.x) / 6;
    const c2y = p2.y - (p3.y - p1.y) / 6;
    d += ` C${c1x},${c1y} ${c2x},${c2y} ${p2.x},${p2.y}`;
  }
  return d;
}

export function TimeSeries({
  title,
  points,
  series,
  period_label,
  footnote,
}: {
  title: string;
  points: { label: string; income: number; expenses: number }[];
  series: "income" | "expenses" | "both";
  period_label?: string;
  footnote?: string;
}) {
  if (!points.length) return <Empty what="movimientos" />;
  const vals = points.map((p) =>
    series === "income" ? num(p.income) : series === "expenses" ? num(p.expenses) : num(p.income) - num(p.expenses),
  );
  const max = Math.max(...vals, 1);
  const min = Math.min(...vals, 0);
  const W = 300;
  const H = 120;
  const PAD = 8;
  const X = (i: number) => PAD + (i / Math.max(points.length - 1, 1)) * (W - PAD * 2);
  const Y = (v: number) => PAD + (1 - (v - min) / Math.max(max - min, 1)) * (H - PAD * 2);
  const pts = vals.map((v, i) => ({ x: X(i), y: Y(v) }));
  const d = smoothPath(pts);
  const minIdx = vals.indexOf(Math.min(...vals));
  const color = series === "expenses" ? "#059669" : "#7c3aed";
  return (
    <div className="rounded-xl border bg-white p-5">
      <div className="flex items-baseline justify-between">
        <p className="text-sm font-medium text-neutral-900">{title}</p>
        {period_label ? <span className="text-xs text-neutral-400">{period_label}</span> : null}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 block w-full" role="img" aria-label={title}>
        <path d={`${d} L${X(points.length - 1)},${H} L${X(0)},${H} Z`} fill={color} opacity=".09" />
        <path d={d} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" />
        <circle cx={pts[minIdx].x} cy={pts[minIdx].y} r="3.5" fill="#fff" stroke={color} strokeWidth="2" />
        <text x={Math.min(Math.max(pts[minIdx].x, 52), W - 52)} y={Math.max(pts[minIdx].y - 10, 12)} textAnchor="middle" fontSize="9" fill="#697079">
          Mín: {money(vals[minIdx])}
        </text>
      </svg>
      <div className="mt-1 flex justify-between text-[10px] text-neutral-500">
        {points.map((p) => (
          <span key={p.label}>{p.label}</span>
        ))}
      </div>
      {footnote ? <p className="mt-3 text-xs text-neutral-500">{footnote}</p> : null}
    </div>
  );
}

/* ---------------- banorte_best_loans ---------------- */

export function BanorteBestLoans({
  amount,
  options,
  top_ids,
  rationale,
}: {
  amount: string;
  options: {
    id: string;
    nombre: string;
    tasa_anual: string;
    pago_mensual: string;
    costo_total: string;
    plazo_meses: number;
  }[];
  top_ids: string[];
  rationale?: string;
}) {
  if (!options.length) return <Empty what="opciones de crédito" />;
  return (
    <div className="rounded-xl border bg-white p-5">
      <p className="text-sm font-medium text-neutral-900">Créditos Banorte para ti</p>
      <p className="text-xs text-neutral-500">Monto solicitado: {money(amount)}</p>
      <div className="mt-3 space-y-2">
        {options.map((o) => {
          const top = top_ids.includes(o.id);
          return (
            <div
              key={o.id}
              className={`rounded-lg border p-3 ${top ? "border-violet-700 bg-violet-50" : ""}`}
            >
              <div className="flex items-center justify-between text-sm">
                <strong>{o.nombre}</strong>
                {top ? (
                  <span className="rounded bg-violet-700 px-2 py-0.5 text-[10px] font-bold text-white">
                    RECOMENDADO
                  </span>
                ) : null}
              </div>
              <div className="mt-1 flex gap-4 text-xs text-neutral-500">
                <span>Tasa {(Number(o.tasa_anual) * 100).toFixed(2)}%</span>
                <span>{o.plazo_meses} meses</span>
                <span>
                  Pago <strong className="text-neutral-900">{money(o.pago_mensual)}</strong>
                </span>
                <span>Costo total {money(o.costo_total)}</span>
              </div>
            </div>
          );
        })}
      </div>
      {rationale ? <p className="mt-3 text-xs text-neutral-500">{rationale}</p> : null}
      <p className="mt-2 text-[10px] text-neutral-400">
        Catálogo demostrativo. El top lo elige el Analista con tu capacidad real.
      </p>
    </div>
  );
}

/* ---------------- metric_trend ---------------- */

export function MetricTrend({
  label,
  value,
  change,
  values,
  tone = "neutral",
  footnote,
}: {
  label: string;
  value: string;
  change: string;
  values: number[];
  tone?: "positive" | "watch" | "urgent" | "neutral";
  footnote?: string;
}) {
  const color = tone === "urgent" ? "#eb0029" : tone === "watch" ? "#d97706" : tone === "positive" ? "#12805c" : "#596069";
  const chip =
    tone === "urgent" ? "text-red-600" : tone === "watch" ? "text-amber-600" : tone === "positive" ? "text-green-600" : "text-neutral-500";
  const safe = values.length > 1 ? values : [values[0] ?? 0, values[0] ?? 0];
  const max = Math.max(...safe.map(num));
  const min = Math.min(...safe.map(num));
  const pts = safe
    .map((v, i) => `${3 + (i / (safe.length - 1)) * 94},${33 - ((num(v) - min) / Math.max(max - min, 1)) * 27}`)
    .join(" ");
  const last = pts.split(" ").at(-1)!.split(",");
  return (
    <div className="rounded-xl border bg-white p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-neutral-900">{label}</p>
        <span className={`text-xs font-bold ${chip}`}>{change}</span>
      </div>
      <p className="mt-1 text-2xl font-bold">{value}</p>
      <p className="text-xs text-neutral-500">Cambio frente al mes anterior</p>
      <svg className="mt-2 block w-full" height="38" viewBox="0 0 100 38" preserveAspectRatio="none" role="img" aria-label={`Tendencia de ${label}`}>
        <polygon points={`3,37 ${pts} 97,37`} fill={color} opacity=".09" />
        <polyline points={pts} fill="none" stroke={color} strokeWidth="2.2" vectorEffect="non-scaling-stroke" />
        <circle cx={Number(last[0])} cy={Number(last[1])} r="2.4" fill={color} />
      </svg>
      {footnote ? <p className="mt-3 text-xs text-neutral-500">{footnote}</p> : null}
    </div>
  );
}

/* ---------------- transactions_list ---------------- */

export function TransactionsList({
  items,
}: {
  items: { id: string; merchant: string; category: string; date: string; amount: string; type: "ingreso" | "egreso" }[];
}) {
  if (!items.length) return <Empty what="movimientos" />;
  return (
    <div className="rounded-xl border bg-white p-5">
      <p className="text-sm font-medium text-neutral-900">Movimientos recientes</p>
      <div className="mt-2 divide-y text-sm">
        {items.map((item) => (
          <div key={item.id} className="flex items-center justify-between gap-2 py-2">
            <div className="min-w-0">
              <p className="truncate font-medium">{item.merchant}</p>
              <p className="text-xs text-neutral-500">
                {item.category} · {item.date.slice(0, 10)}
              </p>
            </div>
            <b className={item.type === "ingreso" ? "text-green-600" : ""}>
              {item.type === "ingreso" ? "+" : "−"}{money(item.amount)}
            </b>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------------- timeline_list ---------------- */

export function TimelineList({
  items,
}: {
  items: { id: string; customer_name: string; due_date: string | null; issued_at: string; amount_pending: string; status: string }[];
}) {
  if (!items.length) return <Empty what="cobros próximos" />;
  return (
    <div className="rounded-xl border bg-white p-5">
      <p className="text-sm font-medium text-neutral-900">Facturas por cobrar</p>
      <p className="text-xs text-neutral-500">Próximos cobros</p>
      <div className="mt-2 space-y-3">
        {items.slice(0, 4).map((item) => (
          <div key={item.id} className="flex items-center gap-2 text-sm">
            <span className={`h-2 w-2 rounded-full ${item.status === "overdue" ? "bg-red-500" : "bg-green-500"}`} />
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{item.customer_name || "Cliente"}</p>
              <p className="text-xs text-neutral-500">
                {item.due_date ? `Vence ${item.due_date.slice(0, 10)}` : `Emitida ${item.issued_at.slice(0, 10)}`}
              </p>
            </div>
            <b>{money(item.amount_pending)}</b>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------------- tax_summary ---------------- */

export function TaxSummary({
  isr_estimado,
  iva_neto,
  pct_deducible,
}: {
  isr_estimado: string;
  iva_neto: string;
  pct_deducible: number;
}) {
  const pct = Math.round(num(pct_deducible) * 100);
  return (
    <div className="rounded-xl border bg-white p-5">
      <p className="text-sm font-medium text-neutral-900">Impuestos estimados</p>
      <p className="text-xs text-neutral-500">Cálculo del mes</p>
      <div className="mt-2 flex items-baseline gap-2">
        <strong className="text-2xl">{money(isr_estimado)}</strong>
        <span className="text-sm text-neutral-500">ISR estimado</span>
      </div>
      <div className="mt-2 flex justify-between border-t pt-2 text-sm">
        <span className="text-neutral-500">IVA neto</span>
        <b>{money(iva_neto)}</b>
      </div>
      <div className="mt-2 h-2 rounded bg-neutral-100">
        <div className="h-2 rounded bg-emerald-600" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
      </div>
      <p className="mt-1 text-xs text-neutral-500">{pct}% del gasto con CFDI</p>
    </div>
  );
}

/* ---------------- waterfall ---------------- */

export function Waterfall({
  title,
  bars,
  footnote,
}: {
  title: string;
  bars: { label: string; value: number }[];
  footnote?: string;
}) {
  if (!bars.length) return <Empty what="partidas" />;
  const max = Math.max(...bars.map((b) => Math.abs(num(b.value))), 1);
  return (
    <div className="rounded-xl border bg-white p-5">
      <p className="text-sm font-medium text-neutral-900">{title}</p>
      <div className="mt-3 space-y-2">
        {bars.map((b) => {
          const v = num(b.value);
          return (
            <div key={b.label} className="flex items-center gap-2 text-xs">
              <span className="w-28 truncate text-neutral-500">{b.label}</span>
              <div className="h-4 flex-1 rounded bg-neutral-100">
                <div
                  className={`h-4 rounded ${v >= 0 ? "bg-emerald-600" : "bg-red-500"}`}
                  style={{ width: `${Math.max(4, (Math.abs(v) / max) * 100)}%` }}
                />
              </div>
              <strong className="w-20 text-right">{money(v)}</strong>
            </div>
          );
        })}
      </div>
      {footnote ? <p className="mt-3 text-xs text-neutral-500">{footnote}</p> : null}
    </div>
  );
}

/* ---------------- insight_text ---------------- */

export function InsightText({
  title,
  body,
  tone = "neutral",
  evidence,
}: {
  title: string;
  body: string;
  tone?: "positive" | "watch" | "urgent" | "neutral";
  evidence?: string[];
}) {
  const dot =
    tone === "positive"
      ? "bg-emerald-500"
      : tone === "watch"
        ? "bg-amber-500"
        : tone === "urgent"
          ? "bg-red-500"
          : "bg-neutral-400";
  return (
    <div className="rounded-xl border bg-white p-5">
      <div className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${dot}`} />
        <h2 className="text-sm font-bold">{title}</h2>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-neutral-700">{body}</p>
      {evidence && evidence.length > 0 ? (
        <details className="mt-2 text-xs text-neutral-500">
          <summary className="cursor-pointer font-semibold">Evidencia ({evidence.length})</summary>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {evidence.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
