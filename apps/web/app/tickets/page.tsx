"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  cancelTicket,
  confirmTicket,
  createTicket,
  fetchTicket,
  provideTicketInput,
  reconcileTicket,
  resumeTicket,
  startTicket,
  ticketScreenshotUrl,
  uploadTicketPhoto,
} from "@/lib/api";
import type { MatchCandidate, ReceiptExtraction, TicketDocument } from "@/lib/types";

/**
 * /tickets — ticket real -> factura real (spec #3.3 caso 1, TIER 2), SIN diseño.
 * Foto (cámara del dispositivo o archivo) -> extracción Vision -> match ->
 * Browser Agent sobre el portal real -> confirmación humana -> CFDI.
 * Backend: app/operator/receipts.py + app/browser/agent.py + /api/tickets/*.
 */

const ACTIVE_STATUSES = new Set(["navegando", "esperando_confirmacion"]);
// Frenos que un humano puede levantar sin reiniciar la sesión: captcha
// resuelto a mano en la ventana visible, seguir más allá del límite, o
// reintentar tras un error técnico transitorio (la página sigue viva).
const RESUMABLE = new Set(["bloqueada_captcha", "bloqueada_limite_pasos", "fallida"]);
const BLOCKED: Record<string, string> = {
  bloqueada_captcha: "El portal pidió un CAPTCHA: no se puede resolver solo.",
  bloqueada_auth: "El portal pidió iniciar sesión (no esperado): se detuvo por seguridad.",
  bloqueada_datos_faltantes: "Falta un dato que Vision no pudo leer del ticket.",
  bloqueada_limite_pasos: "Se alcanzó el límite de pasos sin terminar.",
  fallida: "Error técnico al ejecutar la acción (la sesión sigue viva, se puede reintentar).",
};

function money(v: string | number | null) {
  if (v === null || v === undefined) return "—";
  return `$${Number(v).toLocaleString("es-MX", { minimumFractionDigits: 2 })}`;
}

function normalizeUrl(v: string) {
  return /^https?:\/\//i.test(v) ? v : `https://${v}`;
}

// ---------- Cámara real del dispositivo ----------

function CameraCapture({ onCapture }: { onCapture: (blob: Blob) => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [active, setActive] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function openCamera() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
        audio: false,
      });
      streamRef.current = stream;
      setActive(true);
      // el <video> se monta en este render; conectar el stream en el próximo tick
      requestAnimationFrame(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch(() => {});
        }
      });
    } catch (e) {
      setError(
        "no se pudo abrir la cámara (¿permisos del navegador?): " + String(e),
      );
    }
  }

  function closeCamera() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setActive(false);
  }

  function takePhoto() {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (blob) onCapture(blob);
        closeCamera();
      },
      "image/jpeg",
      0.92,
    );
  }

  useEffect(() => () => closeCamera(), []);

  return (
    <div>
      {!active && (
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button onClick={openCamera}>📷 Abrir cámara</button>
          <label
            style={{
              border: "1px solid #999",
              padding: "6px 10px",
              cursor: "pointer",
              fontSize: 13,
            }}
          >
            o subir/tomar foto
            <input
              type="file"
              accept="image/*"
              capture="environment"
              style={{ display: "none" }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) onCapture(f);
                e.target.value = "";
              }}
            />
          </label>
        </div>
      )}
      {error && <p style={{ color: "red", fontSize: 13 }}>{error}</p>}
      {active && (
        <div>
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <video
            ref={videoRef}
            style={{ width: "100%", maxWidth: 420, background: "#000" }}
            playsInline
            muted
          />
          <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
            <button onClick={takePhoto}>Tomar foto</button>
            <button onClick={closeCamera}>Cancelar</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------- Página ----------

export default function Tickets() {
  return (
    <Suspense fallback={null}>
      <TicketsInner />
    </Suspense>
  );
}

function TicketsInner() {
  const qc = useQueryClient();
  const searchParams = useSearchParams();
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [document_, setDocument] = useState<TicketDocument | null>(null);
  const [extraction, setExtraction] = useState<ReceiptExtraction | null>(null);
  const [candidates, setCandidates] = useState<MatchCandidate[]>([]);
  const [selectedTxn, setSelectedTxn] = useState<string | "">("");
  const [receptorGenerico, setReceptorGenerico] = useState(false);
  const [ticketId, setTicketId] = useState<string | null>(() => searchParams.get("ticket"));
  const [portalUrl, setPortalUrl] = useState(() => searchParams.get("portal") ?? "");
  const [cfdiXml, setCfdiXml] = useState("");
  const [missingValue, setMissingValue] = useState("");
  const [showBrowser, setShowBrowser] = useState(() => searchParams.get("show") === "1");

  const ticket = useQuery({
    queryKey: ["ticket", ticketId],
    queryFn: () => fetchTicket(ticketId as string),
    enabled: !!ticketId,
    refetchInterval: (q) =>
      q.state.data && ACTIVE_STATUSES.has(q.state.data.status) ? 1500 : false,
  });

  async function handleCapture(blob: Blob) {
    setPhotoUrl(URL.createObjectURL(blob));
    setUploading(true);
    setMsg(null);
    setDocument(null);
    setExtraction(null);
    setCandidates([]);
    setTicketId(null);
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
      setMsg(String(e));
    } finally {
      setUploading(false);
    }
  }

  async function handleCreateTicket() {
    if (!document_) return;
    setMsg(null);
    try {
      const t = await createTicket(document_.id, selectedTxn || null, receptorGenerico);
      setTicketId(t.id);
      qc.setQueryData(["ticket", t.id], t);
    } catch (e) {
      setMsg(String(e));
    }
  }

  async function handleStart() {
    if (!ticketId || !portalUrl.trim()) {
      setMsg("pega la URL real del portal de facturación del comercio");
      return;
    }
    setMsg(null);
    try {
      const t = await startTicket(ticketId, portalUrl.trim(), !showBrowser);
      qc.setQueryData(["ticket", ticketId], t);
      ticket.refetch();
    } catch (e) {
      setMsg(String(e));
    }
  }

  async function handleResume(extraSteps = 0) {
    if (!ticketId) return;
    setMsg(null);
    try {
      const t = await resumeTicket(ticketId, extraSteps);
      qc.setQueryData(["ticket", ticketId], t);
      ticket.refetch();
    } catch (e) {
      setMsg(String(e));
    }
  }

  async function handleConfirm(approve: boolean) {
    if (!ticketId) return;
    try {
      const t = await confirmTicket(ticketId, approve);
      qc.setQueryData(["ticket", ticketId], t);
      ticket.refetch();
    } catch (e) {
      setMsg(String(e));
    }
  }

  async function handleProvideInput() {
    const field = ticket.data?.pending_action?.missing_field;
    if (!ticketId || !field || !missingValue.trim()) return;
    setMsg(null);
    try {
      const t = await provideTicketInput(ticketId, field, missingValue.trim());
      qc.setQueryData(["ticket", ticketId], t);
      setMissingValue("");
      ticket.refetch();
    } catch (e) {
      setMsg(String(e));
    }
  }

  async function handleCancel() {
    if (!ticketId) return;
    const t = await cancelTicket(ticketId);
    qc.setQueryData(["ticket", ticketId], t);
  }

  async function handleReconcile() {
    if (!ticketId) return;
    try {
      const r = await reconcileTicket(ticketId, cfdiXml.trim() || undefined);
      setMsg(JSON.stringify(r.result));
      qc.setQueryData(["ticket", ticketId], r.ticket);
    } catch (e) {
      setMsg(String(e));
    }
  }

  function reiniciar() {
    setPhotoUrl(null);
    setDocument(null);
    setExtraction(null);
    setCandidates([]);
    setSelectedTxn("");
    setTicketId(null);
    setPortalUrl("");
    setCfdiXml("");
    setMsg(null);
  }

  const t = ticket.data;

  return (
    <main style={{ maxWidth: 720, margin: "0 auto", padding: 16, fontFamily: "monospace" }}>
      <h1>Tickets — foto real a factura real (sin diseño)</h1>
      <p>
        <a href="/">← inicio</a> · <a href="/debug">debug</a>
      </p>
      {msg && <p style={{ background: "#eee", padding: 8 }}>{msg}</p>}

      {/* Paso 1: foto */}
      <section style={{ marginTop: 16 }}>
        <h3>1. Foto del ticket</h3>
        {!photoUrl && <CameraCapture onCapture={handleCapture} />}
        {photoUrl && (
          <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
            <img src={photoUrl} alt="ticket" style={{ maxWidth: 200, border: "1px solid #ccc" }} />
            <div>
              {uploading && <p>extrayendo con Vision…</p>}
              {!uploading && !document_ && <button onClick={reiniciar}>reintentar</button>}
              {document_ && <button onClick={reiniciar}>tomar otra foto</button>}
            </div>
          </div>
        )}
      </section>

      {/* Paso 2: extracción + match */}
      {extraction && !ticketId && (
        <section style={{ marginTop: 16 }}>
          <h3>2. Lo que Vision leyó</h3>
          <table border={1} cellPadding={6} style={{ fontSize: 12, borderCollapse: "collapse" }}>
            <tbody>
              <tr><td>comercio</td><td>{extraction.comercio ?? "—"}</td></tr>
              <tr><td>RFC comercio</td><td>{extraction.rfc_comercio ?? "—"}</td></tr>
              <tr><td>total</td><td>{money(extraction.total)}</td></tr>
              <tr><td>fecha</td><td>{extraction.fecha ?? "—"}</td></tr>
              <tr><td>folio</td><td>{extraction.folio ?? "—"}</td></tr>
              <tr><td>portal de facturación</td><td>{extraction.portal_facturacion ?? "—"}</td></tr>
              <tr><td>confianza</td><td>{extraction.confianza}</td></tr>
            </tbody>
          </table>
          {extraction.campos_no_legibles.length > 0 && (
            <p style={{ color: "#b45309" }}>
              no legible: {extraction.campos_no_legibles.join(", ")}
            </p>
          )}

          <h4 style={{ marginTop: 12 }}>Candidatos de match (movimiento bancario)</h4>
          {candidates.length === 0 && <p>sin candidatos (¿ya conciliado o gasto no registrado?)</p>}
          {candidates.map((c) => (
            <label key={c.transaction_id} style={{ display: "block", fontSize: 12 }}>
              <input
                type="radio"
                name="txn"
                checked={selectedTxn === c.transaction_id}
                onChange={() => setSelectedTxn(c.transaction_id)}
              />{" "}
              {c.merchant_name} · {money(c.amount)} · {c.date.slice(0, 10)} · score={Number(c.score).toFixed(2)}
            </label>
          ))}
          <label style={{ display: "block", fontSize: 12 }}>
            <input type="radio" name="txn" checked={selectedTxn === ""} onChange={() => setSelectedTxn("")} />{" "}
            ninguno (facturar sin conciliar un movimiento)
          </label>

          <label style={{ display: "block", fontSize: 12, marginTop: 8 }}>
            <input
              type="checkbox"
              checked={receptorGenerico}
              onChange={(e) => setReceptorGenerico(e.target.checked)}
            />{" "}
            usar RFC genérico "Público en general" (XAXX010101000) en vez
            del RFC de la empresa demo
          </label>
          <p style={{ fontSize: 11, color: "#666" }}>
            El RFC de la empresa del seed (CNM160812AB1) no existe de
            verdad en el SAT — un portal real lo va a rechazar. Marca
            esto para probar el flujo completo hasta un CFDI real y
            válido (no se atribuye a ningún negocio, es el mismo RFC que
            usa cualquier venta al público en general).
          </p>

          <button style={{ marginTop: 8 }} onClick={handleCreateTicket}>
            Confirmar y preparar factura →
          </button>
        </section>
      )}

      {/* Paso 3: browser agent */}
      {ticketId && t && (
        <section style={{ marginTop: 16 }}>
          <h3>3. Facturación (Browser Agent, portal real)</h3>
          <p>estado: <b>{t.status}</b></p>

          <details open>
            <summary>payload real para el agente</summary>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: 11 }}>
              {JSON.stringify(t.payload, null, 2)}
            </pre>
          </details>

          {t.status !== "borrador" && t.status !== "listo_para_portal" && (
            <div style={{ marginTop: 8 }}>
              <p style={{ fontSize: 12, marginBottom: 4 }}>
                captura de la página real en este momento (sirve aunque
                corra oculto — se pierde si la sesión ya cerró):
              </p>
              <img
                key={`${t.status}-${t.steps.length}`}
                src={ticketScreenshotUrl(ticketId, `${t.status}-${t.steps.length}-${t.updated_at ?? ""}`)}
                alt="captura del portal"
                style={{ maxWidth: "100%", border: "1px solid #ccc" }}
                onError={(e) => {
                  (e.currentTarget as HTMLImageElement).style.display = "none";
                }}
              />
            </div>
          )}

          {t.status === "listo_para_portal" && (
            <div style={{ marginTop: 8 }}>
              <input
                placeholder="https://portal-real-de-facturacion.com"
                value={portalUrl}
                onChange={(e) => setPortalUrl(e.target.value)}
                style={{ width: 380 }}
              />{" "}
              <button onClick={handleStart}>Iniciar Browser Agent</button>
              <p style={{ fontSize: 11, color: "#666" }}>
                {extraction?.portal_facturacion
                  ? "Precargada del ticket — verifica que sea la correcta antes de iniciar."
                  : "Nunca portales mock: pega la URL real de facturación del comercio del ticket."}
              </p>
              <label style={{ fontSize: 12 }}>
                <input
                  type="checkbox"
                  checked={showBrowser}
                  onChange={(e) => setShowBrowser(e.target.checked)}
                />{" "}
                mostrar el navegador (ventana real, para resolver un CAPTCHA
                a mano si aparece — solo funciona corriendo local, no en Docker)
              </label>
            </div>
          )}

          {t.steps.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <h4>bitácora</h4>
              <ol style={{ fontSize: 12 }}>
                {t.steps.map((s) => (
                  <li key={s.index}>
                    {s.action.action}
                    {s.action.ref !== null ? `[${s.action.ref}]` : ""}
                    {s.action.value ? ` = ${s.action.value}` : ""}
                    {s.confirmado_por_humano ? " (confirmado por humano)" : ""}
                    {" — "}
                    {s.result}
                  </li>
                ))}
              </ol>
            </div>
          )}

          {t.status === "navegando" && <p>🤖 el agente está navegando el portal…</p>}

          {t.status === "esperando_confirmacion" && t.pending_action && (
            <div style={{ marginTop: 8, background: "#fff7ed", padding: 8 }}>
              <p>
                El agente quiere hacer clic en un elemento que parece{" "}
                <b>irreversible</b>:
              </p>
              <table border={1} cellPadding={4} style={{ fontSize: 12, borderCollapse: "collapse" }}>
                <tbody>
                  <tr><td>texto del botón/enlace real</td>
                    <td><b>{t.pending_action.target?.label || "(sin texto)"}</b></td></tr>
                  <tr><td>tipo</td><td>{t.pending_action.target?.type || t.pending_action.target?.tag || "—"}</td></tr>
                  <tr><td>razón del agente</td><td>{t.pending_action.reason}</td></tr>
                </tbody>
              </table>
              <p style={{ fontSize: 11, color: "#666" }}>
                Revisa el texto del botón — si de verdad dice "enviar",
                "generar factura", "timbrar" o similar, es el paso final.
                Si solo parece navegar a otra pantalla, es seguro aprobar.
              </p>
              <button onClick={() => handleConfirm(true)}>Aprobar</button>{" "}
              <button onClick={() => handleConfirm(false)}>Rechazar y cancelar</button>
            </div>
          )}

          {t.status === "bloqueada_datos_faltantes" && t.pending_action && (
            <div style={{ marginTop: 8, background: "#fef2f2", padding: 8 }}>
              <p>{BLOCKED[t.status]}</p>
              <p>
                Dato faltante: <b>{t.pending_action.missing_field ?? "(no especificado)"}</b>
                {t.pending_action.reason && ` — ${t.pending_action.reason}`}
              </p>
              <input
                placeholder={`valor para ${t.pending_action.missing_field ?? "el dato faltante"}`}
                value={missingValue}
                onChange={(e) => setMissingValue(e.target.value)}
                style={{ width: 300 }}
              />{" "}
              <button onClick={handleProvideInput} disabled={!missingValue.trim()}>
                Enviar dato y continuar
              </button>{" "}
              <button onClick={handleCancel}>cerrar sesión</button>
              <p style={{ fontSize: 11, color: "#666" }}>
                El dato se guarda en el payload de este ticket como si
                viniera del propio ticket — el agente sigue navegando desde
                donde se quedó.
              </p>
            </div>
          )}

          {t.status in BLOCKED && t.status !== "bloqueada_datos_faltantes" && (
            <div style={{ marginTop: 8, background: "#fef2f2", padding: 8 }}>
              <p>{BLOCKED[t.status]}</p>
              {t.status === "bloqueada_captcha" && (
                <p style={{ fontSize: 12 }}>
                  Si iniciaste con "mostrar el navegador" activado, resuelve
                  el CAPTCHA a mano en esa ventana y luego dale continuar.
                  Si iniciaste en modo oculto, ciérrala y vuelve a empezar
                  con esa casilla marcada.
                </p>
              )}
              {t.status === "fallida" && t.pending_action?.error && (
                <pre style={{ whiteSpace: "pre-wrap", fontSize: 11, background: "#fff", padding: 6 }}>
                  {t.pending_action.error}
                </pre>
              )}
              {RESUMABLE.has(t.status) && (
                <button onClick={() => handleResume(t.status === "bloqueada_limite_pasos" ? 10 : 0)}>
                  {t.status === "bloqueada_captcha" && "Ya lo resolví, continuar"}
                  {t.status === "bloqueada_limite_pasos" && "Seguir 10 pasos más"}
                  {t.status === "fallida" && "Reintentar"}
                </button>
              )}{" "}
              <button onClick={handleCancel}>cerrar sesión</button>
            </div>
          )}

          {t.status === "resuelta" && t.cfdi_uuid && (
            <div style={{ marginTop: 8, background: "#f0fdf4", padding: 8 }}>
              <p>
                ✓ conciliado de verdad: el agente descargó el XML del
                portal y quedó registrado en la base de datos.
              </p>
              <p>CFDI: <b>{t.cfdi_uuid}</b></p>
            </div>
          )}

          {t.status === "resuelta" && !t.cfdi_uuid && (
            <div style={{ marginTop: 8, background: "#f0fdf4", padding: 8 }}>
              <p>
                ✓ el agente terminó, pero no descargó ningún XML (el
                portal solo dio PDF, o solo confirmó en pantalla). Si de
                todos modos tienes el XML del CFDI, pégalo aquí para
                conciliar de verdad:
              </p>
              <textarea
                value={cfdiXml}
                onChange={(e) => setCfdiXml(e.target.value)}
                placeholder="<cfdi:Comprobante ...>...</cfdi:Comprobante>"
                style={{ width: "100%", height: 100, fontSize: 11 }}
              />
              <br />
              <button onClick={handleReconcile}>Reconciliar</button>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
