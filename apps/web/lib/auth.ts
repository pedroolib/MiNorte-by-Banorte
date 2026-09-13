/**
 * Sesión demo 100% local (sin backend real, sin credenciales de verdad):
 * "te registras" una vez y el navegador recuerda que ya lo hiciste. Sirve
 * para mostrar el flujo de onboarding + vinculación bancaria del spec sin
 * necesitar un proveedor de auth real todavía.
 */

const KEY = "minorte_account_v1";

export interface DummyAccount {
  nombre: string;
  correo: string;
  banco: "Banorte";
  clabeEnmascarada: string;
  vinculadoEn: string;
}

export function getAccount(): DummyAccount | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    return JSON.parse(raw) as DummyAccount;
  } catch {
    return null;
  }
}

export function isRegistered(): boolean {
  return getAccount() !== null;
}

export function saveAccount(account: DummyAccount) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, JSON.stringify(account));
}

export function clearAccount() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(KEY);
}

export function maskClabe(clabe: string): string {
  const digits = clabe.replace(/\D/g, "");
  const tail = digits.slice(-4).padStart(4, "0");
  return `•••• •••• •••• ${tail}`;
}

export function initialsFor(nombre: string): string {
  const partes = nombre.trim().split(/\s+/).filter(Boolean);
  if (partes.length === 0) return "MN";
  const first = partes[0][0] ?? "";
  const last = partes.length > 1 ? partes[partes.length - 1][0] ?? "" : "";
  return (first + last).toUpperCase() || "MN";
}
