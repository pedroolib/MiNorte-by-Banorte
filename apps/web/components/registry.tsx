"use client";

import type { UISchema } from "@/lib/ui-schema";

/**
 * Component Registry (spec #22) — T0 mínimo.
 * Para agregar un diseño nuevo: crea el componente y regístralo aquí.
 * Nada de JSX generado por LLM.
 */

function LoanComparison({ amount }: { amount: number }) {
  return (
    <div className="rounded-xl border p-3 text-sm">
      Comparador de crédito por ${amount.toLocaleString("es-MX")} (llega en T8).
    </div>
  );
}

function ReceivablesResolution({
  total_pending,
}: {
  total_pending: number;
  invoices: unknown[];
}) {
  return (
    <div className="rounded-xl border p-3 text-sm">
      Tienes ${total_pending.toLocaleString("es-MX")} pendientes de cobro.{" "}
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
  total: number;
}) {
  return (
    <div className="rounded-xl border p-3 text-sm">
      {count} gastos necesitan factura (total ${total.toLocaleString("es-MX")}).{" "}
      <button className="rounded-lg bg-black px-3 py-1 text-white">
        Resolver
      </button>
    </div>
  );
}

function HiringSimulation({ monthly_cost }: { monthly_cost: number }) {
  return (
    <div className="rounded-xl border p-3 text-sm">
      Simulación de contratación por ${monthly_cost.toLocaleString("es-MX")}/mes
      (llega en T8).
    </div>
  );
}

const REGISTRY: Record<UISchema["component"], React.FC<any>> = {
  loan_comparison: LoanComparison,
  receivables_resolution: ReceivablesResolution,
  receipts_resolution: ReceiptsResolution,
  hiring_simulation: HiringSimulation,
};

export function DynamicUI({ schema }: { schema: UISchema }) {
  const Cmp = REGISTRY[schema.component];
  if (!Cmp) return <p>Componente no soportado: {schema.component}</p>;
  return <Cmp {...schema.props} />;
}
