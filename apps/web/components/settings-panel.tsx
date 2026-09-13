"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Settings, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { fetchProfile, fetchSugerencia, saveProfile } from "@/lib/api";
import type { CompanyProfile } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Ajustes sin salir del dashboard: engrane en el header que abre un panel
 * anclado. Arranca con la sugerencia detectada de los propios movimientos
 * (GET /api/company/profile/sugerencia) en vez de un formulario vacío.
 * El Consultor usa este perfil como contexto.
 */

const VACIO: CompanyProfile = {
  giro: "",
  ciudad: "",
  estado: "",
  cp: "",
  tamanio: "",
  empleados: null,
  modelo: "mixto",
  notas: "",
};

export function SettingsPanel() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  const perfil = useQuery({ queryKey: ["profile"], queryFn: fetchProfile, retry: 1 });
  const [form, setForm] = useState<CompanyProfile>(VACIO);
  const [cargado, setCargado] = useState(false);
  const [detalleSug, setDetalleSug] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const configurado = perfil.data?.configurado ?? true;

  useEffect(() => {
    if (perfil.data?.perfil && !cargado) {
      setForm({ ...VACIO, ...perfil.data.perfil });
      setCargado(true);
    }
  }, [perfil.data, cargado]);

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

  const set = (k: keyof CompanyProfile, v: string | number | null) =>
    setForm((f) => ({ ...f, [k]: v }));

  async function detectar() {
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      const s = await fetchSugerencia();
      setForm((f) => ({
        ...f,
        giro: s.giro || f.giro,
        ciudad: s.ciudad || f.ciudad,
        estado: s.estado || f.estado,
        cp: s.cp || f.cp,
        tamanio: s.tamanio || f.tamanio,
        modelo: s.modelo || f.modelo,
      }));
      setDetalleSug(`${s.giro_origen}; ${s.tamanio_origen}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo detectar");
    } finally {
      setBusy(false);
    }
  }

  async function guardar() {
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      await saveProfile({
        ...form,
        empleados: form.empleados === null ? null : Number(form.empleados),
      });
      await qc.invalidateQueries({ queryKey: ["profile"] });
      setDetalleSug(null);
      setMsg("Listo. El Consultor ya usa este contexto.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar");
    } finally {
      setBusy(false);
    }
  }

  const campo = "space-y-1";
  const etiqueta = "text-[11px] font-semibold text-muted-foreground";
  const select =
    "h-8 w-full rounded-md border border-input bg-background px-2 text-xs outline-none focus-visible:ring-1 focus-visible:ring-ring";

  return (
    <div ref={box} className="relative">
      <Button
        variant="ghost"
        size="icon"
        onClick={() => setOpen((o) => !o)}
        aria-label="Ajustes del negocio"
        aria-expanded={open}
        className="relative"
      >
        <Settings className="size-4" />
        {!configurado ? (
          <span className="absolute right-1.5 top-1.5 size-2 rounded-full bg-primary ring-2 ring-background" />
        ) : null}
      </Button>

      <div
        aria-hidden={!open}
        className={cn(
          "absolute right-0 top-full z-50 mt-2 w-[min(22rem,calc(100vw-2rem))]",
          "max-h-[min(32rem,calc(100vh-6rem))] overflow-y-auto rounded-2xl border border-border",
          "bg-card p-4 shadow-2xl transition-all duration-150",
          open
            ? "pointer-events-auto translate-y-0 opacity-100"
            : "pointer-events-none invisible -translate-y-1 opacity-0",
        )}
      >
        <h3 className="text-sm font-bold tracking-tight">Tu negocio</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Con esto el Consultor habla de tu giro, no en general.
        </p>

        {!configurado || detalleSug ? (
          <div className="mt-3 rounded-xl border border-primary/20 bg-primary/[0.05] p-3">
            <p className="flex items-center gap-1.5 text-xs font-semibold text-primary">
              <Sparkles className="size-3.5" /> Detectado de tus movimientos
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {detalleSug ?? "Podemos deducir tu giro y tamaño de tus propios datos."}
            </p>
            <Button
              size="sm"
              variant="outline"
              className="mt-2 h-7 text-xs"
              disabled={busy}
              onClick={detectar}
            >
              {busy ? <Loader2 className="size-3.5 animate-spin" /> : null}
              {detalleSug ? "Volver a detectar" : "Detectar"}
            </Button>
          </div>
        ) : null}

        <div className="mt-3 grid grid-cols-2 gap-2.5">
          <div className={cn(campo, "col-span-2")}>
            <label className={etiqueta} htmlFor="ap-giro">Giro</label>
            <Input id="ap-giro" className="h-8 text-xs" value={form.giro}
              onChange={(e) => set("giro", e.target.value)} />
          </div>
          <div className={campo}>
            <label className={etiqueta} htmlFor="ap-ciudad">Ciudad</label>
            <Input id="ap-ciudad" className="h-8 text-xs" value={form.ciudad}
              onChange={(e) => set("ciudad", e.target.value)} />
          </div>
          <div className={campo}>
            <label className={etiqueta} htmlFor="ap-estado">Estado</label>
            <Input id="ap-estado" className="h-8 text-xs" value={form.estado}
              onChange={(e) => set("estado", e.target.value)} />
          </div>
          <div className={campo}>
            <label className={etiqueta} htmlFor="ap-tam">Tamaño</label>
            <select id="ap-tam" className={select} value={form.tamanio}
              onChange={(e) => set("tamanio", e.target.value)}>
              <option value="">—</option>
              <option value="micro">micro</option>
              <option value="pequeña">pequeña</option>
              <option value="mediana">mediana</option>
            </select>
          </div>
          <div className={campo}>
            <label className={etiqueta} htmlFor="ap-emp">Empleados</label>
            <Input id="ap-emp" type="number" className="h-8 text-xs"
              value={form.empleados ?? ""}
              onChange={(e) =>
                set("empleados", e.target.value === "" ? null : Number(e.target.value))
              } />
          </div>
          <div className={campo}>
            <label className={etiqueta} htmlFor="ap-modelo">Modelo</label>
            <select id="ap-modelo" className={select} value={form.modelo}
              onChange={(e) => set("modelo", e.target.value)}>
              <option value="b2b">B2B</option>
              <option value="b2c">B2C</option>
              <option value="mixto">mixto</option>
            </select>
          </div>
          <div className={campo}>
            <label className={etiqueta} htmlFor="ap-cp">CP</label>
            <Input id="ap-cp" className="h-8 text-xs" value={form.cp}
              onChange={(e) => set("cp", e.target.value)} />
          </div>
          <div className={cn(campo, "col-span-2")}>
            <label className={etiqueta} htmlFor="ap-notas">Notas</label>
            <textarea id="ap-notas" rows={2} value={form.notas}
              onChange={(e) => set("notas", e.target.value)}
              className="w-full rounded-md border border-input bg-background p-2 text-xs outline-none focus-visible:ring-1 focus-visible:ring-ring" />
          </div>
        </div>

        {error ? <p role="alert" className="mt-2 text-xs text-destructive">{error}</p> : null}
        {msg ? <p className="mt-2 text-xs text-muted-foreground">{msg}</p> : null}

        <Button className="mt-3 w-full rounded-full" size="sm" disabled={busy} onClick={guardar}>
          {busy ? <Loader2 className="size-4 animate-spin" /> : null} Guardar
        </Button>
      </div>
    </div>
  );
}
