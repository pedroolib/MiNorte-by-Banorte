"use client";

import type { UISchema } from "@/lib/ui-schema";
import {
  ActionCard,
  BanorteBestLoans,
  BarsTotal,
  DonutTotal,
  EntityCluster,
  FinancialAnchor,
  HeroNumber,
  InsightText,
  MetricTrend,
  MultiRing,
  ProgressList,
  ReceiptsResolution,
  ReceivablesResolution,
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

const REGISTRY: Record<UISchema["component"], React.FC<any>> = {
  financial_anchor: FinancialAnchor,
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
