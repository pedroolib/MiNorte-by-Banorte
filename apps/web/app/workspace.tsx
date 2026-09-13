"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  ArrowLeft,
  BookmarkPlus,
  Loader2,
  MessageCircle,
  Sparkles,
} from "lucide-react";

import { AskBar } from "@/components/ask-bar";
import { CollectionsPanel } from "@/components/collections-panel";
import { CriticalBar } from "@/components/critical-bar";
import { InlineAdvice } from "@/components/inline-advice";
import { Markdown } from "@/components/markdown";
import { DynamicUI } from "@/components/registry";
import { TicketResolutionPanel } from "@/components/ticket-resolution-panel";
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
import { SettingsPanel } from "@/components/settings-panel";
import { ThemeToggle } from "@/components/theme-toggle";
import {
  fetchDrill,
  fetchGenDashboard,
  fetchScenarios,
  saveScenario,
  sendChat,
} from "@/lib/api";
import type { GenCard } from "@/lib/types";
import { cn } from "@/lib/utils";

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
  const [toastError, setToastError] = useState(false);
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
      let r;
      try {
        r = await sendChat(t, cid);
      } catch (e) {
        // El id guardado puede apuntar a una conversación que ya no existe
        // (base recargada, otro COMPANY_ID). No es un error del usuario:
        // lo tiramos y arrancamos conversación nueva en el mismo clic.
        if (
          cid &&
          e instanceof Error &&
          e.message.includes("/api/chat: 404")
        ) {
          window.localStorage.removeItem(LS_KEY);
          r = await sendChat(t, null);
        } else {
          throw e;
        }
      }
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
      setToastError(true);
      window.setTimeout(() => setToastError(false), 4000);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-border/70 bg-background/85 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-6 px-4 sm:px-6 lg:px-8">
          <Link href="/" className="flex shrink-0 items-center gap-2.5" aria-label="MiNorte inicio">
            <BanorteMark />
            <div className="leading-none">
              <span className="block text-sm font-extrabold tracking-tight">MiNorte</span>
              <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                by Banorte
              </span>
            </div>
          </Link>

          <div className="ml-auto flex items-center gap-2">
            <SettingsPanel />
            <ThemeToggle />
            <div className="ml-1 hidden size-9 place-items-center rounded-full bg-gradient-to-br from-primary to-red-700 text-xs font-bold text-white shadow-sm sm:grid">
              AN
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-5 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
        <CriticalBar />

        <div className="relative">
          <div className="pointer-events-none absolute inset-y-0 left-4 hidden items-center sm:flex">
            <Sparkles className="size-4 text-primary" />
          </div>
          <div className="sm:[&_input]:pl-10">
            <AskBar onAsk={preguntar} busy={busy} />
          </div>
        </div>

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
          onDeepDive={(id, title) =>
            setMode({ name: "deep_dive", insightId: id, title })
          }
          scenarios={scenarios.data?.items ?? []}
        />
        ) : null}
      </main>

      {(busy || toastError) && (
        <div
          role="status"
          className={
            toastError
              ? "fixed bottom-5 right-5 z-50 flex items-center gap-2.5 rounded-xl border border-[#eb0029] bg-[#fff0f2] px-4 py-2.5 text-sm font-semibold text-[#bc0021] shadow-[0_8px_24px_rgba(0,0,0,0.18)]"
              : "fixed bottom-5 right-5 z-50 flex items-center gap-2.5 rounded-xl bg-[#17191c] px-4 py-2.5 text-sm font-semibold text-white shadow-[0_8px_24px_rgba(0,0,0,0.18)]"
          }
        >
          {!toastError && <Loader2 className="size-4 animate-spin" />}
          {toastError ? "No se pudo generar la respuesta" : "Generando tu respuesta…"}
        </div>
      )}
    </div>
  );
}

function preguntaPara(component: string, props: Record<string, unknown>) {
  const p = props as Record<string, string | number>;
  if (component === "receipts_resolution")
    return `Tengo ${p.count} gastos sin factura por $${p.total}, ¿cómo los resuelvo?`;
  if (component === "receivables_resolution")
    return `Tengo ${p.count} facturas por cobrar por $${p.total}, ¿cómo las cobro?`;
  return `¿Qué hago con esto: ${String(props.title ?? component)}?`;
}

/**
 * Isotipo oficial Banorte (mismo trazo que `app/icon.svg`, el favicon del tab).
 * Rojo institucional #EC1C2D, sin recolorear: es marca registrada.
 */
function BanorteMark() {
  return (
    <svg
      viewBox="0 0 382 235.2"
      role="img"
      aria-label="Banorte"
      className="block h-9 w-auto shrink-0"
    >
      <g fill="#EC1C2D" transform="matrix(3.2,0,0,3.2,-65.6,-911.04)">
        <path d="m 84.5,284.7 c -28.5,0 -51.6,7.5 -51.6,16.8 0,7.8 16.1,14.3 38,16.2 l 9,-27.7 1.6,28.2 c 1,0 2,0 3.1,0 28.5,0 51.6,-7.5 51.6,-16.8 -0.1,-9.1 -23.2,-16.7 -51.7,-16.7" />
        <path d="m 70.6,318.7 c -27.8,0.3 -50.1,9.1 -50.1,20 0,9.2 15.8,16.9 37.4,19.3 z" />
        <path d="m 81.4,319 2.2,39.2 c 22.9,-2 39.9,-10 39.9,-19.5 0.1,-9.8 -18.1,-18 -42.1,-19.7" />
      </g>
    </svg>
  );
}


function WeeklyView({
  loading,
  error,
  retry,
  data,
  onDeepDive,
  scenarios,
}: {
  loading: boolean;
  error: boolean;
  retry: () => void;
  data: import("@/lib/types").GenDashboard | null;
  onDeepDive: (insightId: string, title: string) => void;
  scenarios: import("@/lib/types").SavedScenario[];
}) {
  // Antes de cualquier return: los hooks no pueden ir tras un early return.
  const [resolviendo, setResolviendo] = useState<string | null>(null);

  if (loading) {
    return (
      <div className="space-y-5" aria-label="Cargando dashboard">
        <div className="flex items-center justify-between">
          <Skeleton className="h-7 w-48 rounded-full" />
          <Skeleton className="h-7 w-28 rounded-full" />
        </div>
        <Skeleton className="h-24 w-full rounded-2xl" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-40 rounded-2xl" />
          ))}
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-72 rounded-2xl" />
          <Skeleton className="h-72 rounded-2xl" />
        </div>
      </div>
    );
  }
  if (error || !data) {
    return (
      <Empty className="rounded-3xl border border-dashed bg-card/65 py-16 shadow-sm">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <MessageCircle className="size-5" />
          </EmptyMedia>
          <EmptyTitle>No pudimos cargar tu dashboard</EmptyTitle>
        </EmptyHeader>
        <p className="max-w-md text-center text-sm text-muted-foreground">
          El centro financiero no respondió. Tus datos están seguros; puedes volver a intentarlo.
        </p>
        <Button onClick={retry} className="rounded-full px-5">Intentar de nuevo</Button>
      </Empty>
    );
  }
  const drillables = new Set(
    [...data.actions, ...data.discovery]
      .map((c) => c.insight_id)
      .filter((id) => id && !/^\d{4}-\d{2}_/.test(id) && id !== "consulta"),
  );
  const wrap = (c: GenCard) => {
    const abierto = resolviendo === c.insight_id;
    // Los "Resolver" son barras delgadas: estirarlas deja un cajón vacío.
    const esBanner =
      c.component === "receipts_resolution" ||
      c.component === "receivables_resolution";
    return (
    <div
      key={c.insight_id}
      className={cn(
        "flex flex-col gap-2",
        // Los "Resolver" son barras de aviso: fila completa y alto natural.
        esBanner && "self-start lg:col-span-2",
        // Las de contenido se emparejan por fila y centran su contenido en
        // el alto sobrante, para que no quede un hueco al fondo. Con un
        // panel abierto nadie se estira: el panel cae debajo de su tarjeta.
        !resolviendo &&
          !esBanner &&
          "h-full [&>*:first-child]:grow [&>*:first-child]:flex [&>*:first-child]:flex-col [&>*:first-child]:justify-center",
      )}
    >
      <DynamicUI
        schema={{ component: c.component, props: c.props } as never}
        onAction={() => setResolviendo(abierto ? null : c.insight_id)}
      />
      {abierto ? (
        c.component === "receivables_resolution" ? (
          // cobranza tiene backend propio: se opera, no se consulta
          <CollectionsPanel onClose={() => setResolviendo(null)} />
        ) : c.component === "receipts_resolution" ? (
          // tickets también tiene backend propio (Vision + Browser Agent)
          <TicketResolutionPanel onClose={() => setResolviendo(null)} />
        ) : (
          <InlineAdvice
            question={preguntaPara(c.component, c.props)}
            onClose={() => setResolviendo(null)}
          />
        )
      ) : null}
      {drillables.has(c.insight_id) ? (
        <Button
          variant="ghost"
          size="sm"
          className="-mt-1 h-7 self-start px-2 text-xs text-muted-foreground"
          onClick={() =>
            onDeepDive(c.insight_id, String((c.props as { title?: string }).title ?? c.component))
          }
        >
          Entender por qué
        </Button>
      ) : null}
    </div>
    );
  };
  return (
    <div className="space-y-7">
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">
              {data.month} · {data.week_id}
            </p>
            <h2 className="mt-1 text-xl font-bold tracking-tight">Tu semana financiera</h2>
          </div>
        </div>
        {data.summary ? (
          <Alert className="border-primary/10 bg-gradient-to-r from-primary/[0.07] via-card to-card px-5 py-4">
            <AlertTitle className="text-primary">Resumen inteligente</AlertTitle>
            <AlertDescription>{data.summary}</AlertDescription>
          </Alert>
        ) : null}
      </header>

      <section className="space-y-3" aria-label="Métricas principales">
        <h2 className="text-sm font-bold tracking-tight">
          Métricas principales
        </h2>
        <div className="minorte-card-grid grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
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
          <h2 className="text-sm font-bold tracking-tight">
            Requieren acción
          </h2>
          <div
            className={cn(
              "minorte-card-grid grid gap-4 lg:grid-cols-2",
              resolviendo && "items-start",
            )}
          >
            {data.actions.map(wrap)}
          </div>
        </section>
      ) : null}

      {data.discovery.length > 0 ? (
        <section className="space-y-3" aria-label="Descubrimientos">
          <h2 className="text-sm font-bold tracking-tight">
            Descubrimientos
          </h2>
          <div
            className={cn(
              "minorte-card-grid grid gap-4 lg:grid-cols-2",
              resolviendo && "items-start",
            )}
          >
            {data.discovery.map(wrap)}
          </div>
        </section>
      ) : null}

      {scenarios.length > 0 ? (
        <section className="space-y-3" aria-label="Escenarios guardados">
          <h2 className="text-sm font-bold tracking-tight">
            Escenarios guardados
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            {scenarios.map((s) => (
              <div key={s.id} className="rounded-2xl border border-border/70 bg-card p-5 shadow-sm">
                <Badge variant="secondary">Escenario guardado</Badge>
                <p className="mt-2 text-sm font-bold">{s.titulo}</p>
                <p className="mt-1 text-sm text-muted-foreground">{s.detalle}</p>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <footer className="border-t pt-5 text-xs text-muted-foreground">
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
        <AlertDescription>
          <Markdown text={answer.respuesta} />
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
            <AlertDescription>
              <Markdown text={drill.data.texto} />
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
