"use client";

import { useState } from "react";
import { Loader2, SendHorizonal } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** Barra de preguntar: entrada libre al equipo (ask-bar, no chatbot). */
export function AskBar({
  onAsk,
  busy,
  placeholder = "Pregúntale a tu equipo lo que sea…",
}: {
  onAsk: (pregunta: string) => void;
  busy: boolean;
  placeholder?: string;
}) {
  const [texto, setTexto] = useState("");
  const enviar = () => {
    const t = texto.trim();
    if (!t || busy) return;
    setTexto("");
    onAsk(t);
  };
  return (
    <div className="flex gap-2 rounded-2xl border border-border/70 bg-card p-1.5 shadow-[0_12px_35px_-24px_rgba(23,23,23,0.45)]">
      <Input
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") enviar();
        }}
        placeholder={placeholder}
        disabled={busy}
        aria-label="Preguntar al equipo financiero"
        className="h-11 border-0 bg-transparent px-3 shadow-none focus-visible:ring-0"
      />
      <Button
        onClick={enviar}
        disabled={busy || !texto.trim()}
        aria-label={busy ? "Generando respuesta" : "Enviar pregunta"}
        className="size-11 rounded-xl px-0 shadow-[0_8px_20px_-8px_rgba(235,0,41,0.8)]"
      >
        {busy ? (
          <Loader2 className="size-4 animate-spin" aria-label="cargando" />
        ) : (
          <SendHorizonal className="size-4" />
        )}
      </Button>
    </div>
  );
}
