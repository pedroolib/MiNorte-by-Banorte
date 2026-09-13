"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, BookmarkPlus, MessageCircle } from "lucide-react";

import { AskBar } from "@/components/ask-bar";
import { CriticalBar } from "@/components/critical-bar";
import { DynamicUI } from "@/components/registry";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import {
  fetchDrill,
  fetchGenDashboard,
  fetchScenarios,
  saveScenario,
  sendChat,
} from "@/lib/api";
import type { GenCard } from "@/lib/types";

type Mode =
  | { name: "weekly" }
  | { name: "consultant"; question: string }
  | { name: "deep_dive"; insightId: string; title: string };

const LS_KEY = "minorte_conversation_id";

/**
 * Workspace MiNorte: weekly_dashboard (Analista) + consultant_view temporal
 * + deep_dive por tarjeta. La barra de críticos vive sobre cualquier modo.
 */
export default function Workspace() {
  const [mode, setMode] = useState<Mode>({ name: "weekly" });
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<{
    pregunta: string;
    respuesta: string;
    tarjetas: GenCard[];
    cid: string | null;
    evaluable: boolean;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const dashboard = useQuery({
    queryKey: ["dashboard-gen"],
    queryFn: fetchGenDashboard,
    refetchInterval: 60_000,
    retry: 2,
  });
  const scenarios = useQuery({
    queryKey: ["scenarios"],
    queryFn: fetchScenarios,
    retry: 1,
  });

  async function preguntar(pregunta: string) {
    const t = pregunta.trim();
    if (!t || busy) return;
    setBusy(true);
    setError(null);
    try {
      const cid =
        typeof window === "undefined"
          ? null
          : window.localStorage.getItem(LS_KEY);
      const r = await sendChat(t, cid);
      if (typeof window !== "undefined") {
        window.localStorage.setItem(LS_KEY, r.conversation_id);
      }
      setAnswer({
        pregunta: t,
        respuesta: r.respuesta,
        tarjetas: r.tarjetas ?? [],
        cid: r.conversation_id,
        evaluable: (r.tools_usados ?? []).includes("evaluar_gasto"),
      });
      setMode({ name: "consultant", question: t });
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo preguntar");
    } finally {
      setBusy(false);
    }
  }

  function preguntaPara(component: string, props: Record<string, unknown>) {
    const p = props as Record<string, string | number>;
    if (component === "receipts_resolution")
      return `Tengo ${p.count} gastos sin factura por $${p.total}, ¿cómo los resuelvo?`;
    if (component === "receivables_resolution")
      return `Tengo ${p.count} facturas por cobrar por $${p.total}, ¿cómo las cobro?`;
    return `¿Qué hago con esto: ${String(props.title ?? component)}?`;
  }

  return (
    <main className="mx-auto max-w-5xl space-y-6 p-6">
      <CriticalBar />
      <AskBar onAsk={preguntar} busy={busy} />

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Falló la pregunta</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {mode.name !== "weekly" ? (
        <Button variant="outline" size="sm" onClick={() => setMode({ name: "weekly" })}>
          <ArrowLeft className="size-4" /> Volver a mi resumen
        </Button>
      ) : null}

      {mode.name === "consultant" && answer ? (
        <ConsultantView
          answer={answer}
          onSave={async () => {
            await saveScenario({
              conversation_id: answer.cid,
              titulo: answer.pregunta.slice(0, 80),
              detalle: answer.respuesta.slice(0, 500),
              cifras: {},
            });
            scenarios.refetch();
          }}
        />
      ) : null}

      {mode.name === "deep_dive" ? (
        <DeepDive
          insightId={mode.insightId}
          title={mode.title}
          onAsk={preguntar}
        />
      ) : null}

      {mode.name === "weekly" ? (
        <WeeklyView
          loading={dashboard.isLoading}
          error={dashboard.isError}
          retry={() => dashboard.refetch()}
          data={dashboard.data ?? null}
          onAction={(c, p) => preguntar(preguntaPara(c, p))}
          onDeepDive={(id, title) =>
            setMode({ name: "deep_dive", insightId: id, title })
          }
          scenarios={scenarios.data?.items ?? []}
        />
      ) : null}
    </main>
  );
}

function WeeklyView({
  loading,
  error,
  retry,
  data,
  onAction,
  onDeepDive,
  scenarios,
}: {
  loading: boolean;
  error: boolean;
  retry: () => void;
  data: import("@/lib/types").GenDashboard | null;
  onAction: (component: string, props: Record<string, unknown>) => void;
  onDeepDive: (insightId: string, title: string) => void;
  scenarios: import("@/lib/types").SavedScenario[];
}) {
  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-20 w-full" />
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-44" />
          ))}
        </div>
      </div>
    );
  }
  if (error || !data) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <MessageCircle className="size-5" />
          </EmptyMedia>
          <EmptyTitle>No pudimos cargar tu dashboard</EmptyTitle>
        </EmptyHeader>
        <Button onClick={retry}>Intentar de nuevo</Button>
      </Empty>
    );
  }
  const drillables = new Set(
    [...data.actions, ...data.discovery]
      .map((c) => c.insight_id)
      .filter((id) => id && !/^\d{4}-\d{2}_/.test(id) && id !== "consulta"),
  );
  const wrap = (c: GenCard) => (
    <div key={c.insight_id} className="space-y-2">
      <DynamicUI
        schema={{ component: c.component, props: c.props } as never}
        onAction={onAction}
      />
      {drillables.has(c.insight_id) ? (
        <Button
          variant="ghost"
          size="sm"
          onClick={() =>
            onDeepDive(c.insight_id, String((c.props as { title?: string }).title ?? c.component))
          }
        >
          Entender por qué
        </Button>
      ) : null}
    </div>
  );
  return (
    <div className="space-y-8">
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
              schema={{ component: "financial_anchor", props: a } as never}
            />
          ))}
        </div>
      </section>

      {data.actions.length > 0 ? (
        <section className="space-y-3" aria-label="Requieren acción">
          <h2 className="text-sm font-semibold text-muted-foreground">
            Requieren acción
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            {data.actions.map(wrap)}
          </div>
        </section>
      ) : null}

      {data.discovery.length > 0 ? (
        <section className="space-y-3" aria-label="Descubrimientos">
          <h2 className="text-sm font-semibold text-muted-foreground">
            Descubrimientos
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            {data.discovery.map(wrap)}
          </div>
        </section>
      ) : null}

      {scenarios.length > 0 ? (
        <section className="space-y-3" aria-label="Escenarios guardados">
          <h2 className="text-sm font-semibold text-muted-foreground">
            Escenarios guardados
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            {scenarios.map((s) => (
              <div key={s.id} className="rounded-xl border bg-card p-5">
                <Badge variant="secondary">Escenario guardado</Badge>
                <p className="mt-2 text-sm font-bold">{s.titulo}</p>
                <p className="mt-1 text-sm text-muted-foreground">{s.detalle}</p>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <footer className="text-xs text-muted-foreground">
        Datos del motor financiero · {data.month}. El motor calcula, la
        interfaz explica.
      </footer>
    </div>
  );
}

function ConsultantView({
  answer,
  onSave,
}: {
  answer: {
    pregunta: string;
    respuesta: string;
    tarjetas: GenCard[];
    evaluable: boolean;
  };
  onSave: () => Promise<void>;
}) {
  const [saved, setSaved] = useState(false);
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Badge>Vista temporal</Badge>
        <h2 className="text-lg font-bold">{answer.pregunta}</h2>
      </div>
      <Alert>
        <AlertDescription className="whitespace-pre-wrap">
          {answer.respuesta}
        </AlertDescription>
      </Alert>
      {answer.tarjetas.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2">
          {answer.tarjetas.map((c, i) => (
            <DynamicUI
              key={c.insight_id + i}
              schema={{ component: c.component, props: c.props } as never}
            />
          ))}
        </div>
      ) : null}
      {answer.evaluable && !saved ? (
        <Button
          variant="outline"
          onClick={async () => {
            await onSave();
            setSaved(true);
          }}
        >
          <BookmarkPlus className="size-4" /> Guardar escenario
        </Button>
      ) : null}
      {saved ? <Badge variant="success">Escenario guardado</Badge> : null}
    </div>
  );
}

function DeepDive({
  insightId,
  title,
  onAsk,
}: {
  insightId: string;
  title: string;
  onAsk: (q: string) => void;
}) {
  const drill = useQuery({
    queryKey: ["drill", insightId],
    queryFn: () => fetchDrill(insightId),
    retry: 1,
  });
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Badge variant="secondary">Investigación</Badge>
        <h2 className="text-lg font-bold">{title}</h2>
      </div>
      {drill.isLoading ? <Skeleton className="h-32 w-full" /> : null}
      {drill.isError ? (
        <Alert variant="destructive">
          <AlertTitle>No se pudo investigar</AlertTitle>
          <AlertDescription>Intenta de nuevo más tarde.</AlertDescription>
        </Alert>
      ) : null}
      {drill.data ? (
        <>
          <Alert>
            <AlertDescription className="whitespace-pre-wrap">
              {drill.data.texto}
            </AlertDescription>
          </Alert>
          <div className="grid gap-4 md:grid-cols-2">
            {drill.data.tarjetas.map((c, i) => (
              <DynamicUI
                key={c.insight_id + i}
                schema={{ component: c.component, props: c.props } as never}
              />
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onAsk(`¿Este tema va a afectar mi flujo de caja? (${title})`)}
            >
              ¿Afecta mi flujo?
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onAsk(`¿Qué hago con esto: ${title}?`)}
            >
              ¿Qué hago?
            </Button>
          </div>
        </>
      ) : null}
    </div>
  );
}
