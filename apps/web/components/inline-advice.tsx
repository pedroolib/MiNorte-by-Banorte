"use client";

import { useEffect, useState } from "react";
import { Loader2, Sparkles, TriangleAlert, X } from "lucide-react";

import { Markdown } from "@/components/markdown";
import { DynamicUI } from "@/components/registry";
import { Button } from "@/components/ui/button";
import { sendChat } from "@/lib/api";
import type { GenCard } from "@/lib/types";

/**
 * Respuesta del Consultor DENTRO de la tarjeta que la pidió.
 * Misma llamada que el AskBar (POST /api/chat) pero sin cambiar de vista:
 * el dashboard completo sigue detrás.
 */

const LS_KEY = "minorte_conversation_id";

export function InlineAdvice({
  question,
  onClose,
}: {
  question: string;
  onClose: () => void;
}) {
  const [texto, setTexto] = useState<string | null>(null);
  const [tarjetas, setTarjetas] = useState<GenCard[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    (async () => {
      setTexto(null);
      setError(null);
      try {
        const cid = window.localStorage.getItem(LS_KEY);
        let r;
        try {
          r = await sendChat(question, cid);
        } catch (e) {
          // id guardado que ya no existe: arrancamos conversación nueva.
          if (cid && e instanceof Error && e.message.includes("/api/chat: 404")) {
            window.localStorage.removeItem(LS_KEY);
            r = await sendChat(question, null);
          } else {
            throw e;
          }
        }
        if (!vivo) return;
        window.localStorage.setItem(LS_KEY, r.conversation_id);
        setTexto(r.respuesta);
        setTarjetas(r.tarjetas ?? []);
      } catch (e) {
        if (vivo) {
          setError(
            e instanceof Error && e.message.includes("502")
              ? "El Consultor no está disponible (falta OPENAI_API_KEY)."
              : "No pudimos consultarlo ahorita.",
          );
        }
      }
    })();
    return () => {
      vivo = false;
    };
  }, [question]);

  return (
    <div className="rounded-2xl border border-primary/20 bg-card p-4 shadow-sm sm:p-5">
      <div className="mb-2 flex items-start justify-between gap-3">
        <p className="flex items-center gap-1.5 text-sm font-bold tracking-tight">
          <Sparkles className="size-4 text-primary" /> Cómo resolverlo
        </p>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Cerrar">
          <X className="size-4" />
        </Button>
      </div>

      {!texto && !error ? (
        <p className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Revisando tus números…
        </p>
      ) : null}

      {error ? (
        <p role="alert" className="flex items-center gap-2 py-2 text-sm text-destructive">
          <TriangleAlert className="size-4" /> {error}
        </p>
      ) : null}

      {texto ? (
        <div className="text-sm">
          <Markdown text={texto} />
        </div>
      ) : null}

      {tarjetas.length > 0 ? (
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {tarjetas.map((c, i) => (
            <DynamicUI
              key={c.insight_id + i}
              schema={{ component: c.component, props: c.props } as never}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
