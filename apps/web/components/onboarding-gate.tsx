"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { BanorteMark } from "@/components/banorte-mark";
import { isRegistered } from "@/lib/auth";

/**
 * Primera visita -> /login (registro + vincular Banorte, spec de sesión).
 * Ya registrado y entrando a /login -> lo manda derecho al dashboard.
 * Todo es local (localStorage): no hay backend de auth real todavía.
 */
export function OnboardingGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const registrado = isRegistered();
    if (!registrado && pathname !== "/login") {
      router.replace("/login");
      return;
    }
    if (registrado && pathname === "/login") {
      router.replace("/");
      return;
    }
    setReady(true);
  }, [pathname, router]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <BanorteMark className="h-8 w-auto animate-pulse opacity-70" />
      </div>
    );
  }

  return <>{children}</>;
}
