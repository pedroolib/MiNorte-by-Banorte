"use client";

import { useState } from "react";
import { SendHorizonal } from "lucide-react";

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
    <div className="flex gap-2">
      <Input
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") enviar();
        }}
        placeholder={placeholder}
        disabled={busy}
        aria-label="Preguntar al equipo financiero"
      />
      <Button onClick={enviar} disabled={busy || !texto.trim()} aria-label="Enviar pregunta">
        <SendHorizonal className="size-4" />
      </Button>
    </div>
  );
}
