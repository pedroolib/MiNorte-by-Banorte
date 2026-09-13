import type {
  Alert,
  CfdiItem,
  ChatResponse,
  CompanyProfile,
  ContactItem,
  CriticalBar,
  DrillResult,
  DashboardData,
  DraftItem,
  FinancialSummary,
  GenDashboard,
  MatchCandidate,
  MatchItem,
  SavedScenario,
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
    cobertura: { receivable_id: string; customer_rfc: string; customer_name: string; tiene_email: boolean }[];
  }>("/api/collections/contacts");

export const saveContact = (customer_rfc: string, email: string, customer_name = "") =>
  post<ContactItem>("/api/collections/contacts", { customer_rfc, email, customer_name });

async function del<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`API ${path}: ${r.status}`);
  return r.json() as Promise<T>;
}

export const deleteContact = (customer_rfc: string, customer_name = "") =>
  del<ContactItem>("/api/collections/contacts", { customer_rfc, customer_name });

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

export async function fetchGenDashboard(): Promise<GenDashboard> {
  try {
    return await get<GenDashboard>("/api/dashboard/gen");
  } catch (e) {
    const dashboard = await fetchDashboard();
    const current = dashboard.monthly.at(-1);
    const previous = dashboard.monthly.at(-2);
    const trend = (now: number, before: number) => ({
      direction: now > before ? "up" as const : now < before ? "down" as const : "flat" as const,
      percentage: before === 0 ? 0 : Math.round(Math.abs(((now - before) / before) * 100)),
    });
    const money = (value: number | string) =>
      new Intl.NumberFormat("es-MX", {
        style: "currency",
        currency: "MXN",
        maximumFractionDigits: 0,
      }).format(Number(value));
    const card = (
      suffix: string,
      component: string,
      props: Record<string, unknown>,
    ) => ({
      insight_id: `${dashboard.month}_${suffix}`,
      component,
      props,
      rationale: "Vista de respaldo construida con datos verificados del motor financiero.",
    });

    return {
      month: dashboard.month,
      week_id: "Resumen mensual",
      degraded: true,
      gen_failed: e instanceof Error ? e.message : "gen no disponible",
      summary: `Tu negocio registró ${money(Number(dashboard.signals.ventas))} en ventas. Hay ${money(dashboard.summary.cuentas_por_cobrar)} pendientes de cobro y ${money(dashboard.summary.efectivo)} disponibles en caja.`,
      anchors: [
        {
          metric: "revenue",
          label: "Ventas",
          value: Number(dashboard.signals.ventas),
          trend: current && previous ? trend(Number(current.sales), Number(previous.sales)) : null,
          analyst_comment: "Ingresos registrados durante el periodo actual.",
        },
        {
          metric: "expenses",
          label: "Gastos",
          value: Number(dashboard.signals.gastos),
          trend: current && previous ? trend(Number(current.expenses), Number(previous.expenses)) : null,
          analyst_comment: "Egresos operativos identificados por el motor financiero.",
        },
        {
          metric: "profit",
          label: "Utilidad",
          value: Number(dashboard.signals.utilidad),
          trend: current && previous ? trend(Number(current.profit), Number(previous.profit)) : null,
          analyst_comment: `Margen del periodo: ${(Number(dashboard.signals.margen) * 100).toFixed(1)}%.`,
        },
        {
          metric: "cash",
          label: "Balance disponible",
          value: Number(dashboard.summary.efectivo),
          trend: null,
          analyst_comment: `${dashboard.signals.runway_dias} días estimados de caja al ritmo actual.`,
        },
      ],
      actions: dashboard.alerts.map((alert, index) =>
        card(
          `alert_${index}`,
          alert.payload.component ?? "action_card",
          alert.payload.component
            ? (alert.payload.props ?? {})
            : {
                eyebrow: "REQUIERE ATENCIÓN",
                title: alert.titulo,
                body: alert.detalle,
                value: alert.total ? money(alert.total) : "",
                action_label: "Revisar",
                tone: alert.severity === "critical" ? "urgent" : "watch",
              },
        ),
      ),
      discovery: [
        card("cash_flow", "time_series", {
          title: "Flujo de dinero",
          points: dashboard.daily.slice(-8).map((point) => ({
            label: new Intl.DateTimeFormat("es-MX", { day: "numeric", month: "short" }).format(new Date(point.date)),
            income: Number(point.income),
            expenses: Number(point.expenses),
          })),
          series: "both",
          period_label: "Últimos movimientos",
          footnote: "Ingresos y gastos registrados por día.",
        }),
        card("liquidity", "donut_total", {
          title: "Liquidez disponible",
          center_value: money(Number(dashboard.summary.efectivo) + Number(dashboard.summary.cuentas_por_cobrar)),
          center_label: "Caja + por cobrar",
          segments: [
            { label: "Balance", value: Number(dashboard.summary.efectivo) },
            { label: "Por cobrar", value: Number(dashboard.summary.cuentas_por_cobrar) },
          ],
          footnote: "Composición de los recursos que pueden convertirse en liquidez.",
        }),
        card("transactions", "transactions_list", {
          items: dashboard.recent_transactions.slice(0, 6).map((item) => ({
            id: item.id,
            merchant: item.merchant,
            category: item.category,
            date: item.date,
            amount: item.amount,
            type: item.type,
          })),
          footnote: "Tus movimientos más recientes, del más nuevo al más viejo.",
        }),
        card("receivables", "timeline_list", {
          items: dashboard.receivables.items.slice(0, 6),
          footnote: "Facturas que tus clientes todavía no te pagan.",
        }),
      ],
    };
  }
}

export const fetchCriticalBar = () =>
  get<CriticalBar>("/api/critical-bar");

export const fetchDrill = (insight_id: string) =>
  get<DrillResult>(
    `/api/drill?insight_id=${encodeURIComponent(insight_id)}`,
  );

export const fetchScenarios = () =>
  get<{ items: SavedScenario[] }>("/api/scenarios");

export const saveScenario = (body: {
  conversation_id?: string | null;
  titulo: string;
  detalle: string;
  cifras?: Record<string, unknown>;
}) => post<SavedScenario>("/api/scenarios", body);

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
