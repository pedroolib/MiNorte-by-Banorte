"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, SendHorizonal } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** Barra de preguntar: entrada libre al asesor (ask-bar, no chatbot). */
export function AskBar({
  onAsk,
  busy,
  placeholder = "Pregúntale a tu asesor lo que sea…",
}: {
  onAsk: (pregunta: string) => void;
  busy: boolean;
  placeholder?: string;
}) {
  const [texto, setTexto] = useState("");
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const enviar = () => {
    const t = texto.trim();
    if (!t || busy) return;
    setTexto("");
    onAsk(t);
  };

  // Atajo "/" para enfocar la barra desde cualquier parte de la página,
  // salvo que ya se esté escribiendo en otro campo.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "/") return;
      const activo = document.activeElement;
      const escribiendo =
        activo instanceof HTMLElement &&
        (activo.tagName === "INPUT" ||
          activo.tagName === "TEXTAREA" ||
          activo.isContentEditable);
      if (escribiendo) return;
      e.preventDefault();
      inputRef.current?.focus();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div className="flex gap-2 rounded-2xl border border-border/70 bg-card p-1.5 shadow-[0_12px_35px_-24px_rgba(23,23,23,0.45)]">
      <div className="relative min-w-0 flex-1">
        <Input
          ref={inputRef}
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") enviar();
          }}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder={placeholder}
          disabled={busy}
          aria-label="Preguntar al asesor financiero"
          className="h-11 border-0 bg-transparent px-3 shadow-none focus-visible:ring-0"
        />
        {!focused && !texto ? (
          <kbd
            aria-hidden="true"
            className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 rounded-md border border-border/70 bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground"
          >
            /
          </kbd>
        ) : null}
      </div>
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
