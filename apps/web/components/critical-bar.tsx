"use client";

import { useQuery } from "@tanstack/react-query";
import { TriangleAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { fetchCriticalBar } from "@/lib/api";

/** Barra compacta de pendientes: visible sobre cualquier modo. */
export function CriticalBar() {
  const bar = useQuery({
    queryKey: ["critical-bar"],
    queryFn: fetchCriticalBar,
    refetchInterval: 60_000,
    retry: 1,
  });
  if (!bar.data || bar.data.pendientes === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-card px-3 py-2 text-xs">
      <TriangleAlert className="size-3.5 text-destructive" />
      <strong>Esta semana · {bar.data.pendientes} pendientes</strong>
      {bar.data.items.slice(0, 3).map((c) => (
        <Badge
          key={c.insight_id}
          variant={c.component === "insight_text" ? "destructive" : "warning"}
        >
          {resumen(c)}
        </Badge>
      ))}
    </div>
  );
}

function resumen(c: { component: string; props: Record<string, unknown> }) {
  const p = c.props as Record<string, string | number>;
  if (c.component === "receipts_resolution")
    return `${p.count} gastos sin factura`;
  if (c.component === "receivables_resolution")
    return `${p.count} por cobrar`;
  return String(p.title ?? c.component);
}
