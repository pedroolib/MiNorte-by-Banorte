"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchProfile,
  fetchSugerencia,
  saveProfile,
} from "@/lib/api";
import type { CompanyProfile } from "@/lib/types";

/**
 * /ajustes — perfil del negocio, crudo y SIN diseño.
 * El Consultor usa este contexto (giro, ciudad, tamaño) para analizar
 * enfocado. La sugerencia se detecta de tus datos; tú confirmas o corriges.
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

export default function Ajustes() {
  const qc = useQueryClient();
  const perfil = useQuery({ queryKey: ["profile"], queryFn: fetchProfile });
  const [form, setForm] = useState<CompanyProfile>(VACIO);
  const [cargado, setCargado] = useState(false);
  const [sug, setSug] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (perfil.data?.perfil && !cargado) {
      setForm({ ...VACIO, ...perfil.data.perfil });
      setCargado(true);
    }
  }, [perfil.data, cargado]);

  const set = (k: keyof CompanyProfile, v: string | number | null) =>
    setForm((f) => ({ ...f, [k]: v }));

  async function aplicarSugerencia() {
    setBusy(true);
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
      setSug(true);
      setMsg(
        `sugerencia aplicada (${s.giro_origen}; ${s.tamanio_origen}). Revisa y Guarda.`,
      );
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function guardar() {
    setBusy(true);
    setMsg(null);
    try {
      await saveProfile({
        ...form,
        empleados: form.empleados === null ? null : Number(form.empleados),
      });
      await qc.invalidateQueries({ queryKey: ["profile"] });
      setMsg("guardado. El Consultor ya usa este contexto.");
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={{ maxWidth: 640, margin: "0 auto", padding: 16, fontFamily: "monospace" }}>
      <h1>Ajustes — perfil del negocio (crudo)</h1>
      <p>
        <a href="/">← inicio</a> · <a href="/chat">chat</a>
      </p>
      {perfil.isLoading && <p>cargando…</p>}
      {perfil.error && <p style={{ color: "red" }}>error: {String(perfil.error)}</p>}
      {perfil.data && (
        <p>
          estado: {perfil.data.configurado ? "configurado" : "sin configurar (usa defaults del seed)"}
        </p>
      )}

      <div style={{ border: "1px solid #ccc", padding: 12, marginBottom: 12 }}>
        <h3>Sugerencia detectada de tus datos</h3>
        <button disabled={busy} onClick={aplicarSugerencia}>
          Detectar y aplicar
        </button>
        {sug && <p>revisa los campos y presiona Guardar.</p>}
      </div>

      <div style={{ display: "grid", gap: 8 }}>
        <label>Giro* <input value={form.giro} onChange={(e) => set("giro", e.target.value)} style={{ width: "100%" }} /></label>
        <label>Ciudad* <input value={form.ciudad} onChange={(e) => set("ciudad", e.target.value)} style={{ width: "100%" }} /></label>
        <label>Estado <input value={form.estado} onChange={(e) => set("estado", e.target.value)} style={{ width: "100%" }} /></label>
        <label>CP <input value={form.cp} onChange={(e) => set("cp", e.target.value)} style={{ width: "100%" }} /></label>
        <label>Tamaño
          <select value={form.tamanio} onChange={(e) => set("tamanio", e.target.value)} style={{ width: "100%" }}>
            <option value="">—</option>
            <option value="micro">micro</option>
            <option value="pequeña">pequeña</option>
            <option value="mediana">mediana</option>
          </select>
        </label>
        <label>Empleados
          <input type="number" value={form.empleados ?? ""} onChange={(e) => set("empleados", e.target.value === "" ? null : Number(e.target.value))} style={{ width: "100%" }} />
        </label>
        <label>Modelo
          <select value={form.modelo} onChange={(e) => set("modelo", e.target.value)} style={{ width: "100%" }}>
            <option value="b2b">B2B</option>
            <option value="b2c">B2C</option>
            <option value="mixto">mixto</option>
          </select>
        </label>
        <label>Notas <textarea value={form.notas} onChange={(e) => set("notas", e.target.value)} style={{ width: "100%" }} rows={3} /></label>
        <button disabled={busy} onClick={guardar}>Guardar</button>
      </div>

      {msg && <p style={{ background: "#eee", padding: 8 }}>{msg}</p>}
    </main>
  );
}
