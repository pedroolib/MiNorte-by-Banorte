"use client";

import type { UISchema } from "@/lib/ui-schema";
import {
  ActionCard,
  BanorteBestLoans,
  BarsTotal,
  DonutTotal,
  EntityCluster,
  HeroNumber,
  InsightText,
  MetricTrend,
  MultiRing,
  ProgressList,
  TaxSummary,
  TimeSeries,
  TimelineList,
  TransactionsList,
  Waterfall,
} from "./cards";

/**
 * Component Registry (spec #22) — T0 mínimo.
 * Para agregar un diseño nuevo: crea el componente y regístralo aquí.
 * Nada de JSX generado por LLM.
 */

function ReceivablesResolution({
  count,
  total,
}: {
  count: number;
  total: string;
}) {
  return (
    <div className="rounded-xl border p-3 text-sm">
      {count} facturas pendientes de cobro (total $
      {Number(total).toLocaleString("es-MX")}).{" "}
      <button className="rounded-lg bg-black px-3 py-1 text-white">
        Resolver
      </button>
    </div>
  );
}

function ReceiptsResolution({
  count,
  total,
}: {
  count: number;
  total: string;
}) {
  return (
    <div className="rounded-xl border p-3 text-sm">
      {count} gastos necesitan factura (total $
      {Number(total).toLocaleString("es-MX")}).{" "}
      <button className="rounded-lg bg-black px-3 py-1 text-white">
        Resolver
      </button>
    </div>
  );
}

const REGISTRY: Record<UISchema["component"], React.FC<any>> = {
  receivables_resolution: ReceivablesResolution,
  receipts_resolution: ReceiptsResolution,
  hero_number: HeroNumber,
  multi_ring: MultiRing,
  bars_total: BarsTotal,
  progress_list: ProgressList,
  donut_total: DonutTotal,
  entity_cluster: EntityCluster,
  action_card: ActionCard,
  waterfall: Waterfall,
  insight_text: InsightText,
  time_series: TimeSeries,
  banorte_best_loans: BanorteBestLoans,
  metric_trend: MetricTrend,
  transactions_list: TransactionsList,
  timeline_list: TimelineList,
  tax_summary: TaxSummary,
};

export function DynamicUI({ schema }: { schema: UISchema }) {
  const Cmp = REGISTRY[schema.component];
  if (!Cmp) return <p>Componente no soportado: {schema.component}</p>;
  return <Cmp {...schema.props} />;
}
