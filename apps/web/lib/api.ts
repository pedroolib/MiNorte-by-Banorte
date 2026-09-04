import type {
  Alert,
  CfdiItem,
  FinancialSummary,
  MatchItem,
  ReceivableItem,
} from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`API ${path}: ${r.status}`);
  return r.json() as Promise<T>;
}

export const fetchHealth = () =>
  get<{ status: string; company_id: string }>("/health");

export const fetchSummary = () => get<FinancialSummary>("/api/summary");

export const fetchAlerts = (month?: string) =>
  get<{ month: string; items: Alert[] }>(
    `/api/alerts${month ? `?month=${month}` : ""}`,
  );

export const fetchReceivables = () =>
  get<{ total: number; total_pending: string; items: ReceivableItem[] }>(
    "/api/receivables",
  );

export const fetchMatches = (status?: string) =>
  get<{ counts: Record<string, number>; items: MatchItem[] }>(
    `/api/matches?limit=200${status ? `&status=${status}` : ""}`,
  );

export const fetchCfdis = (tipo?: string) =>
  get<{ total: number; items: CfdiItem[] }>(
    `/api/cfdis?limit=5${tipo ? `&tipo=${tipo}` : ""}`,
  );
