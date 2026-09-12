import type {
  Alert,
  CfdiItem,
  ContactItem,
  DashboardData,
  DraftItem,
  FinancialSummary,
  MatchItem,
  ReceivableItem,
  SendItem,
  SignalSet,
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

export const fetchDashboard = () => get<DashboardData>("/api/dashboard");

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

export const fetchSignals = (month?: string) =>
  get<{ month: string; signals: SignalSet }>(
    `/api/signals${month ? `?month=${month}` : ""}`,
  );

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    const detail = await r.json().catch(() => null);
    throw new Error(
      `API ${path}: ${r.status} ${JSON.stringify(detail?.detail ?? detail)}`,
    );
  }
  return r.json() as Promise<T>;
}

export const fetchDrafts = () =>
  get<{ items: DraftItem[] }>("/api/collections/draft");

export const fetchContacts = () =>
  get<{
    contacts: ContactItem[];
    cobertura: { receivable_id: string; customer_rfc: string; tiene_email: boolean }[];
  }>("/api/collections/contacts");

export const saveContact = (customer_rfc: string, email: string) =>
  post<ContactItem>("/api/collections/contacts", { customer_rfc, email });

export const sendReminders = (receivable_ids: string[], confirm: boolean, force = false) =>
  post<{ provider: string; resumen: Record<string, number>; items: SendItem[] }>(
    "/api/collections/send",
    { receivable_ids, confirm, force },
  );
