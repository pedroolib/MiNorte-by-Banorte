/**
 * UI Schema (spec #22) — T0 solo define los tipos.
 * Regla: el LLM nunca devuelve JSX, solo este JSON, y el
 * Component Registry decide qué React renderizar.
 *
 * En T8 se validará con zod + Structured Outputs.
 */

export type UISchema =
  | {
      component: "receivables_resolution";
      props: { count: number; total: string };
    }
  | {
      component: "receipts_resolution";
      props: { count: number; total: string };
    }
  | {
      component: "hero_number";
      props: { label: string; sublabel: string; value: string; delta?: string; tone?: string };
    }
  | {
      component: "multi_ring";
      props: { items: { label: string; value: number }[]; footnote?: string };
    }
  | {
      component: "bars_total";
      props: { title: string; total: string; values: number[]; labels: string[]; footnote?: string };
    }
  | {
      component: "progress_list";
      props: { title: string; items: { label: string; percent: number }[]; footnote?: string };
    }
  | {
      component: "donut_total";
      props: {
        title: string;
        center_value: string;
        center_label: string;
        segments: { label: string; value: number }[];
        footnote?: string;
      };
    }
  | {
      component: "entity_cluster";
      props: { title: string; subtitle: string; items: { name: string }[]; action_label?: string; footnote?: string };
    }
  | {
      component: "action_card";
      props: {
        eyebrow: string;
        title: string;
        body: string;
        value: string;
        action_label: string;
        tone?: string;
      };
    }
  | {
      component: "waterfall";
      props: { title: string; bars: { label: string; value: number }[]; footnote?: string };
    }
  | {
      component: "insight_text";
      props: { title: string; body: string; tone?: string; evidence?: string[] };
    }
  | {
      component: "time_series";
      props: {
        title: string;
        points: { label: string; income: number; expenses: number }[];
        series: "income" | "expenses" | "both";
        period_label?: string;
        footnote?: string;
      };
    }
  | {
      component: "banorte_best_loans";
      props: {
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
      };
    }
  | {
      component: "metric_trend";
      props: { label: string; value: string; change: string; values: number[]; tone?: string; footnote?: string };
    }
  | {
      component: "transactions_list";
      props: {
        items: {
          id: string;
          merchant: string;
          category: string;
          date: string;
          amount: string;
          type: "ingreso" | "egreso";
        }[];
      };
    }
  | {
      component: "timeline_list";
      props: {
        items: {
          id: string;
          customer_name: string;
          due_date: string | null;
          issued_at: string;
          amount_pending: string;
          status: string;
        }[];
      };
    }
  | {
      component: "tax_summary";
      props: { isr_estimado: string; iva_neto: string; pct_deducible: number };
    };
