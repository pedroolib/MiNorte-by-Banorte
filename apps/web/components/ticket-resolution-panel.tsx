"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Camera,
  Check,
  CheckCircle2,
  ChevronRight,
  Loader2,
  Lock,
  ShieldAlert,
  Upload,
  TriangleAlert,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  cancelTicket,
  confirmTicket,
  createTicket,
  fetchTicket,
  provideTicketInput,
  reconcileTicket,
  resumeTicket,
  startTicket,
  uploadTicketPhoto,
} from "@/lib/api";
import type {
  InvoiceRequestStatus,
  MatchCandidate,
  ReceiptExtraction,
  TicketDocument,
} from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Resolver "gastos sin factura" desde el dashboard: misma herramienta que
 * `/tickets` (foto real -> Vision -> match -> Browser Agent -> CFDI real),
 * envuelta con el estilo del panel (como CollectionsPanel/InlineAdvice) y
 * con texto pensado para el cliente, no para depurar. Corre siempre oculto
 * (headless) aquí: si el usuario elige "ventana visible" lo mandamos a
 * `/tickets` con la sesión ya creada, porque eso solo sirve corriendo
 * local (no en Docker) y se opera mejor en la página completa.
 */

const ACTIVE_STATUSES = new Set(["navegando", "esperando_confirmacion"]);
const RESUMABLE = new Set(["bloqueada_captcha", "bloqueada_limite_pasos", "fallida"]);

const STATUS_META: Record<
  InvoiceRequestStatus,
  { label: string; tone: "secondary" | "warning" | "destructive" | "success" }
> = {
  borrador: { label: "Preparando", tone: "secondary" },
  listo_para_portal: { label: "Listo para iniciar", tone: "secondary" },
  navegando: { label: "Trabajando en tu factura", tone: "secondary" },
  esperando_confirmacion: { label: "Esperando tu confirmación", tone: "warning" },
  bloqueada_captcha: { label: "Verificación de seguridad", tone: "warning" },
  bloqueada_auth: { label: "Necesita iniciar sesión", tone: "destructive" },
  bloqueada_datos_faltantes: { label: "Falta un dato", tone: "warning" },
  bloqueada_limite_pasos: { label: "Tardando más de lo normal", tone: "warning" },
  cancelada: { label: "Cancelado", tone: "secondary" },
  resuelta: { label: "Factura generada", tone: "success" },
  fallida: { label: "Hubo un problema", tone: "destructive" },
};

const BLOCKED_COPY: Partial<Record<InvoiceRequestStatus, string>> = {
  bloqueada_captcha:
    "El portal pidió verificar que no eres un robot. Ábrelo con la ventana visible para resolverlo a mano.",
  bloqueada_auth:
    "El portal pidió iniciar sesión, algo que no esperábamos — nos detuvimos por tu seguridad.",
  bloqueada_limite_pasos: "El agente está tardando más pasos de lo normal en este portal.",
  fallida: "Tuvimos un problema técnico al continuar. Tu sesión sigue activa, puedes reintentar.",
};

const FIELD_LABELS: Record<string, string> = {
  comercio: "Comercio",
  rfc_comercio: "RFC del comercio",
  total: "Total",
  fecha: "Fecha",
  folio: "Folio del ticket",
  folio_ticket: "Folio del ticket",
  portal_facturacion: "Portal de facturación",
  rfc_receptor: "RFC",
  razon_social_receptor: "Razón social / Nombre",
  email_receptor: "Correo electrónico",
  cp_receptor: "Código postal",
  regimen_fiscal_receptor: "Régimen fiscal",
  uso_cfdi: "Uso de CFDI",
  credenciales: "Credenciales de acceso al portal",
};

function friendlyField(key: string | null | undefined): string {
  if (!key) return "un dato";
  return FIELD_LABELS[key] ?? key.replace(/_/g, " ");
}

const money = new Intl.NumberFormat("es-MX", {
  style: "currency",
  currency: "MXN",
  minimumFractionDigits: 2,
});

function moneyOrDash(v: string | number | null) {
  if (v === null || v === undefined) return "—";
  return money.format(Number(v));
}

function normalizeUrl(v: string) {
  return /^https?:\/\//i.test(v) ? v : `https://${v}`;
}

function StatusPill({ status }: { status: InvoiceRequestStatus }) {
  const meta = STATUS_META[status] ?? { label: status, tone: "secondary" as const };
  const spin = status === "navegando";
  return (
    <Badge variant={meta.tone}>
      {spin ? <Loader2 className="size-3 animate-spin" /> : null}
      {meta.label}
    </Badge>
  );
}

function CapturaFoto({ onCapture }: { onCapture: (blob: Blob) => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [activa, setActiva] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function abrir() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
        audio: false,
      });
      streamRef.current = stream;
      setActiva(true);
      requestAnimationFrame(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch(() => {});
        }
      });
    } catch (e) {
      setError("No pudimos abrir tu cámara. Revisa los permisos del navegador.");
    }
  }

  function cerrar() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setActiva(false);
  }

  function tomar() {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (blob) onCapture(blob);
      cerrar();
    }, "image/jpeg", 0.92);
  }

  useEffect(() => () => cerrar(), []);

  if (activa) {
    return (
      <div className="space-y-2">
        {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
        <video ref={videoRef} className="w-full max-w-sm rounded-lg bg-black" playsInline muted />
        <div className="flex gap-2">
          <Button size="sm" onClick={tomar} className="rounded-full">
            <Camera className="size-4" /> Tomar foto
          </Button>
          <Button size="sm" variant="ghost" onClick={cerrar}>
            Cancelar
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button size="sm" variant="outline" onClick={abrir} className="rounded-full">
        <Camera className="size-4" /> Tomar foto
      </Button>
      <label>
        <Button size="sm" variant="outline" className="rounded-full" asChild>
          <span className="cursor-pointer">
            <Upload className="size-4" /> Subir foto
          </span>
        </Button>
        <input
          type="file"
          accept="image/*"
          capture="environment"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onCapture(f);
            e.target.value = "";
          }}
        />
      </label>
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
    </div>
  );
}

export function TicketResolutionPanel({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const router = useRouter();

  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [document_, setDocument] = useState<TicketDocument | null>(null);
  const [extraction, setExtraction] = useState<ReceiptExtraction | null>(null);
  const [candidates, setCandidates] = useState<MatchCandidate[]>([]);
  const [selectedTxn, setSelectedTxn] = useState<string | "">("");
  const [receptorGenerico, setReceptorGenerico] = useState(false);
  const [ticketId, setTicketId] = useState<string | null>(null);
  const [portalUrl, setPortalUrl] = useState("");
  const [cfdiXml, setCfdiXml] = useState("");
  const [missingValue, setMissingValue] = useState("");
  // Una sola bandera de "acción en curso": solo puede haber una a la vez
  // en este panel, así que un botón basta para saber si mostrar su spinner.
  const [busy, setBusy] = useState<
    | "create"
    | "start"
    | "open_visible"
    | "confirm"
    | "reject"
    | "input"
    | "cancel"
    | "resume"
    | "reconcile"
    | null
  >(null);

  const ticket = useQuery({
    queryKey: ["ticket", ticketId],
    queryFn: () => fetchTicket(ticketId as string),
    enabled: !!ticketId,
    refetchInterval: (q) =>
      q.state.data && ACTIVE_STATUSES.has(q.state.data.status) ? 1500 : false,
  });
  const t = ticket.data;

  // Un error de una acción vieja (ej. un provide_input que llegó tarde,
  // ya con el ticket en otro status por el polling) no debe quedarse
  // pegado en pantalla una vez que el estado real ya avanzó.
  useEffect(() => {
    setError(null);
  }, [t?.status]);

  async function handleCapture(blob: Blob) {
    setPhotoUrl(URL.createObjectURL(blob));
    setUploading(true);
    setError(null);
    setDocument(null);
    setExtraction(null);
    setCandidates([]);
    try {
      const r = await uploadTicketPhoto(blob);
      setDocument(r.document);
      setExtraction(r.extraction);
      setCandidates(r.candidates);
      if (r.candidates[0]) setSelectedTxn(r.candidates[0].transaction_id);
      if (r.extraction.portal_facturacion) {
        setPortalUrl(normalizeUrl(r.extraction.portal_facturacion));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "No pudimos leer el ticket. Intenta con otra foto.");
    } finally {
      setUploading(false);
    }
  }

  async function handleCreateTicket() {
    if (!document_) return;
    setError(null);
    setBusy("create");
    try {
      const nt = await createTicket(document_.id, selectedTxn || null, receptorGenerico);
      setTicketId(nt.id);
      qc.setQueryData(["ticket", nt.id], nt);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No pudimos preparar la factura.");
    } finally {
      setBusy(null);
    }
  }

  async function handleStartAqui() {
    if (!ticketId || !portalUrl.trim()) {
      setError("Nos falta la dirección del portal de facturación del comercio.");
      return;
    }
    setError(null);
    setBusy("start");
    try {
      const nt = await startTicket(ticketId, portalUrl.trim(), true);
      qc.setQueryData(["ticket", ticketId], nt);
      ticket.refetch();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No pudimos iniciar la facturación.");
    } finally {
      setBusy(null);
    }
  }

  async function handleAbrirVisible() {
    if (!ticketId || !portalUrl.trim()) {
      setError("Nos falta la dirección del portal de facturación del comercio.");
      return;
    }
    setError(null);
    setBusy("open_visible");
    try {
      // Arranca de verdad con ventana visible antes de mandar a /tickets —
      // si ya había una sesión oculta corriendo, start() la cierra y abre
      // una nueva; así la página a la que llegamos ya tiene al agente
      // trabajando en vivo, no un formulario pidiendo empezar de nuevo.
      const nt = await startTicket(ticketId, portalUrl.trim(), false);
      qc.setQueryData(["ticket", ticketId], nt);
      router.push(`/tickets?ticket=${ticketId}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No pudimos abrir el navegador visible.");
    } finally {
      setBusy(null);
    }
  }

  async function handleResume(extra = 0) {
    if (!ticketId) return;
    setError(null);
    setBusy("resume");
    try {
      const nt = await resumeTicket(ticketId, extra);
      qc.setQueryData(["ticket", ticketId], nt);
      ticket.refetch();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No pudimos continuar.");
    } finally {
      setBusy(null);
    }
  }

  async function handleConfirm(approve: boolean) {
    if (!ticketId) return;
    setError(null);
    setBusy(approve ? "confirm" : "reject");
    try {
      const nt = await confirmTicket(ticketId, approve);
      qc.setQueryData(["ticket", ticketId], nt);
      ticket.refetch();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No pudimos registrar tu respuesta.");
    } finally {
      setBusy(null);
    }
  }

  async function handleProvideInput() {
    const field = t?.pending_action?.missing_field;
    if (!ticketId || !field || !missingValue.trim()) return;
    setError(null);
    setBusy("input");
    try {
      const nt = await provideTicketInput(ticketId, field, missingValue.trim());
      qc.setQueryData(["ticket", ticketId], nt);
      setMissingValue("");
      ticket.refetch();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No pudimos enviar el dato.");
    } finally {
      setBusy(null);
    }
  }

  async function handleCancel() {
    if (!ticketId) return;
    setError(null);
    setBusy("cancel");
    try {
      const nt = await cancelTicket(ticketId);
      qc.setQueryData(["ticket", ticketId], nt);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No pudimos cerrar la sesión.");
    } finally {
      setBusy(null);
    }
  }

  async function handleReconcile() {
    if (!ticketId) return;
    setError(null);
    setBusy("reconcile");
    try {
      const r = await reconcileTicket(ticketId, cfdiXml.trim() || undefined);
      qc.setQueryData(["ticket", ticketId], r.ticket);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No pudimos registrar el CFDI.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="rounded-2xl border border-primary/20 bg-card/55 p-4 shadow-xl backdrop-blur-lg sm:p-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold tracking-tight">Resolver gasto sin factura</h3>
          <p className="text-xs text-muted-foreground">
            Sube la foto de tu ticket y nosotros nos encargamos del resto: leerlo, encontrar el
            movimiento correspondiente y tramitar tu factura real con el comercio.
          </p>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Cerrar">
          <X className="size-4" />
        </Button>
      </div>

      {error ? (
        <p role="alert" className="mb-3 flex items-center gap-2 text-xs text-destructive">
          <TriangleAlert className="size-3.5 shrink-0" /> {error}
        </p>
      ) : null}

      {/* Paso 1: foto */}
      {!ticketId && (
        <div className="space-y-3">
          {photoUrl ? (
            <div className="flex items-start gap-3">
              <img src={photoUrl} alt="Foto del ticket" className="h-28 w-auto rounded-lg border object-cover" />
              <div className="flex flex-col gap-2">
                {uploading ? (
                  <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Loader2 className="size-3.5 animate-spin" /> Leyendo tu ticket…
                  </p>
                ) : (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setPhotoUrl(null);
                      setDocument(null);
                      setExtraction(null);
                      setCandidates([]);
                    }}
                  >
                    Tomar otra foto
                  </Button>
                )}
              </div>
            </div>
          ) : (
            <CapturaFoto onCapture={handleCapture} />
          )}

          {extraction ? (
            <div className="space-y-4 rounded-xl border border-border/70 bg-muted/30 p-3">
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                <dt className="text-muted-foreground">Comercio</dt>
                <dd className="font-medium">{extraction.comercio ?? "—"}</dd>
                <dt className="text-muted-foreground">Total</dt>
                <dd className="font-medium">{moneyOrDash(extraction.total)}</dd>
                <dt className="text-muted-foreground">Fecha</dt>
                <dd className="font-medium">{extraction.fecha ?? "—"}</dd>
                <dt className="text-muted-foreground">Folio</dt>
                <dd className="font-medium">{extraction.folio ?? "—"}</dd>
              </dl>
              {extraction.campos_no_legibles.length > 0 ? (
                <p className="text-xs text-amber-700 dark:text-amber-400">
                  No pudimos leer bien: {extraction.campos_no_legibles.map(friendlyField).join(", ")}.
                  Puedes seguir — lo pedimos más adelante si hace falta.
                </p>
              ) : null}

              <div>
                <p className="mb-2 text-xs font-semibold">¿Con qué movimiento de tu cuenta corresponde?</p>
                <div className="space-y-1.5">
                  {candidates.map((c) => {
                    const selected = selectedTxn === c.transaction_id;
                    return (
                      <button
                        key={c.transaction_id}
                        type="button"
                        onClick={() => setSelectedTxn(c.transaction_id)}
                        className={cn(
                          "flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-xs transition-colors",
                          selected
                            ? "border-primary bg-primary/10"
                            : "border-border/70 bg-background hover:border-primary/40 hover:bg-muted/50",
                        )}
                      >
                        <span className="min-w-0">
                          <span className="block truncate font-medium">{c.merchant_name}</span>
                          <span className="text-muted-foreground">
                            {moneyOrDash(c.amount)} · {c.date.slice(0, 10)}
                          </span>
                        </span>
                        {selected ? (
                          <CheckCircle2 className="size-4 shrink-0 text-primary" />
                        ) : (
                          <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                        )}
                      </button>
                    );
                  })}
                  <button
                    type="button"
                    onClick={() => setSelectedTxn("")}
                    className={cn(
                      "flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-xs text-muted-foreground transition-colors",
                      selectedTxn === ""
                        ? "border-primary bg-primary/10 text-foreground"
                        : "border-dashed border-border/70 hover:border-primary/40",
                    )}
                  >
                    Ninguno — solo tramitar la factura
                    {selectedTxn === "" ? <CheckCircle2 className="size-4 shrink-0 text-primary" /> : null}
                  </button>
                </div>
              </div>

              <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-border/70 bg-background px-3 py-2 text-xs">
                <input
                  type="checkbox"
                  className="mt-0.5 accent-[hsl(var(--primary))]"
                  checked={receptorGenerico}
                  onChange={(e) => setReceptorGenerico(e.target.checked)}
                />
                <span>
                  <span className="font-medium">Facturar como consumidor final</span>
                  <span className="block text-muted-foreground">
                    Útil si el RFC de la empresa aún no está dado de alta ante el SAT.
                  </span>
                </span>
              </label>

              <Button
                size="sm"
                onClick={handleCreateTicket}
                disabled={busy === "create"}
                className="w-full rounded-full sm:w-auto"
              >
                {busy === "create" ? <Loader2 className="size-4 animate-spin" /> : null}
                Confirmar y preparar factura
              </Button>
            </div>
          ) : null}
        </div>
      )}

      {/* Paso 2: browser agent */}
      {ticketId && t && (
        <div className="space-y-3">
          <StatusPill status={t.status} />

          {t.status === "listo_para_portal" ? (
            <div className="space-y-2 rounded-xl border border-border/70 bg-muted/30 p-3">
              <Input
                placeholder="https://portal-real-de-facturacion.com"
                value={portalUrl}
                onChange={(e) => setPortalUrl(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                {extraction?.portal_facturacion
                  ? "Tomamos esta dirección del ticket — confirma que sea la correcta antes de continuar."
                  : "Escribe la dirección del portal de facturación del comercio."}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  onClick={handleStartAqui}
                  disabled={busy !== null}
                  className="rounded-full"
                >
                  {busy === "start" ? <Loader2 className="size-4 animate-spin" /> : null}
                  Tramitar factura
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleAbrirVisible}
                  disabled={busy !== null}
                  className="rounded-full"
                >
                  {busy === "open_visible" ? <Loader2 className="size-4 animate-spin" /> : null}
                  Ver el proceso en vivo
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Si el portal suele pedir verificación de seguridad, usa "Ver el proceso en vivo"
                para poder resolverla tú mismo.
              </p>
            </div>
          ) : null}

          {t.status === "navegando" ? (
            <p className="flex items-center gap-2 rounded-xl border border-border/70 bg-muted/30 p-3 text-sm text-muted-foreground">
              <Loader2 className="size-4 shrink-0 animate-spin" /> Estamos llenando tu factura en el
              portal del comercio…
            </p>
          ) : null}

          {t.status === "esperando_confirmacion" && t.pending_action ? (
            <div className="space-y-3 rounded-xl border border-amber-300/60 bg-amber-50 p-3 text-xs dark:bg-amber-950/30">
              <div className="flex items-start gap-2">
                <ShieldAlert className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
                <p>
                  Tu factura está lista para enviarse. Antes de hacerlo de verdad, confírmanos que
                  quieres continuar
                  {t.pending_action.target?.label ? (
                    <>
                      {" "}
                      (se hará clic en <b>{t.pending_action.target.label}</b>)
                    </>
                  ) : null}
                  .
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={() => handleConfirm(true)}
                  disabled={busy !== null}
                  className="rounded-full"
                >
                  {busy === "confirm" ? <Loader2 className="size-4 animate-spin" /> : <Check className="size-4" />}
                  Confirmar y enviar
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleConfirm(false)}
                  disabled={busy !== null}
                >
                  {busy === "reject" ? <Loader2 className="size-4 animate-spin" /> : null}
                  Cancelar
                </Button>
              </div>
            </div>
          ) : null}

          {t.status === "bloqueada_datos_faltantes" && t.pending_action ? (
            <div className="space-y-2 rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-xs">
              <p>
                Necesitamos <b>{friendlyField(t.pending_action.missing_field)}</b>: no venía en tu
                ticket.
              </p>
              <div className="flex flex-wrap gap-2">
                <Input
                  placeholder={friendlyField(t.pending_action.missing_field)}
                  value={missingValue}
                  onChange={(e) => setMissingValue(e.target.value)}
                  className="max-w-xs"
                />
                <Button
                  size="sm"
                  onClick={handleProvideInput}
                  disabled={!missingValue.trim() || busy === "input"}
                  className="rounded-full"
                >
                  {busy === "input" ? <Loader2 className="size-4 animate-spin" /> : null}
                  Continuar
                </Button>
                <Button size="sm" variant="ghost" onClick={handleCancel} disabled={busy === "cancel"}>
                  {busy === "cancel" ? <Loader2 className="size-4 animate-spin" /> : null}
                  Cerrar
                </Button>
              </div>
            </div>
          ) : null}

          {t.status in BLOCKED_COPY && t.status !== "bloqueada_datos_faltantes" ? (
            <div className="space-y-2 rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-xs">
              <div className="flex items-start gap-2">
                <Lock className="mt-0.5 size-4 shrink-0 text-destructive" />
                <p>{BLOCKED_COPY[t.status]}</p>
              </div>
              {t.status === "fallida" && t.pending_action?.error ? (
                <details className="text-muted-foreground">
                  <summary className="cursor-pointer select-none">Detalles técnicos</summary>
                  <pre className="mt-1 whitespace-pre-wrap rounded-md bg-background p-2 text-[11px]">
                    {t.pending_action.error}
                  </pre>
                </details>
              ) : null}
              <div className="flex flex-wrap gap-2">
                {t.status === "bloqueada_captcha" ? (
                  <Button
                    size="sm"
                    onClick={handleAbrirVisible}
                    disabled={busy !== null}
                    className="rounded-full"
                  >
                    {busy === "open_visible" ? <Loader2 className="size-4 animate-spin" /> : null}
                    Ver el proceso en vivo
                  </Button>
                ) : null}
                {RESUMABLE.has(t.status) && t.status !== "bloqueada_captcha" ? (
                  <Button
                    size="sm"
                    onClick={() => handleResume(t.status === "bloqueada_limite_pasos" ? 10 : 0)}
                    disabled={busy === "resume"}
                    className="rounded-full"
                  >
                    {busy === "resume" ? <Loader2 className="size-4 animate-spin" /> : null}
                    {t.status === "bloqueada_limite_pasos" ? "Seguir intentando" : "Reintentar"}
                  </Button>
                ) : null}
                <Button size="sm" variant="ghost" onClick={handleCancel} disabled={busy === "cancel"}>
                  {busy === "cancel" ? <Loader2 className="size-4 animate-spin" /> : null}
                  Cerrar sesión
                </Button>
              </div>
            </div>
          ) : null}

          {t.status === "resuelta" && t.cfdi_uuid ? (
            <div className="space-y-1 rounded-xl border border-emerald-300/60 bg-emerald-50 p-3 text-xs dark:bg-emerald-950/30">
              <p className="flex items-center gap-1.5 font-medium">
                <CheckCircle2 className="size-4 text-emerald-600 dark:text-emerald-400" />
                ¡Listo! Tu factura quedó registrada.
              </p>
              <p className="text-muted-foreground">
                Folio fiscal: <span className="font-mono text-foreground">{t.cfdi_uuid}</span>
              </p>
            </div>
          ) : null}

          {t.status === "resuelta" && !t.cfdi_uuid ? (
            <div className="space-y-2 rounded-xl border border-emerald-300/60 bg-emerald-50 p-3 text-xs dark:bg-emerald-950/30">
              <p>
                Terminamos en el portal, pero no encontramos un archivo XML para descargar
                automáticamente. Si ya lo tienes (por correo, por ejemplo), pégalo aquí para
                completar el registro:
              </p>
              <textarea
                value={cfdiXml}
                onChange={(e) => setCfdiXml(e.target.value)}
                placeholder="<cfdi:Comprobante ...>...</cfdi:Comprobante>"
                className="h-24 w-full rounded-md border border-input bg-transparent p-2 text-[11px] outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
              />
              <Button size="sm" onClick={handleReconcile} disabled={busy === "reconcile"} className="rounded-full">
                {busy === "reconcile" ? <Loader2 className="size-4 animate-spin" /> : null}
                Registrar factura
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
