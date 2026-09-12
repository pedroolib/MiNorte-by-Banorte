"use client";

import { useQuery } from "@tanstack/react-query";
import {
  fetchAlerts,
  fetchCfdis,
  fetchHealth,
  fetchMatches,
  fetchReceivables,
  fetchSignals,
  fetchSummary,
} from "@/lib/api";

/**
 * /debug — volcado crudo de datos, SIN diseño.
 * Para el equipo y la persona de diseño/UI generativa.
 * El detalle fila-por-fila vive en seed/transactions.csv + Supabase.
 */

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ border: "1px solid #ccc", padding: 12, marginBottom: 12 }}>
      <h2 style={{ fontWeight: "bold", marginBottom: 8 }}>{title}</h2>
      {children}
    </section>
  );
}

function Status({ isLoading, error }: { isLoading: boolean; error: unknown }) {
  if (isLoading) return <p>cargando…</p>;
  if (error) return <p style={{ color: "red" }}>error: {String(error)}</p>;
  return null;
}

function Table({ rows }: { rows: (string | null)[][] }) {
  return (
    <table border={1} cellPadding={4} style={{ fontSize: 12, borderCollapse: "collapse" }}>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            {r.map((c, j) => (
              <td key={j}>{c}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const MESES = ["2026-06", "2026-07", "2026-08"];

export default function Debug() {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth });
  const summary = useQuery({ queryKey: ["summary"], queryFn: fetchSummary });
  const receivables = useQuery({ queryKey: ["receivables"], queryFn: fetchReceivables });
  const matches = useQuery({ queryKey: ["matches"], queryFn: () => fetchMatches() });
  const unmatched = useQuery({
    queryKey: ["matches", "unmatched"],
    queryFn: () => fetchMatches("unmatched"),
  });
  const cfdisRec = useQuery({ queryKey: ["cfdis", "recibido"], queryFn: () => fetchCfdis("recibido") });
  const cfdisEmi = useQuery({ queryKey: ["cfdis", "emitido"], queryFn: () => fetchCfdis("emitido") });
  const alerts06 = useQuery({ queryKey: ["alerts", MESES[0]], queryFn: () => fetchAlerts(MESES[0]) });
  const alerts07 = useQuery({ queryKey: ["alerts", MESES[1]], queryFn: () => fetchAlerts(MESES[1]) });
  const alerts08 = useQuery({ queryKey: ["alerts", MESES[2]], queryFn: () => fetchAlerts(MESES[2]) });
  const signals = useQuery({ queryKey: ["signals"], queryFn: () => fetchSignals() });

  return (
    <main style={{ maxWidth: 900, margin: "0 auto", padding: 16, fontFamily: "monospace" }}>
      <h1>MiNorte — volcado de datos (sin diseño)</h1>
      <p>
        <a href="/">← inicio</a> · contrato UI generativa en <code>docs/ui-schema.md</code>
      </p>

      <Section title="1. Empresa / salud API">
        <Status isLoading={health.isLoading} error={health.error} />
        {health.data && <pre>{JSON.stringify(health.data, null, 2)}</pre>}
        <p>Detalle empresa: seed/company.json · Cuentas: seed/accounts.json</p>
      </Section>

      <Section title="2. Resumen último mes (GET /api/summary)">
        <Status isLoading={summary.isLoading} error={summary.error} />
        {summary.data && <pre>{JSON.stringify(summary.data, null, 2)}</pre>}
      </Section>

      <Section title="3. Alertas por mes (GET /api/alerts?month=)">
        {(
          [
            { mes: MESES[0], q: alerts06 },
            { mes: MESES[1], q: alerts07 },
            { mes: MESES[2], q: alerts08 },
          ] as const
        ).map(({ mes, q }) => (
          <div key={mes}>
            <h3>{mes}</h3>
            <Status isLoading={q.isLoading} error={q.error} />
            {q.data && <pre>{JSON.stringify(q.data.items, null, 2)}</pre>}
          </div>
        ))}
      </Section>

      <Section title="4. Cuentas por cobrar (GET /api/receivables)">
        <Status isLoading={receivables.isLoading} error={receivables.error} />
        {receivables.data && (
          <>
            <p>
              total: {receivables.data.total} · pendiente: ${receivables.data.total_pending}
            </p>
            <Table
              rows={[
                ["id", "cliente", "monto", "pendiente", "emitida", "vence", "status"],
                ...receivables.data.items.map((r) => [
                  r.id, r.customer_name, r.amount, r.amount_pending,
                  r.issued_at.slice(0, 10), r.due_date?.slice(0, 10) ?? "—", r.status,
                ]),
              ]}
            />
          </>
        )}
      </Section>

      <Section title="5. Conciliación (GET /api/matches)">
        <Status isLoading={matches.isLoading} error={matches.error} />
        {matches.data && <pre>counts: {JSON.stringify(matches.data.counts)}</pre>}
        <h3>Sin factura (status=unmatched)</h3>
        <Status isLoading={unmatched.isLoading} error={unmatched.error} />
        {unmatched.data && (
          <Table
            rows={[
              ["transaction_id", "score", "monto", "fecha", "comercio"],
              ...unmatched.data.items.map((m) => [
                m.transaction_id, m.score, m.amount_score, m.date_score, m.merchant_score,
              ]),
            ]}
          />
        )}
      </Section>

      <Section title="6. CFDIs (GET /api/cfdis, muestra 5 por tipo)">
        <Status isLoading={cfdisEmi.isLoading} error={cfdisEmi.error} />
        {cfdisEmi.data && <p>emitidos total: {cfdisEmi.data.total}</p>}
        {cfdisEmi.data && (
          <Table
            rows={[
              ["folio", "receptor", "total", "emisión"],
              ...cfdisEmi.data.items.map((c) => [
                `${c.serie ?? ""}-${c.folio ?? ""}`, c.receptor_nombre,
                c.total, c.fecha_emision.slice(0, 10),
              ]),
            ]}
          />
        )}
        <Status isLoading={cfdisRec.isLoading} error={cfdisRec.error} />
        {cfdisRec.data && <p>recibidos total: {cfdisRec.data.total} (muestra 5)</p>}
        {cfdisRec.data && (
          <Table
            rows={[
              ["folio", "emisor", "total", "emisión"],
              ...cfdisRec.data.items.map((c) => [
                `${c.serie ?? ""}-${c.folio ?? ""}`, c.emisor_nombre,
                c.total, c.fecha_emision.slice(0, 10),
              ]),
            ]}
          />
        )}
      </Section>

      <Section title="7. Señales del motor para el Analista (GET /api/signals)">
        <Status isLoading={signals.isLoading} error={signals.error} />
        {signals.data && <pre>{JSON.stringify(signals.data, null, 2)}</pre>}
        <p>Fórmulas sin juicio: es lo que la IA recibirá para decidir tarjetas.</p>
      </Section>

      <Section title="8. Movimientos (473 filas)">
        <p>
          Sin endpoint de detalle (a propósito). Ver <code>seed/transactions.csv</code> o
          tabla <code>transactions</code> en Supabase.
        </p>
      </Section>
    </main>
  );
}
