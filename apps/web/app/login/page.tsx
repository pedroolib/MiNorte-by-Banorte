"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Banknote,
  CheckCircle2,
  Fingerprint,
  Loader2,
  Lock,
  ShieldCheck,
} from "lucide-react";

import { BanorteMark } from "@/components/banorte-mark";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { fetchSummary } from "@/lib/api";
import { maskClabe, saveAccount } from "@/lib/auth";
import { cn } from "@/lib/utils";

/**
 * Primer contacto con MiNorte: registro + un dummy de vincular la cuenta
 * Banorte (spec: sesión + onboarding). Todo es local -- no hay proveedor
 * de auth real ni credenciales bancarias de verdad se envían a ningún
 * lado; es la demo de CÓMO se vería el flujo.
 */

type Paso = "registro" | "vincular" | "listo";

const PASOS: Paso[] = ["registro", "vincular", "listo"];

const money = new Intl.NumberFormat("es-MX", {
  style: "currency",
  currency: "MXN",
  maximumFractionDigits: 2,
});

function emailValido(v: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
}

export default function LoginPage() {
  const router = useRouter();
  const [paso, setPaso] = useState<Paso>("registro");

  // Paso 1: registro
  const [nombre, setNombre] = useState("");
  const [correo, setCorreo] = useState("");
  const [password, setPassword] = useState("");
  const [errorRegistro, setErrorRegistro] = useState<string | null>(null);

  // Paso 2: vincular Banorte
  const [usuarioBanorte, setUsuarioBanorte] = useState("");
  const [passwordBanorte, setPasswordBanorte] = useState("");
  const [conectando, setConectando] = useState(false);
  const [errorVincular, setErrorVincular] = useState<string | null>(null);
  const [clabe, setClabe] = useState<string | null>(null);

  const summary = useQuery({
    queryKey: ["summary"],
    queryFn: fetchSummary,
    enabled: paso === "vincular" || paso === "listo",
    retry: 1,
  });

  function handleRegistro() {
    if (!nombre.trim() || !correo.trim() || !password.trim()) {
      setErrorRegistro("Completa tu nombre, correo y contraseña para continuar.");
      return;
    }
    if (!emailValido(correo.trim())) {
      setErrorRegistro("Ese correo no se ve válido — revísalo.");
      return;
    }
    if (password.trim().length < 6) {
      setErrorRegistro("Tu contraseña necesita al menos 6 caracteres.");
      return;
    }
    setErrorRegistro(null);
    setPaso("vincular");
  }

  async function handleVincular() {
    if (!usuarioBanorte.trim() || !passwordBanorte.trim()) {
      setErrorVincular("Necesitamos tu usuario y contraseña de banca en línea Banorte.");
      return;
    }
    setErrorVincular(null);
    setConectando(true);
    // Dummy: aquí iría el OAuth/agregador real (ej. Belvo). Simulamos la
    // latencia de una conexión bancaria real para que la demo se sienta
    // honesta sobre qué está pasando, en vez de "vincular" instantáneo.
    await new Promise((r) => setTimeout(r, 1600));
    setClabe(maskClabe(usuarioBanorte + passwordBanorte + Date.now()));
    setConectando(false);
    setPaso("listo");
  }

  function handleFinalizar() {
    saveAccount({
      nombre: nombre.trim(),
      correo: correo.trim(),
      banco: "Banorte",
      clabeEnmascarada: clabe ?? maskClabe("0000"),
      vinculadoEn: new Date().toISOString(),
    });
    router.replace("/");
  }

  const pasoIndex = PASOS.indexOf(paso);

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-md space-y-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <BanorteMark className="h-10 w-auto" />
          <div className="leading-none">
            <span className="block text-base font-extrabold tracking-tight">MiNorte</span>
            <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              by Banorte
            </span>
          </div>
        </div>

        <div className="space-y-1.5">
          <Progress value={((pasoIndex + 1) / PASOS.length) * 100} />
          <p className="text-center text-xs text-muted-foreground">
            Paso {pasoIndex + 1} de {PASOS.length}
          </p>
        </div>

        <Card className="hover:translate-y-0 hover:shadow-[0_12px_35px_-24px_rgba(23,23,23,0.45)]">
          {paso === "registro" ? (
            <>
              <CardHeader>
                <CardTitle className="text-lg">Crea tu cuenta</CardTitle>
                <CardDescription>
                  Tu centro financiero inteligente empieza aquí. Te toma un minuto.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {errorRegistro ? (
                  <Alert variant="destructive">
                    <AlertDescription>{errorRegistro}</AlertDescription>
                  </Alert>
                ) : null}
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground" htmlFor="nombre">
                    Nombre completo
                  </label>
                  <Input
                    id="nombre"
                    placeholder="Ana Nuñez"
                    value={nombre}
                    onChange={(e) => setNombre(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleRegistro()}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground" htmlFor="correo">
                    Correo
                  </label>
                  <Input
                    id="correo"
                    type="email"
                    placeholder="tu@negocio.com"
                    value={correo}
                    onChange={(e) => setCorreo(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleRegistro()}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground" htmlFor="password">
                    Contraseña
                  </label>
                  <Input
                    id="password"
                    type="password"
                    placeholder="Mínimo 6 caracteres"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleRegistro()}
                  />
                </div>
                <Button onClick={handleRegistro} className="w-full rounded-full">
                  Crear cuenta
                </Button>
                <p className="text-center text-[11px] text-muted-foreground">
                  Al continuar aceptas que esto es una demo — no se guarda ninguna
                  contraseña real en ningún lado.
                </p>
              </CardContent>
            </>
          ) : null}

          {paso === "vincular" ? (
            <>
              <CardHeader>
                <div className="mb-1 flex items-center gap-2">
                  <BanorteMark className="h-6 w-auto" />
                  <span className="text-sm font-bold">Banorte</span>
                  <span className="ml-auto flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
                    <ShieldCheck className="size-3" /> Conexión segura
                  </span>
                </div>
                <CardTitle className="text-lg">Vincula tu cuenta Banorte</CardTitle>
                <CardDescription>
                  Para leer tus movimientos y armar tu resumen financiero
                  automáticamente. Nunca guardamos tu contraseña — se procesa
                  directo con el banco.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {errorVincular ? (
                  <Alert variant="destructive">
                    <AlertDescription>{errorVincular}</AlertDescription>
                  </Alert>
                ) : null}
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground" htmlFor="usuario-banorte">
                    Usuario en línea o número de cliente
                  </label>
                  <div className="relative">
                    <Fingerprint className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      id="usuario-banorte"
                      placeholder="Tu usuario de bancaenlinea.banorte.com"
                      className="pl-9"
                      value={usuarioBanorte}
                      onChange={(e) => setUsuarioBanorte(e.target.value)}
                      disabled={conectando}
                      onKeyDown={(e) => e.key === "Enter" && handleVincular()}
                    />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground" htmlFor="password-banorte">
                    Contraseña
                  </label>
                  <div className="relative">
                    <Lock className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      id="password-banorte"
                      type="password"
                      placeholder="••••••••"
                      className="pl-9"
                      value={passwordBanorte}
                      onChange={(e) => setPasswordBanorte(e.target.value)}
                      disabled={conectando}
                      onKeyDown={(e) => e.key === "Enter" && handleVincular()}
                    />
                  </div>
                </div>
                <Button
                  onClick={handleVincular}
                  disabled={conectando}
                  className="w-full rounded-full"
                >
                  {conectando ? (
                    <>
                      <Loader2 className="size-4 animate-spin" /> Conectando con Banorte…
                    </>
                  ) : (
                    <>
                      <Banknote className="size-4" /> Conectar con Banorte
                    </>
                  )}
                </Button>
                <p className="text-center text-[11px] text-muted-foreground">
                  Demo: estas credenciales no viajan a ningún banco real.
                </p>
              </CardContent>
            </>
          ) : null}

          {paso === "listo" ? (
            <>
              <CardHeader className="items-center text-center">
                <div className="grid size-12 place-items-center rounded-full bg-emerald-100 dark:bg-emerald-950">
                  <CheckCircle2 className="size-6 text-emerald-600 dark:text-emerald-400" />
                </div>
                <CardTitle className="text-lg">¡Tu cuenta quedó vinculada!</CardTitle>
                <CardDescription>
                  Ya podemos leer tus movimientos y mantener tu resumen al día.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2 rounded-xl border border-border/70 bg-muted/30 p-3 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Titular</span>
                    <span className="font-medium">{nombre.trim() || "—"}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Banco</span>
                    <span className="flex items-center gap-1.5 font-medium">
                      <BanorteMark className="h-4 w-auto" /> Banorte
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Cuenta</span>
                    <span className="font-mono font-medium">{clabe ?? "—"}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Saldo detectado</span>
                    <span className="font-medium">
                      {summary.data ? money.format(Number(summary.data.efectivo)) : "—"}
                    </span>
                  </div>
                </div>
                <Button onClick={handleFinalizar} className="w-full rounded-full">
                  Ir a mi dashboard
                </Button>
              </CardContent>
            </>
          ) : null}
        </Card>

        <p
          className={cn(
            "text-center text-xs text-muted-foreground transition-opacity",
            paso === "registro" ? "opacity-100" : "opacity-0",
          )}
        >
          ¿Ya te registraste en este navegador? Refresca la página.
        </p>
      </div>
    </div>
  );
}
