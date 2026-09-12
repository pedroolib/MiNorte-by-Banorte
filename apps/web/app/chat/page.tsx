"use client";

import { useEffect, useRef, useState } from "react";
import { Markdown } from "@/components/markdown";
import { sendChat } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";

/**
 * /chat — Consultor permanente, SIN diseño y NO generativo.
 * Esta página siempre sale igual; la UI generativa (tarjetas que elige
 * la IA) vive en el registry y llega con el dashboard diseñado.
 */

const LS_KEY = "minorte_conversation_id";

const SUGERENCIAS = [
  "¿Puedo contratar a alguien por $20,000 al mes?",
  "¿Cuánto efectivo tengo?",
  "¿Qué gasto me está afectando más?",
  "Quiero un crédito de $100,000, ¿cuál me conviene?",
];

export default function Chat() {
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [cid, setCid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setCid(localStorage.getItem(LS_KEY));
  }, []);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, busy]);

  async function nueva() {
    localStorage.removeItem(LS_KEY);
    setCid(null);
    setMsgs([]);
    setError(null);
  }

  async function enviar(texto: string) {
    const t = texto.trim();
    if (!t || busy) return;
    setBusy(true);
    setError(null);
    setMsgs((m) => [...m, { role: "user", content: t }]);
    setInput("");
    try {
      const r = await sendChat(t, cid);
      setCid(r.conversation_id);
      localStorage.setItem(LS_KEY, r.conversation_id);
      setMsgs((m) => [
        ...m,
        { role: "assistant", content: r.respuesta, tools: r.tools_usados },
      ]);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={{ maxWidth: 700, margin: "0 auto", padding: 16, fontFamily: "monospace" }}>
      <h1>Consultor — crudo (siempre igual)</h1>
      <p>
        <a href="/">← inicio</a> · <a href="/debug">debug</a> ·{" "}
        <a href="/cobranza">cobranza</a> ·{" "}
        <button onClick={nueva}>+ nueva conversación</button>
      </p>

      <div style={{ border: "1px solid #ccc", padding: 12, minHeight: 300, marginBottom: 12 }}>
        {msgs.length === 0 && !busy && (
          <div>
            <p>Pregúntame sobre tu negocio. Ejemplos:</p>
            <ul>
              {SUGERENCIAS.map((s) => (
                <li key={s}>
                  <button onClick={() => enviar(s)} style={{ textAlign: "left" }}>
                    {s}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} style={{ marginBottom: 12, textAlign: m.role === "user" ? "right" : "left" }}>
            <div
              style={{
                display: "inline-block",
                background: m.role === "user" ? "#000" : "#eee",
                color: m.role === "user" ? "#fff" : "#000",
                padding: "8px 12px",
                borderRadius: 8,
                maxWidth: "90%",
                whiteSpace: "pre-wrap",
                textAlign: "left",
              }}
            >
              {m.role === "assistant" ? (
                <Markdown text={m.content} />
              ) : (
                m.content
              )}
            </div>
            {m.tools && m.tools.length > 0 && (
              <div style={{ fontSize: 11, color: "#666", marginTop: 4 }}>
                tools: {m.tools.join(", ")}
              </div>
            )}
          </div>
        ))}
        {busy && <p>el consultor está revisando tus números…</p>}
        <div ref={bottom} />
      </div>

      {error && <p style={{ color: "red" }}>{error}</p>}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          enviar(input);
        }}
        style={{ display: "flex", gap: 8 }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Pregúntame sobre tu negocio…"
          style={{ flex: 1, padding: 8 }}
        />
        <button type="submit" disabled={busy}>
          Enviar
        </button>
      </form>
    </main>
  );
}
