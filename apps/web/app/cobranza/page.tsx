"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchContacts,
  fetchDrafts,
  saveContact,
  sendReminders,
} from "@/lib/api";
import type { SendItem } from "@/lib/types";

/**
 * /cobranza — cobranza cruda, SIN diseño.
 * Borradores -> alta de correos faltantes -> envío parcial con guardas.
 * Backend: app/operator/collections.py + POST /api/collections/*.
 */

export default function Cobranza() {
  const qc = useQueryClient();
  const drafts = useQuery({ queryKey: ["drafts"], queryFn: fetchDrafts });
  const contacts = useQuery({ queryKey: ["contacts"], queryFn: fetchContacts });
  const [sel, setSel] = useState<Record<string, boolean>>({});
  const [emails, setEmails] = useState<Record<string, string>>({});
  const [confirm, setConfirm] = useState(false);
  const [force, setForce] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [results, setResults] = useState<SendItem[] | null>(null);
  const [provider, setProvider] = useState<string | null>(null);

  const rfcDe = (rid: string) =>
    contacts.data?.cobertura.find((c) => c.receivable_id === rid)
      ?.customer_rfc ?? "";

  async function guardar(rid: string) {
    const email = (emails[rid] ?? "").trim();
    if (!email) {
      setMsg("escribe un correo primero");
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      await saveContact(rfcDe(rid), email);
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["drafts"] }),
        qc.invalidateQueries({ queryKey: ["contacts"] }),
      ]);
      setMsg(`guardado ${email} (ya puedes enviarle)`);
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function enviar() {
    const ids = (drafts.data?.items ?? [])
      .map((d) => d.receivable_id)
      .filter((id) => sel[id]);
    if (ids.length === 0) {
      setMsg("selecciona al menos 1 factura (checkbox)");
      return;
    }
    if (!confirm) {
      setMsg("marca 'confirmo el envío' (guarda anti-doble-clic)");
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const r = await sendReminders(ids, true, force);
      setResults(r.items);
      setProvider(r.provider);
      setMsg(`resumen: ${JSON.stringify(r.resumen)} (provider=${r.provider})`);
      await qc.invalidateQueries({ queryKey: ["drafts"] });
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  const items = drafts.data?.items ?? [];

  return (
    <main style={{ maxWidth: 1000, margin: "0 auto", padding: 16, fontFamily: "monospace" }}>
      <h1>Cobranza — crudo (sin diseño)</h1>
      <p>
        <a href="/">← inicio</a> · <a href="/debug">debug</a>
      </p>
      {(drafts.isLoading || contacts.isLoading) && <p>cargando…</p>}
      {(drafts.error || contacts.error) && (
        <p style={{ color: "red" }}>
          error API (¿corre en :8000? ¿migración 004 aplicada?):{" "}
          {String(drafts.error ?? contacts.error)}
        </p>
      )}
      {msg && <p style={{ background: "#eee", padding: 8 }}>{msg}</p>}

      <table border={1} cellPadding={6} style={{ fontSize: 12, borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr>
            <th>enviar</th>
            <th>factura</th>
            <th>contacto</th>
            <th>asunto</th>
          </tr>
        </thead>
        <tbody>
          {items.map((d) => (
            <tr key={d.receivable_id}>
              <td>
                <input
                  type="checkbox"
                  checked={!!sel[d.receivable_id]}
                  onChange={(e) =>
                    setSel((s) => ({ ...s, [d.receivable_id]: e.target.checked }))
                  }
                />
              </td>
              <td>
                <b>{d.receivable_id}</b>
                <pre style={{ whiteSpace: "pre-wrap" }}>{d.subject}</pre>
              </td>
              <td>
                {d.contact_status === "listo" ? (
                  <span>{d.to}</span>
                ) : (
                  <span>
                    <span style={{ color: "red" }}>falta_email</span>
                    <br />
                    <input
                      placeholder="correo@cliente.com"
                      value={emails[d.receivable_id] ?? ""}
                      onChange={(e) =>
                        setEmails((m) => ({ ...m, [d.receivable_id]: e.target.value }))
                      }
                      style={{ width: 200 }}
                    />{" "}
                    <button disabled={busy} onClick={() => guardar(d.receivable_id)}>
                      Guardar
                    </button>
                  </span>
                )}
              </td>
              <td>
                <details>
                  <summary>ver texto</summary>
                  <pre style={{ whiteSpace: "pre-wrap" }}>{d.body}</pre>
                </details>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={{ marginTop: 12 }}>
        <label>
          <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />{" "}
          confirmo el envío
        </label>{" "}
        <label>
          <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />{" "}
          force (reenviar aunque ya salió en 24h)
        </label>{" "}
        <button disabled={busy} onClick={enviar}>
          Enviar seleccionados
        </button>
      </div>

      {provider && <p>provider usado: <b>{provider}</b> (log = no salió nada real)</p>}
      {results && (
        <table border={1} cellPadding={6} style={{ fontSize: 12, borderCollapse: "collapse", width: "100%", marginTop: 12 }}>
          <thead>
            <tr>
              <th>factura</th>
              <th>para</th>
              <th>estado</th>
              <th>detalle</th>
            </tr>
          </thead>
          <tbody>
            {results.map((r) => (
              <tr key={r.receivable_id}>
                <td>{r.receivable_id}</td>
                <td>{r.to ?? "—"}</td>
                <td>{r.status}</td>
                <td>{r.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
