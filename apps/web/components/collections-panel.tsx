"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, Mail, TriangleAlert, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  fetchContacts,
  fetchDrafts,
  fetchReceivables,
  deleteContact,
  saveContact,
  sendReminders,
} from "@/lib/api";
import type { SendItem } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Cobranza dentro del dashboard: se abre bajo la tarjeta que la origina
 * y no reemplaza la vista. Misma ruta que `/cobranza`
 * (GET /api/collections/draft + POST contacts/send) con las guardas del
 * backend intactas: confirm explícito, 24h y force solo si hace falta.
 */

const money = new Intl.NumberFormat("es-MX", {
  style: "currency",
  currency: "MXN",
  maximumFractionDigits: 0,
});

function diasTexto(due: string | null): string {
  if (!due) return "sin fecha";
  const hoy = new Date();
  const d = new Date(`${due}T00:00:00`);
  const dias = Math.round((d.getTime() - hoy.getTime()) / 86_400_000);
  if (dias < 0) return `vencida hace ${Math.abs(dias)} d`;
  if (dias === 0) return "vence hoy";
  return `vence en ${dias} d`;
}

export function CollectionsPanel({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const drafts = useQuery({ queryKey: ["drafts"], queryFn: fetchDrafts });
  const contacts = useQuery({ queryKey: ["contacts"], queryFn: fetchContacts });
  const receivables = useQuery({
    queryKey: ["receivables"],
    queryFn: fetchReceivables,
  });

  const [sel, setSel] = useState<Record<string, boolean>>({});
  const [emails, setEmails] = useState<Record<string, string>>({});
  const [armado, setArmado] = useState(false);
  const [force, setForce] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, SendItem> | null>(null);

  const items = drafts.data?.items ?? [];

  const porId = useMemo(() => {
    const m = new Map<string, { nombre: string; monto: string; vence: string | null }>();
    for (const r of receivables.data?.items ?? []) {
      m.set(r.id, {
        nombre: r.customer_name,
        monto: r.amount_pending,
        vence: r.due_date,
      });
    }
    return m;
  }, [receivables.data]);

  const rfcDe = (rid: string) =>
    contacts.data?.cobertura.find((c) => c.receivable_id === rid)?.customer_rfc ?? "";
  const nombreDe = (rid: string) =>
    porId.get(rid)?.nombre ??
    contacts.data?.cobertura.find((c) => c.receivable_id === rid)?.customer_name ?? "";

  async function borrarEmail(rid: string) {
    setBusy(true);
    setError(null);
    try {
      await deleteContact(rfcDe(rid), nombreDe(rid));
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["drafts"] }),
        qc.invalidateQueries({ queryKey: ["contacts"] }),
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo borrar el correo");
    } finally {
      setBusy(false);
    }
  }

  const elegidas = items.filter((d) => sel[d.receivable_id]);
  const hubo24h = Object.values(result ?? {}).some(
    (r) => r.status === "omitida_24h",
  );

  async function guardarEmail(rid: string) {
    const email = (emails[rid] ?? "").trim();
    if (!email) return;
    setBusy(true);
    setError(null);
    try {
      await saveContact(rfcDe(rid), email, nombreDe(rid));
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["drafts"] }),
        qc.invalidateQueries({ queryKey: ["contacts"] }),
      ]);
      setEmails((m) => ({ ...m, [rid]: "" }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar el correo");
    } finally {
      setBusy(false);
    }
  }

  async function enviar() {
    if (!armado) {
      setArmado(true);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await sendReminders(
        elegidas.map((d) => d.receivable_id),
        true,
        force,
      );
      setResult(Object.fromEntries(r.items.map((i) => [i.receivable_id, i])));
      setArmado(false);
      setForce(false);
      await qc.invalidateQueries({ queryKey: ["drafts"] });
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo enviar");
      setArmado(false);
    } finally {
      setBusy(false);
    }
  }

  const cargando = drafts.isLoading || receivables.isLoading;

  return (
    <div className="rounded-2xl border border-primary/20 bg-card/55 p-4 shadow-xl backdrop-blur-lg sm:p-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold tracking-tight">Cobrar estas facturas</h3>
          <p className="text-xs text-muted-foreground">
            Elige a quién le escribes. Nada sale sin tu confirmación.
          </p>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Cerrar cobranza">
          <X className="size-4" />
        </Button>
      </div>

      {cargando ? (
        <p className="py-6 text-center text-sm text-muted-foreground">Cargando facturas…</p>
      ) : items.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          No hay facturas pendientes de cobro.
        </p>
      ) : (
        <ul className="divide-y divide-border/70">
          {items.map((d) => {
            const meta = porId.get(d.receivable_id);
            const res = result?.[d.receivable_id];
            const faltaEmail = d.contact_status === "falta_email";
            return (
              <li key={d.receivable_id} className="flex flex-wrap items-center gap-3 py-3">
                <input
                  type="checkbox"
                  className="size-4 shrink-0 accent-[hsl(var(--primary))]"
                  checked={!!sel[d.receivable_id]}
                  disabled={faltaEmail || !!res}
                  onChange={(e) =>
                    setSel((s) => ({ ...s, [d.receivable_id]: e.target.checked }))
                  }
                  aria-label={`Seleccionar ${meta?.nombre ?? d.receivable_id}`}
                />

                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold">
                    {meta?.nombre ?? d.receivable_id}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {meta ? `${money.format(Number(meta.monto))} · ${diasTexto(meta.vence)}` : d.receivable_id}
                  </p>
                </div>

                {res ? (
                  <Badge variant={res.status === "enviada" ? "success" : "warning"}>
                    {res.status === "enviada" ? "Enviado" : res.detail}
                  </Badge>
                ) : faltaEmail ? (
                  <div className="flex w-full items-center gap-2 sm:w-auto">
                    <Input
                      type="email"
                      placeholder="correo@cliente.com"
                      className="h-8 w-full text-xs sm:w-52"
                      value={emails[d.receivable_id] ?? ""}
                      onChange={(e) =>
                        setEmails((m) => ({ ...m, [d.receivable_id]: e.target.value }))
                      }
                      aria-label={`Correo de ${meta?.nombre ?? d.receivable_id}`}
                    />
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy || !(emails[d.receivable_id] ?? "").trim()}
                      onClick={() => guardarEmail(d.receivable_id)}
                    >
                      Guardar
                    </Button>
                  </div>
                ) : (
                  <span className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span>{d.to}</span>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      onClick={() => borrarEmail(d.receivable_id)}
                      aria-label={`Borrar correo de ${meta?.nombre ?? d.receivable_id}`}
                      title="Borrar correo"
                    >
                      <X className="size-3.5" />
                    </Button>
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {error ? (
        <p role="alert" className="mt-3 flex items-center gap-2 text-xs text-destructive">
          <TriangleAlert className="size-3.5" /> {error}
        </p>
      ) : null}

      {items.length > 0 ? (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button
            onClick={enviar}
            disabled={busy || elegidas.length === 0}
            variant={armado ? "destructive" : "default"}
            className="rounded-full"
          >
            {busy ? (
              <Loader2 className="size-4 animate-spin" />
            ) : armado ? (
              <Check className="size-4" />
            ) : (
              <Mail className="size-4" />
            )}
            {armado
              ? `Confirmar envío a ${elegidas.length}`
              : elegidas.length === 0
                ? "Selecciona facturas"
                : `Enviar ${elegidas.length} recordatorio${elegidas.length > 1 ? "s" : ""}`}
          </Button>

          {armado ? (
            <Button variant="ghost" size="sm" onClick={() => setArmado(false)}>
              Cancelar
            </Button>
          ) : null}

          {hubo24h && !armado ? (
            <button
              type="button"
              onClick={() => {
                setForce(true);
                setResult(null);
                setArmado(true);
              }}
              className={cn(
                "text-xs underline underline-offset-4",
                "text-muted-foreground hover:text-foreground",
              )}
            >
              Ya le escribiste hoy · reenviar de todas formas
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
