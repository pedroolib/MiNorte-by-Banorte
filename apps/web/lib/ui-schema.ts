/**
 * UI Schema (spec #22) — T0 solo define los tipos.
 * Regla: el LLM nunca devuelve JSX, solo este JSON, y el
 * Component Registry decide qué React renderizar.
 *
 * En T8 se validará con zod + Structured Outputs.
 */

export type UISchema =
  | {
      component: "loan_comparison";
      props: { amount: number };
    }
  | {
      component: "receivables_resolution";
      props: { total_pending: number; invoices: unknown[] };
    }
  | {
      component: "receipts_resolution";
      props: { count: number; total: number };
    }
  | {
      component: "hiring_simulation";
      props: { monthly_cost: number };
    };
