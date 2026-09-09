"use client";

import { useQuery } from "@tanstack/react-query";
import { Landmark } from "lucide-react";

import { DynamicUI } from "@/components/registry";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchGenDashboard } from "@/lib/api";
import type { GenCard } from "@/lib/types";

/**
 * `/` — dashboard generativo (Composition Engine).
 * Anchors + acciones + discovery + summary desde
 * GET /api/dashboard/gen, renderizado con DynamicUI.
 * Sin filtros: la composición ya cura qué se muestra.
 */
export default function GenDashboard() {
  const dashboard = useQuery({
    queryKey: ["dashboard-gen"],
    queryFn: fetchGenDashboard,
    refetchInterval: 60_000,
    retry: 2,
  });

  if (dashboard.isLoading) {
    return (
      <main className="mx-auto max-w-5xl space-y-6 p-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-20 w-full" />
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-44" />
          ))}
        </div>
      </main>
    );
  }

  if (dashboard.isError || !dashboard.data) {
    return (
      <main className="mx-auto max-w-5xl space-y-6 p-6">
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Landmark className="size-5" />
            </EmptyMedia>
            <EmptyTitle>No pudimos cargar tu dashboard</EmptyTitle>
          </EmptyHeader>
          <p className="text-sm text-muted-foreground">
            La interfaz está lista, pero la API no respondió. Revisa que esté
            activa en el puerto 8000.
          </p>
          <Button onClick={() => dashboard.refetch()}>Intentar de nuevo</Button>
        </Empty>
      </main>
    );
  }

  const data = dashboard.data;
  const cards = (list: GenCard[]) =>
    list.map((c) => (
      <DynamicUI
        key={c.insight_id}
        schema={{ component: c.component, props: c.props } as never}
      />
    ));

  return (
    <main className="mx-auto max-w-5xl space-y-8 p-6">
      <header className="space-y-2">
        <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
          Centro financiero · {data.month} · {data.week_id}
        </p>
        <h1 className="text-2xl font-bold tracking-tight">MiNorte</h1>
        {data.summary ? (
          <Alert>
            <AlertTitle>Esta semana</AlertTitle>
            <AlertDescription>{data.summary}</AlertDescription>
          </Alert>
        ) : null}
      </header>

      <section className="space-y-3" aria-label="Métricas principales">
        <h2 className="text-sm font-semibold text-muted-foreground">
          Métricas principales
        </h2>
        <div className="grid gap-4 md:grid-cols-2">
          {data.anchors.map((a) => (
            <DynamicUI
              key={a.metric}
              schema={{
                component: "financial_anchor",
                props: a,
              } as never}
            />
          ))}
        </div>
      </section>

      {data.actions.length > 0 ? (
        <section className="space-y-3" aria-label="Requieren acción">
          <h2 className="text-sm font-semibold text-muted-foreground">
            Requieren acción
          </h2>
          <div className="grid gap-4 md:grid-cols-2">{cards(data.actions)}</div>
        </section>
      ) : null}

      {data.discovery.length > 0 ? (
        <section className="space-y-3" aria-label="Descubrimientos">
          <h2 className="text-sm font-semibold text-muted-foreground">
            Descubrimientos
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            {cards(data.discovery)}
          </div>
        </section>
      ) : null}

      <footer className="text-xs text-muted-foreground">
        Datos del motor financiero · {data.month}. El motor calcula, la
        interfaz explica.
      </footer>
    </main>
  );
}
