"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchHealth, fetchSummary } from "@/lib/api";
import { DynamicUI } from "@/components/registry";
import type { UISchema } from "@/lib/ui-schema";

const fmt = (n: number | string) =>
  new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency: "MXN",
    maximumFractionDigits: 0,
  }).format(Number(n));

export default function Home() {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth });
  const summary = useQuery({ queryKey: ["summary"], queryFn: fetchSummary });

  // Demo T0 del registry generativo: en T8 el Consultant devolverá
  // estos schemas desde el backend en vez de JSX arbitrario.
  const demoSchemas: UISchema[] = summary.data
    ? [
        {
          component: "receivables_resolution",
          props: {
            total_pending: Number(summary.data.cuentas_por_cobrar),
            invoices: [],
          },
        },
      ]
    : [];

  return (
    <main className="mx-auto max-w-2xl space-y-6 p-6">
      <header>
        <p className="text-sm text-neutral-500">MiNorte by Banorte · T0</p>
        <h1 className="text-2xl font-semibold">Buenos días</h1>
        <p className="text-sm text-neutral-500">
          Backend:{" "}
          {health.isLoading
            ? "conectando…"
            : health.data
              ? `ok (${health.data.company_id})`
              : "sin conexión — levanta la API en :8000"}
        </p>
      </header>

      <section className="rounded-2xl bg-white p-5 shadow-sm">
        <h2 className="mb-3 font-medium">Tu negocio hoy</h2>
        {summary.isLoading ? (
          <p className="text-sm">Conectando con Banorte…</p>
        ) : summary.data ? (
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-neutral-500">Ventas</dt>
              <dd className="text-lg font-semibold">
                {fmt(summary.data.ventas)}
              </dd>
            </div>
            <div>
              <dt className="text-neutral-500">Utilidad</dt>
              <dd className="text-lg font-semibold">
                {fmt(summary.data.utilidad)}
              </dd>
            </div>
            <div>
              <dt className="text-neutral-500">Efectivo</dt>
              <dd className="text-lg font-semibold">
                {fmt(summary.data.efectivo)}
              </dd>
            </div>
            <div>
              <dt className="text-neutral-500">Cuentas por cobrar</dt>
              <dd className="text-lg font-semibold">
                {fmt(summary.data.cuentas_por_cobrar)}
              </dd>
            </div>
          </dl>
        ) : (
          <p className="text-sm text-red-600">
            No se pudo cargar el resumen. ¿Está corriendo `GET /api/summary`?
          </p>
        )}
      </section>

      <section className="rounded-2xl bg-white p-5 shadow-sm">
        <h2 className="mb-2 font-medium">Necesita tu atención (T0 demo)</h2>
        {demoSchemas.map((s, i) => (
          <DynamicUI key={i} schema={s} />
        ))}
        {!summary.data && (
          <p className="text-sm text-neutral-500">Sin datos todavía.</p>
        )}
      </section>

      <section className="rounded-2xl bg-white p-5 shadow-sm">
        <h2 className="mb-2 font-medium">Pregúntame sobre tu negocio…</h2>
        <p className="text-sm text-neutral-500">
          El chat del Consultor llega en T8. En T0 esto es solo placeholder.
        </p>
      </section>
    </main>
  );
}
