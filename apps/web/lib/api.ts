import type {
  Alert,
  CfdiItem,
  ChatResponse,
  CompanyProfile,
  ContactItem,
  DashboardData,
  DraftItem,
  FinancialSummary,
  MatchCandidate,
  MatchItem,
  ProfileSugerencia,
  ReceiptExtraction,
  ReceivableItem,
  SendItem,
  SignalSet,
  TicketDocument,
  TicketItem,
} from "./types";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  return request<T>(path, "POST", body);
}

async function put<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, "PUT", body);
}

async function request<T>(path: string, method: string, body: unknown): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method,
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

export const sendChat = (mensaje: string, conversation_id: string | null) =>
  post<ChatResponse>("/api/chat", { mensaje, conversation_id });

export const fetchProfile = () =>
  get<{ configurado: boolean; perfil: CompanyProfile | null }>(
    "/api/company/profile",
  );

export const saveProfile = (perfil: Partial<CompanyProfile>) =>
  put<CompanyProfile>("/api/company/profile", perfil);

export const fetchSugerencia = () =>
  get<ProfileSugerencia>("/api/company/profile/sugerencia");

// ---------- Tickets (spec #3.3 caso 1, TIER 2) ----------

export const uploadTicketPhoto = async (file: Blob, filename = "ticket.jpg") => {
  const form = new FormData();
  form.append("file", file, filename);
  const r = await fetch(`${API}/api/tickets/upload`, { method: "POST", body: form });
  if (!r.ok) {
    const detail = await r.json().catch(() => null);
    throw new Error(`API /api/tickets/upload: ${r.status} ${JSON.stringify(detail?.detail ?? detail)}`);
  }
  return r.json() as Promise<{
    document: TicketDocument;
    extraction: ReceiptExtraction;
    candidates: MatchCandidate[];
  }>;
};

export const createTicket = (
  document_id: string,
  transaction_id: string | null,
  receptor_generico = false,
) => post<TicketItem>("/api/tickets", { document_id, transaction_id, receptor_generico });

export const fetchTickets = () => get<{ items: TicketItem[] }>("/api/tickets");

export const fetchTicket = (id: string) => get<TicketItem>(`/api/tickets/${id}`);

export const startTicket = (id: string, portal_url: string, headless = true) =>
  post<TicketItem>(`/api/tickets/${id}/start`, { portal_url, headless });

export const confirmTicket = (id: string, approve: boolean) =>
  post<TicketItem>(`/api/tickets/${id}/confirm`, { approve });

export const provideTicketInput = (id: string, field: string, value: string) =>
  post<TicketItem>(`/api/tickets/${id}/provide_input`, { field, value });

export const resumeTicket = (id: string, extra_steps = 0) =>
  post<TicketItem>(`/api/tickets/${id}/resume`, { extra_steps });

/** URL de la captura actual (funciona corriendo headless). `cacheBust`
 * evita que el navegador reuse una imagen vieja para la misma URL. */
export const ticketScreenshotUrl = (id: string, cacheBust: string | number) =>
  `${API}/api/tickets/${id}/screenshot?t=${cacheBust}`;

export const cancelTicket = (id: string) =>
  post<TicketItem>(`/api/tickets/${id}/cancel`, {});

export const reconcileTicket = (id: string, cfdi_xml?: string) =>
  post<{ result: Record<string, unknown>; ticket: TicketItem }>(
    `/api/tickets/${id}/reconcile`, { cfdi_xml });
