"use client";

import React from "react";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BadgeCheck,
  Bell,
  FileWarning,
  Flame,
  Landmark,
  PiggyBank,
  ReceiptText,
  TrendingDown,
  Wallet,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Label,
  Pie,
  PieChart,
  PolarGrid,
  PolarRadiusAxis,
  RadialBar,
  RadialBarChart,
  ReferenceDot,
  ReferenceLine,
  XAxis,
  YAxis,
} from "recharts";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Empty as EmptyState,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";

/**
 * Catálogo de tarjetas MiNorte sobre shadcn/ui (presentacionales, sin datos quemados).
 * Cada una recibe SOLO props tipadas en `lib/ui-schema.ts`.
 * Reglas: números es-MX, moneda MXN, estados loading/vacío/error los maneja
 * el composer (aquí: guardas mínimas "Sin datos").
 */

const fmtMoney0 = new Intl.NumberFormat("es-MX", {
  style: "currency",
  currency: "MXN",
  maximumFractionDigits: 0,
});
const num = (v: unknown) => Number(v ?? 0);
const money = (v: unknown) => fmtMoney0.format(num(v));

function Empty({ what }: { what: string }) {
  return (
    <EmptyState className="border-solid">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <ReceiptText className="size-5" />
        </EmptyMedia>
        <EmptyTitle className="text-sm">Sin datos de {what}.</EmptyTitle>
      </EmptyHeader>
    </EmptyState>
  );
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

function Footnote({ text }: { text?: string }) {
  if (!text) return null;
  return <p className="mt-3 text-xs text-muted-foreground">{text}</p>;
}

type Tone = "positive" | "watch" | "urgent" | "neutral";

function toneBadge(
  tone: Tone,
): "success" | "warning" | "destructive" | "secondary" {
  if (tone === "positive") return "success";
  if (tone === "watch") return "warning";
  if (tone === "urgent") return "destructive";
  return "secondary";
}

/* ---------------- financial_anchor ---------------- */

export function FinancialAnchor({
  metric,
  label,
  value,
  trend,
  analyst_comment,
}: {
  metric: string;
  label: string;
  value: number | string | null;
  trend: { direction: "up" | "down" | "flat"; percentage: number } | null;
  analyst_comment: string;
}) {
  const trendBadge =
    !trend || metric === "estimated_tax" ? null : (
      <Badge variant={trend.direction === "up" ? "success" : trend.direction === "down" ? "destructive" : "secondary"}>
        {trend.direction === "up" ? (
          <ArrowUpRight className="size-3" />
        ) : trend.direction === "down" ? (
          <ArrowDownRight className="size-3" />
        ) : null}
        {trend.direction === "flat" ? "±" : ""}
        {trend.percentage}%
      </Badge>
    );
  return (
    <Card data-metric={metric}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-sm">{label}</CardTitle>
          {trendBadge}
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-bold tracking-tight">
          {value === null || value === undefined ? "—" : typeof value === "number" ? money(value) : value}
        </p>
        {analyst_comment ? (
          <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{analyst_comment}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

/* ---------------- data_table ---------------- */

export function DataTable({
  title,
  columns,
  rows,
  footnote,
}: {
  title: string;
  columns: string[];
  rows: (string | number)[][];
  footnote?: string;
}) {
  if (!columns.length || !rows.length) return <Empty what="filas" />;
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent className="px-2">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((c, i) => (
                <TableHead key={i} className={i > 0 ? "text-right" : ""}>
                  {c}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
            <TableBody>
              {rows.map((row, i) => (
                <TableRow key={i}>
                  {row.map((cell, j) => (
                    <TableCell key={j} className={j > 0 ? "text-right font-medium" : "font-medium"}>
                      {typeof cell === "number"
                        ? cell.toLocaleString("es-MX")
                        : cell}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
        </Table>
        <Footnote text={footnote} />
      </CardContent>
    </Card>
  );
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
  const TrendIcon =
    tone === "positive" ? ArrowUpRight : tone === "negative" ? ArrowDownRight : null;
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{label}</CardTitle>
        <CardDescription>{sublabel}</CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-4xl font-bold tracking-tight">{value}</p>
        {delta ? (
          <div className="mt-2">
            <Badge
              variant={
                tone === "positive"
                  ? "success"
                  : tone === "negative"
                    ? "destructive"
                    : "secondary"
              }
            >
              {TrendIcon ? <TrendIcon className="size-3" /> : null}
              {delta}
            </Badge>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

/* ---------------- multi_ring ---------------- */

const RING_COLORS = ["#16a34a", "#7c3aed", "#eb0029", "#d97706"];

export function MultiRing({ items, footnote }: { items: { label: string; value: number }[]; footnote?: string }) {
  if (!items.length) return <Empty what="indicadores" />;
  const rings = items.slice(0, 3);
  const data = rings.map((item, i) => ({
    name: item.label,
    value: Math.max(0, Math.min(100, num(item.value))),
    fill: RING_COLORS[i % RING_COLORS.length],
  }));
  const config = Object.fromEntries(
    rings.map((item, i) => [item.label, { label: item.label, color: RING_COLORS[i % RING_COLORS.length] }]),
  ) satisfies ChartConfig;
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-center gap-6">
          <ChartContainer config={config} className="mx-auto aspect-square w-full max-w-[160px]">
            <RadialBarChart data={data} innerRadius="30%" outerRadius="100%" startAngle={90} endAngle={-270}>
              <ChartTooltip cursor={false} content={<ChartTooltipContent hideLabel nameKey="name" />} />
              <PolarGrid gridType="circle" radialLines={false} stroke="none" />
              <RadialBar dataKey="value" background cornerRadius={8} />
              <PolarRadiusAxis tick={false} tickLine={false} axisLine={false}>
                <Label
                  content={({ viewBox }) => {
                    if (viewBox && "cx" in viewBox && "cy" in viewBox) {
                      return (
                        <text x={viewBox.cx} y={viewBox.cy} textAnchor="middle" dominantBaseline="middle">
                          <tspan x={viewBox.cx} y={(viewBox.cy || 0) - 8} fontSize="20" fontWeight="800" fill="hsl(var(--foreground))">
                            {Math.round(num(items[0]?.value))}%
                          </tspan>
                          <tspan x={viewBox.cx} y={(viewBox.cy || 0) + 12} fontSize="10" fill="hsl(var(--muted-foreground))">
                            {items[0]?.label}
                          </tspan>
                        </text>
                      );
                    }
                    return null;
                  }}
                />
              </PolarRadiusAxis>
            </RadialBarChart>
          </ChartContainer>
          <ul className="space-y-2 text-sm">
            {items.map((item, i) => (
              <li key={item.label} className="flex items-center gap-2">
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ background: RING_COLORS[i % RING_COLORS.length] }}
                />
                <span className="text-muted-foreground">{item.label}</span>
                <strong>{Math.round(num(item.value))}%</strong>
              </li>
            ))}
          </ul>
        </div>
        <Footnote text={footnote} />
      </CardContent>
    </Card>
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
  const data = values.map((v, i) => ({ label: labels[i] ?? "", value: num(v) }));
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{title}</CardDescription>
        <CardTitle className="text-3xl">{total}</CardTitle>
      </CardHeader>
      <CardContent>
        <ChartContainer config={{ value: { label: title, color: "hsl(var(--primary))" } }} className="h-28 w-full">
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
            <ChartTooltip cursor={false} content={<ChartTooltipContent hideLabel />} />
            <XAxis dataKey="label" tickLine={false} axisLine={false} tickMargin={6} fontSize={9} interval={0} angle={-18} textAnchor="end" height={52} tickFormatter={(v: string) => (v.length > 14 ? `${v.slice(0, 13)}…` : v)} />
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {data.map((entry, i) => (
                <Cell key={entry.label} fill={i === data.length - 1 ? "hsl(var(--primary))" : "hsl(var(--primary) / 0.2)"} />
              ))}
            </Bar>
          </BarChart>
        </ChartContainer>
        <Footnote text={footnote} />
      </CardContent>
    </Card>
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
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.map((item) => {
          const pct = Math.max(0, Math.min(100, num(item.percent)));
          return (
            <div key={item.label}>
              <div className="flex justify-between text-xs">
                <span className="font-medium">{item.label}</span>
                <span className="font-semibold text-primary">{Math.round(pct)}%</span>
              </div>
              <Progress value={pct} className="mt-1" />
            </div>
          );
        })}
        <Footnote text={footnote} />
      </CardContent>
    </Card>
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
  const data = segments.map((s, i) => ({
    name: s.label,
    value: num(s.value),
    fill: colors[i % colors.length],
  }));
  const config = Object.fromEntries(
    segments.map((s, i) => [s.label, { label: s.label, color: colors[i % colors.length] }]),
  ) satisfies ChartConfig;
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-5">
          <ChartContainer config={config} className="mx-auto aspect-square w-full max-w-[140px]">
            <PieChart>
              <ChartTooltip cursor={false} content={<ChartTooltipContent hideLabel />} />
              <Pie data={data} dataKey="value" nameKey="name" innerRadius="62%" outerRadius="100%" strokeWidth={2}>
                {data.map((entry) => (
                  <Cell key={entry.name} fill={entry.fill} />
                ))}
                <Label
                  content={({ viewBox }) => {
                    if (viewBox && "cx" in viewBox && "cy" in viewBox) {
                      return (
                        <text x={viewBox.cx} y={viewBox.cy} textAnchor="middle" dominantBaseline="middle">
                          <tspan x={viewBox.cx} y={(viewBox.cy || 0) - 8} fontSize="14" fontWeight="800" fill="hsl(var(--foreground))">
                            {center_value}
                          </tspan>
                          <tspan x={viewBox.cx} y={(viewBox.cy || 0) + 12} fontSize="9" fill="hsl(var(--muted-foreground))">
                            {center_label}
                          </tspan>
                        </text>
                      );
                    }
                    return null;
                  }}
                />
              </Pie>
            </PieChart>
          </ChartContainer>
          <ul className="space-y-2 text-xs">
            {segments.map((s, i) => (
              <li key={s.label} className="flex items-center gap-2">
                <span
                  className="inline-block h-2 w-2 rounded-sm"
                  style={{ background: colors[i % colors.length] }}
                />
                <span className="text-muted-foreground">{s.label}:</span>
                <strong>{money(s.value)}</strong>
              </li>
            ))}
          </ul>
        </div>
        <Footnote text={footnote} />
      </CardContent>
    </Card>
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
    <Card>
      <CardContent className="pt-6 text-center">
        <div className="flex items-center justify-center -space-x-2 *:data-[slot=avatar]:ring-background *:data-[slot=avatar]:ring-2">
          {shown.map((item) => (
            <Avatar key={item.name} title={item.name}>
              <AvatarFallback>{initials(item.name)}</AvatarFallback>
            </Avatar>
          ))}
          {rest > 0 && (
            <Avatar>
              <AvatarFallback>+{rest}</AvatarFallback>
            </Avatar>
          )}
        </div>
        <p className="mt-3 text-sm font-medium">{title}</p>
        <p className="text-xs text-muted-foreground">{subtitle}</p>
        {action_label ? (
          <Button variant="outline" size="sm" className="mt-3">
            {action_label}
          </Button>
        ) : null}
        <Footnote text={footnote} />
      </CardContent>
    </Card>
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
  icon,
  onAction,
}: {
  eyebrow: string;
  title: string;
  body: string;
  value: string;
  action_label: string;
  tone?: "urgent" | "watch" | "neutral";
  icon?: string;
  onAction?: () => void;
}) {
  const visuals: Record<string, React.ReactNode> = {
    receipt: <ReceiptText className="size-12" />,
    wallet: <Wallet className="size-12" />,
    flame: <Flame className="size-12" />,
    "piggy-bank": <PiggyBank className="size-12" />,
    "trending-down": <TrendingDown className="size-12" />,
    "file-warning": <FileWarning className="size-12" />,
    landmark: <Landmark className="size-12" />,
    bell: <Bell className="size-12" />,
  };
  const visual = icon ? visuals[icon] : null;
  return (
    <Card className="p-0">
      <Alert variant={tone === "urgent" ? "destructive" : "default"} className="border-0">
        <div className="col-start-2 flex items-start gap-4">
          <div className="min-w-0 flex-1">
            <AlertTitle className="flex items-center gap-2">
              <span className="text-[10px] font-bold uppercase tracking-widest opacity-70">
                {eyebrow}
              </span>
            </AlertTitle>
            <AlertDescription>
              <span className="block text-lg font-bold text-foreground">{title}</span>
              <span className="block text-3xl font-extrabold text-foreground">{value}</span>
              <span className="mt-1 block">{body}</span>
            </AlertDescription>
          </div>
          {visual ? (
            <span className="grid size-24 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
              {visual}
            </span>
          ) : null}
        </div>
        <Button className="col-start-2 mt-3 w-full" onClick={onAction}>{action_label}</Button>
      </Alert>
    </Card>
  );
}

/* ---------------- time_series ---------------- */

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
  const color = series === "expenses" ? "#059669" : "#7c3aed";
  const data = points.map((p, i) => ({ label: p.label, value: vals[i] }));
  const minVal = Math.min(...vals);
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-baseline justify-between">
          <CardTitle className="text-sm">{title}</CardTitle>
          {period_label ? <span className="text-xs text-muted-foreground">{period_label}</span> : null}
        </div>
      </CardHeader>
      <CardContent>
        <ChartContainer config={{ value: { label: title, color } }} className="h-[120px] w-full">
          <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
            <defs>
              <linearGradient id="tsFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.25} />
                <stop offset="100%" stopColor={color} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <ChartTooltip cursor={false} content={<ChartTooltipContent hideLabel />} />
            <XAxis dataKey="label" tickLine={false} axisLine={false} tickMargin={6} fontSize={10} />
            <Area dataKey="value" type="monotone" fill="url(#tsFill)" stroke={color} strokeWidth={2.5} dot={false} activeDot={{ r: 3.5 }} />
            <ReferenceDot x={points[vals.indexOf(minVal)]?.label} y={minVal} r={3.5} fill="hsl(var(--card))" stroke={color} strokeWidth={2} />
          </AreaChart>
        </ChartContainer>
        <p className="mt-1 text-[10px] text-muted-foreground">Mín: {money(minVal)}</p>
        <Footnote text={footnote} />
      </CardContent>
    </Card>
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
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Créditos Banorte para ti</CardTitle>
        <CardDescription>Monto solicitado: {money(amount)}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {options.map((o) => {
          const top = top_ids.includes(o.id);
          return (
            <div
              key={o.id}
              className={`cursor-pointer rounded-lg border p-3 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md ${top ? "border-primary bg-primary/5" : ""}`}
            >
              <div className="flex items-center justify-between text-sm">
                <strong>{o.nombre}</strong>
                {top ? <Badge>RECOMENDADO</Badge> : null}
              </div>
              <div className="mt-1 flex gap-4 text-xs text-muted-foreground">
                <span>Tasa {(Number(o.tasa_anual) * 100).toFixed(2)}%</span>
                <span>{o.plazo_meses} meses</span>
                <span>
                  Pago <strong className="text-foreground">{money(o.pago_mensual)}</strong>
                </span>
                <span>Costo total {money(o.costo_total)}</span>
              </div>
            </div>
          );
        })}
        {rationale ? <p className="text-xs text-muted-foreground">{rationale}</p> : null}
        <p className="text-[10px] text-muted-foreground">
          Catálogo demostrativo. El top lo elige el Analista con tu capacidad real.
        </p>
      </CardContent>
    </Card>
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
  const safe = values.length > 1 ? values : [values[0] ?? 0, values[0] ?? 0];
  const data = safe.map((v, i) => ({ idx: i, value: num(v) }));
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">{label}</CardTitle>
          <Badge variant={toneBadge(tone)}>{change}</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-bold">{value}</p>
        <p className="text-xs text-muted-foreground">Cambio frente al mes anterior</p>
        <ChartContainer config={{ value: { label, color } }} className="mt-2 h-[38px] w-full">
          <AreaChart data={data} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
            <defs>
              <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.25} />
                <stop offset="100%" stopColor={color} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <Area dataKey="value" type="monotone" fill="url(#trendFill)" stroke={color} strokeWidth={2.2} dot={false} />
          </AreaChart>
        </ChartContainer>
        <Footnote text={footnote} />
      </CardContent>
    </Card>
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
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Movimientos recientes</CardTitle>
      </CardHeader>
      <CardContent className="px-2">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Comercio</TableHead>
              <TableHead>Categoría</TableHead>
              <TableHead>Fecha</TableHead>
              <TableHead className="text-right">Monto</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="font-medium">{item.merchant}</TableCell>
                <TableCell className="text-muted-foreground">{item.category}</TableCell>
                <TableCell className="text-muted-foreground">{item.date.slice(0, 10)}</TableCell>
                <TableCell className="text-right">
                  <Badge variant={item.type === "ingreso" ? "success" : "secondary"}>
                    {item.type === "ingreso" ? "+" : "−"}
                    {money(item.amount)}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

/* ---------------- timeline_list ---------------- */

export function TimelineList({
  items,
}: {
  items: { id: string; customer_name: string; due_date: string | null; issued_at: string; amount_pending: string; status: string }[];
}) {
  if (!items.length) return <Empty what="cobros próximos" />;
  const now = new Date();
  const diasPara = (iso: string | null) =>
    iso ? Math.ceil((new Date(iso).getTime() - now.getTime()) / 86400000) : null;
  const colorDot = (d: number | null) =>
    d === null || d > 14
      ? "bg-emerald-500"
      : d > 7
        ? "bg-amber-400"
        : "bg-destructive";
  const etiqueta = (d: number | null) =>
    d === null
      ? null
      : d < 0
        ? `Vencida hace ${Math.abs(d)} d`
        : d === 0
          ? "Vence hoy"
          : `Vence en ${d} d`;
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Facturas por cobrar</CardTitle>
        <CardDescription>Próximos cobros</CardDescription>
      </CardHeader>
      <CardContent>
        <ol className="relative space-y-4 border-l border-border pl-0">
          {items.slice(0, 4).map((item) => {
            const d = diasPara(item.due_date);
            return (
              <li key={item.id} className="relative flex items-start gap-3 pl-5">
                <span
                  className={`absolute top-1 -left-[5px] size-2.5 rounded-full ring-4 ring-background ${colorDot(d)}`}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{item.customer_name || "Cliente"}</p>
                  <p className="text-xs text-muted-foreground">
                    {item.due_date ? `Vence ${item.due_date.slice(0, 10)}` : `Emitida ${item.issued_at.slice(0, 10)}`}
                    {etiqueta(d) ? ` · ${etiqueta(d)}` : ""}
                  </p>
                </div>
                <Badge variant={d !== null && d <= 7 ? "destructive" : "success"}>
                  {money(item.amount_pending)}
                </Badge>
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
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
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Impuestos estimados</CardTitle>
        <CardDescription>Cálculo del mes</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-baseline gap-2">
          <strong className="text-2xl">{money(isr_estimado)}</strong>
          <span className="text-sm text-muted-foreground">ISR estimado</span>
        </div>
        <div className="mt-2 flex justify-between border-t pt-2 text-sm">
          <span className="text-muted-foreground">IVA neto</span>
          <b>{money(iva_neto)}</b>
        </div>
        <Progress value={Math.max(0, Math.min(100, pct))} className="mt-2" />
        <p className="mt-1 text-xs text-muted-foreground">{pct}% del gasto con CFDI</p>
      </CardContent>
    </Card>
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
  const data = bars.map((b) => ({ label: b.label, value: num(b.value) }));
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ChartContainer config={{ value: { label: title } }} className="h-[180px] w-full">
          <BarChart data={data} layout="vertical" margin={{ top: 0, right: 12, bottom: 0, left: 8 }}>
            <ChartTooltip cursor={false} content={<ChartTooltipContent hideLabel />} />
            <XAxis type="number" hide />
            <YAxis dataKey="label" type="category" tickLine={false} axisLine={false} tickMargin={8} fontSize={10} width={90} />
            <ReferenceLine x={0} stroke="hsl(var(--border))" />
            <Bar dataKey="value" radius={[0, 4, 4, 0]}>
              {data.map((entry) => (
                <Cell key={entry.label} fill={entry.value >= 0 ? "#059669" : "hsl(var(--destructive))"} />
              ))}
            </Bar>
          </BarChart>
        </ChartContainer>
        <Footnote text={footnote} />
      </CardContent>
    </Card>
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
  return (
    <Alert variant={tone === "urgent" ? "destructive" : "default"}>
      {tone === "positive" ? (
        <BadgeCheck />
      ) : tone === "urgent" || tone === "watch" ? (
        <AlertTriangle />
      ) : null}
      <AlertTitle>
        <Badge variant={toneBadge(tone)}>{title}</Badge>
      </AlertTitle>
      <AlertDescription>
        <p>{body}</p>
        {evidence && evidence.length > 0 ? (
          <details className="mt-2">
            <summary className="cursor-pointer font-semibold">
              Evidencia ({evidence.length})
            </summary>
            <ul className="mt-1 list-disc space-y-1 pl-5">
              {evidence.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          </details>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}

/* ---------------- resolution (curadas) ---------------- */

function ResolutionCard({
  icon,
  text,
  count,
  total,
  onAction,
}: {
  icon: React.ReactNode;
  text: string;
  count: number;
  total: string;
  onAction?: () => void;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 pt-6 text-sm">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
          {icon}
        </span>
        <p className="flex-1">
          <strong>{count}</strong> {text} (total {money(total)}).
        </p>
        <Button size="sm" onClick={onAction}>Resolver</Button>
      </CardContent>
    </Card>
  );
}

export function ReceivablesResolution({
  count,
  total,
  onAction,
}: {
  count: number;
  total: string;
  onAction?: () => void;
}) {
  return (
    <ResolutionCard
      icon={<Wallet className="size-5" />}
      text="facturas pendientes de cobro"
      count={count}
      total={total}
      onAction={onAction}
    />
  );
}

export function ReceiptsResolution({
  count,
  total,
  onAction,
}: {
  count: number;
  total: string;
  onAction?: () => void;
}) {
  return (
    <ResolutionCard
      icon={<ReceiptText className="size-5" />}
      text="gastos necesitan factura"
      count={count}
      total={total}
      onAction={onAction}
    />
  );
}

export function BankLandmark({ className }: { className?: string }) {
  return <Landmark className={className} />;
}
