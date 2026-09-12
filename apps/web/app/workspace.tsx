"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  ArrowLeft,
  BookmarkPlus,
  HandCoins,
  LayoutDashboard,
  MessageCircle,
  MessageSquareText,
  Settings,
  Sparkles,
} from "lucide-react";

import { AskBar } from "@/components/ask-bar";
import { CriticalBar } from "@/components/critical-bar";
import { Markdown } from "@/components/markdown";
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
import { ThemeToggle } from "@/components/theme-toggle";
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

          <nav className="hidden items-center gap-1 md:flex" aria-label="Navegación principal">
            <NavItem href="/" label="Resumen" icon={LayoutDashboard} active />
            <NavItem href="/cobranza" label="Cobranza" icon={HandCoins} />
            <NavItem href="/chat" label="Consultor" icon={MessageSquareText} />
            <NavItem href="/ajustes" label="Ajustes" icon={Settings} />
          </nav>

          <div className="ml-auto flex items-center gap-2">
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
          onAction={(c, p) => preguntar(preguntaPara(c, p))}
          onDeepDive={(id, title) =>
            setMode({ name: "deep_dive", insightId: id, title })
          }
          scenarios={scenarios.data?.items ?? []}
        />
        ) : null}
      </main>
    </div>
  );
}

function BanorteMark() {
  return (
    <span className="relative block size-9 rounded-xl bg-primary shadow-[0_8px_18px_-8px_rgba(235,0,41,0.85)]">
      <span className="absolute left-[9px] top-[9px] h-2 w-4 -rotate-12 rounded-full bg-white" />
      <span className="absolute bottom-[9px] right-[9px] h-2 w-4 -rotate-12 rounded-full bg-white/75" />
    </span>
  );
}

function NavItem({
  href,
  label,
  icon: Icon,
  active = false,
}: {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  active?: boolean;
}) {
  return (
    <Button
      asChild
      variant={active ? "secondary" : "ghost"}
      size="sm"
      className={active ? "rounded-full text-primary" : "rounded-full text-muted-foreground"}
    >
      <Link href={href} aria-current={active ? "page" : undefined}>
        <Icon className="size-3.5" />
        {label}
      </Link>
    </Button>
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
    <div className="space-y-7">
      <header className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">
              {data.month} · {data.week_id}
            </p>
            <h2 className="mt-1 text-xl font-bold tracking-tight">Tu semana financiera</h2>
          </div>
          <Badge variant="outline" className="rounded-full bg-card px-3 py-1.5">
            MXN · Pesos mexicanos
          </Badge>
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
          <div className="minorte-card-grid grid gap-4 lg:grid-cols-2">
            {data.actions.map(wrap)}
          </div>
        </section>
      ) : null}

      {data.discovery.length > 0 ? (
        <section className="space-y-3" aria-label="Descubrimientos">
          <h2 className="text-sm font-bold tracking-tight">
            Descubrimientos
          </h2>
          <div className="minorte-card-grid grid gap-4 lg:grid-cols-2">
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
