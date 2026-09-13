"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  BookmarkPlus,
  Loader2,
  LogOut,
  MessageCircle,
  Sparkles,
  TriangleAlert,
  X,
} from "lucide-react";

import { AskBar } from "@/components/ask-bar";
import { BanorteMark } from "@/components/banorte-mark";
import { CollectionsPanel } from "@/components/collections-panel";
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
import { clearAccount, getAccount, initialsFor, type DummyAccount } from "@/lib/auth";
import type { GenCard } from "@/lib/types";
import { cn } from "@/lib/utils";

const LS_KEY = "minorte_conversation_id";

/**
 * Workspace MiNorte: weekly_dashboard (Analista) + consultant_view temporal.
 * "Entender por qué" y "Cómo resolverlo" se explican inline en su tarjeta.
 * La barra de críticos vive sobre cualquier modo.
 */
/** "Buenos días" 5-12h, "Buenas tardes" 12-19h, "Buenas noches" el resto. */
function saludoPorHora(hora: number): string {
  if (hora >= 5 && hora < 12) return "Buenos días";
  if (hora >= 12 && hora < 19) return "Buenas tardes";
  return "Buenas noches";
}

export default function Workspace() {
  const [busy, setBusy] = useState(false);
  const [toastError, setToastError] = useState(false);
  const [saludo, setSaludo] = useState<string | null>(null);

  useEffect(() => {
    const nombre = getAccount()?.nombre.split(" ")[0];
    setSaludo(nombre ? `${saludoPorHora(new Date().getHours())}, ${nombre}` : saludoPorHora(new Date().getHours()));
  }, []);
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
          <Link href="/" className="flex shrink-0 items-center" aria-label="MiNorte inicio">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/minorte-logo.png" alt="MiNorte" className="h-7 w-auto dark:hidden" />
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/minorte-logo-dark.png" alt="MiNorte" className="hidden h-7 w-auto dark:block" />
          </Link>

          <div className="ml-auto flex items-center gap-2">
            <SettingsPanel />
            <ThemeToggle />
            <CuentaAvatar />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-5 px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
        {saludo ? (
          <p className="text-2xl font-bold tracking-tight">{saludo}</p>
        ) : null}

        <div className="relative">
          <div className="pointer-events-none absolute inset-y-0 left-4 hidden items-center sm:flex">
            <Sparkles className="size-4 text-primary" />
          </div>
          <div className="sm:[&_input]:pl-10">
            <AskBar onAsk={preguntar} busy={busy} />
          </div>
          {answer ? (
            <div className="absolute inset-x-0 top-full z-30 pt-2">
              <AutoHidePanel key={answer.cid ?? answer.pregunta} onClose={() => setAnswer(null)}>
                <ConsultantView
                  answer={answer}
                  onClose={() => setAnswer(null)}
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
              </AutoHidePanel>
            </div>
          ) : null}
        </div>

        {error ? (
          <Alert variant="destructive">
            <AlertTitle>Falló la pregunta</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        <WeeklyView
          loading={dashboard.isLoading}
          error={dashboard.isError}
          retry={() => dashboard.refetch()}
          data={dashboard.data ?? null}
          onAsk={preguntar}
          scenarios={scenarios.data?.items ?? []}
        />
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

/** Avatar del header: iniciales reales de la cuenta demo vinculada +
 * "cerrar sesión" (mismo patrón anclado que SettingsPanel). */
function CuentaAvatar() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [account, setAccount] = useState<DummyAccount | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setAccount(getAccount());
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onClick = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  function cerrarSesion() {
    clearAccount();
    router.replace("/login");
  }

  return (
    <div className="relative" ref={box}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="ml-1 hidden size-9 place-items-center rounded-full bg-gradient-to-br from-primary to-red-700 text-xs font-bold text-white shadow-sm transition-transform hover:scale-105 sm:grid"
        aria-label="Tu cuenta"
      >
        {initialsFor(account?.nombre ?? "")}
      </button>
      {open ? (
        <div className="absolute right-0 top-11 z-50 w-56 rounded-xl border border-border/70 bg-card p-3 shadow-lg">
          <p className="truncate text-sm font-semibold">{account?.nombre || "Tu cuenta"}</p>
          <p className="truncate text-xs text-muted-foreground">{account?.correo || "—"}</p>
          {account?.banco ? (
            <p className="mt-1.5 text-[11px] text-muted-foreground">
              Vinculado a {account.banco} · {account.clabeEnmascarada}
            </p>
          ) : null}
          <Button
            variant="ghost"
            size="sm"
            onClick={cerrarSesion}
            className="mt-2 w-full justify-start text-destructive hover:text-destructive"
          >
            <LogOut className="size-4" /> Cerrar sesión
          </Button>
        </div>
      ) : null}
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

function WeeklyView({
  loading,
  error,
  retry,
  data,
  onAsk,
  scenarios,
}: {
  loading: boolean;
  error: boolean;
  retry: () => void;
  data: import("@/lib/types").GenDashboard | null;
  onAsk: (question: string) => void;
  scenarios: import("@/lib/types").SavedScenario[];
}) {
  // Antes de cualquier return: los hooks no pueden ir tras un early return.
  const [resolviendo, setResolviendo] = useState<string | null>(null);
  const [entendiendo, setEntendiendo] = useState<string | null>(null);

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
  // Anti-huérfanos: en grillas de 2 columnas, si las tarjetas de
  // contenido (no banners: esos van a fila completa) son impares, la
  // última se estira a la fila completa en vez de dejar un hoyo.
  const esBannerComp = (component: string) =>
    component === "receipts_resolution" ||
    component === "receivables_resolution";
  const conHuerfana = (lista: GenCard[]) => {
    const nContenido = lista.filter((c) => !esBannerComp(c.component)).length;
    let vista = -1;
    return lista.map((c) => {
      if (!esBannerComp(c.component)) vista += 1;
      return { tarjeta: c, esHuerfana: !esBannerComp(c.component) &&
        nContenido % 2 === 1 && vista === nContenido - 1 };
    });
  };
  const wrap = ({ tarjeta: c, esHuerfana }: { tarjeta: GenCard; esHuerfana: boolean }) => {
    const abierto = resolviendo === c.insight_id;
    const explicando = entendiendo === c.insight_id;
    const titulo = String((c.props as { title?: string }).title ?? c.component);
    // Los "Resolver" son barras delgadas: estirarlas deja un cajón vacío.
    const esBanner =
      c.component === "receipts_resolution" ||
      c.component === "receivables_resolution";
    // Anti-huérfanos: si las de contenido son impares, la última ocupa
    // la fila completa en vez de dejar un hoyo (solo en lg, 2 columnas).
    return (
    <div
      key={c.insight_id}
      className={cn(
        "relative flex flex-col gap-2",
        // Los "Resolver" son barras de aviso: fila completa y alto natural.
        esBanner && "self-start lg:col-span-2",
        esHuerfana && "lg:col-span-2",
        // Las de contenido se emparejan por fila y centran su contenido en
        // el alto sobrante, para que no quede un hueco al fondo. El panel
        // ("Cómo resolverlo" / "Entender por qué") flota encima de lo que
        // haya debajo en vez de empujarlo, así nadie más se reacomoda.
        !esBanner &&
          "h-full [&>*:first-child]:grow [&>*:first-child]:flex [&>*:first-child]:flex-col [&>*:first-child]:justify-center",
      )}
    >
      <DynamicUI
        schema={{ component: c.component, props: c.props } as never}
        onAction={() => setResolviendo(abierto ? null : c.insight_id)}
      />
      {drillables.has(c.insight_id) ? (
        <Button
          variant="ghost"
          size="sm"
          className="-mt-1 h-7 self-start px-2 text-xs text-muted-foreground"
          onClick={() => setEntendiendo(explicando ? null : c.insight_id)}
        >
          Entender por qué
        </Button>
      ) : null}
      {abierto || explicando ? (
        <div className="absolute inset-x-0 top-full z-30 space-y-2 pt-2">
          {abierto ? (
            <AutoHidePanel onClose={() => setResolviendo(null)}>
              {c.component === "receivables_resolution" ? (
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
              )}
            </AutoHidePanel>
          ) : null}
          {explicando ? (
            <AutoHidePanel onClose={() => setEntendiendo(null)}>
              <DrillInline
                insightId={c.insight_id}
                title={titulo}
                onAsk={onAsk}
                onClose={() => setEntendiendo(null)}
              />
            </AutoHidePanel>
          ) : null}
        </div>
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
              {data.month}
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
          <div className="minorte-card-grid grid gap-4 lg:grid-cols-2">
            {conHuerfana(data.actions).map(wrap)}
          </div>
        </section>
      ) : null}

      {data.discovery.length > 0 ? (
        <section className="space-y-3" aria-label="Descubrimientos">
          <h2 className="text-sm font-bold tracking-tight">
            Descubrimientos
          </h2>
          <div className="minorte-card-grid grid gap-4 lg:grid-cols-2">
            {conHuerfana(data.discovery).map(wrap)}
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

/**
 * Respuesta del asesor DENTRO de un desplegable bajo la barra de preguntas,
 * igual que "Cómo resolverlo" y "Entender por qué": nada de navegar a otra
 * vista, el dashboard completo sigue detrás.
 */
function ConsultantView({
  answer,
  onSave,
  onClose,
}: {
  answer: {
    pregunta: string;
    respuesta: string;
    tarjetas: GenCard[];
    evaluable: boolean;
  };
  onSave: () => Promise<void>;
  onClose: () => void;
}) {
  const [saved, setSaved] = useState(false);
  return (
    <div className="rounded-2xl border border-primary/20 bg-card/55 p-4 shadow-xl backdrop-blur-lg sm:p-5">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Badge variant="secondary">Respuesta</Badge>
          <h2 className="text-base font-bold">{answer.pregunta}</h2>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Cerrar">
          <X className="size-4" />
        </Button>
      </div>
      <div className="text-sm">
        <Markdown text={answer.respuesta} />
      </div>
      {answer.tarjetas.length > 0 ? (
        <div className="mt-4 grid gap-4 md:grid-cols-2">
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
          className="mt-4"
          onClick={async () => {
            await onSave();
            setSaved(true);
          }}
        >
          <BookmarkPlus className="size-4" /> Guardar escenario
        </Button>
      ) : null}
      {saved ? <Badge variant="success" className="mt-4">Escenario guardado</Badge> : null}
    </div>
  );
}

const AUTO_HIDE_MS = 5000;

/**
 * Los paneles flotantes se cierran solos si nadie interactúa con ellos:
 * el mouse encima pausa la cuenta regresiva, al salir se reinicia.
 */
function AutoHidePanel({
  onClose,
  children,
}: {
  onClose: () => void;
  children: ReactNode;
}) {
  const timer = useRef<number | null>(null);

  const schedule = () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(onClose, AUTO_HIDE_MS);
  };
  const cancel = () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
  };

  useEffect(() => {
    schedule();
    return cancel;
    // Solo al montar: cada apertura es una instancia nueva del panel.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div onMouseEnter={cancel} onMouseLeave={schedule}>
      {children}
    </div>
  );
}

/**
 * "Entender por qué" DENTRO de la tarjeta que lo pidió, igual que
 * InlineAdvice para "Cómo resolverlo": nada de navegar a otra vista,
 * el dashboard completo sigue detrás.
 */
function DrillInline({
  insightId,
  title,
  onAsk,
  onClose,
}: {
  insightId: string;
  title: string;
  onAsk: (q: string) => void;
  onClose: () => void;
}) {
  const drill = useQuery({
    queryKey: ["drill", insightId],
    queryFn: () => fetchDrill(insightId),
    retry: 1,
  });
  return (
    <div className="rounded-2xl border border-primary/20 bg-card/55 p-4 shadow-xl backdrop-blur-lg sm:p-5">
      <div className="mb-2 flex items-start justify-between gap-3">
        <p className="flex items-center gap-1.5 text-sm font-bold tracking-tight">
          <Sparkles className="size-4 text-primary" /> Por qué
        </p>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Cerrar">
          <X className="size-4" />
        </Button>
      </div>

      {drill.isLoading ? (
        <p className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Investigando…
        </p>
      ) : null}

      {drill.isError ? (
        <p role="alert" className="flex items-center gap-2 py-2 text-sm text-destructive">
          <TriangleAlert className="size-4" /> No pudimos investigarlo ahorita.
        </p>
      ) : null}

      {drill.data ? (
        <>
          <div className="text-sm">
            <Markdown text={drill.data.texto} />
          </div>
          {drill.data.tarjetas.length > 0 ? (
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              {drill.data.tarjetas.map((c, i) => (
                <DynamicUI
                  key={c.insight_id + i}
                  schema={{ component: c.component, props: c.props } as never}
                />
              ))}
            </div>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-2">
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
