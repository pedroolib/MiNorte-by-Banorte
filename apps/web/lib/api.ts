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
  MatchItem,
  SavedScenario,
  ProfileSugerencia,
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

export async function fetchGenDashboard(): Promise<GenDashboard> {
  try {
    return await get<GenDashboard>("/api/dashboard/gen");
  } catch {
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
          label: "Efectivo disponible",
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
            { label: "Efectivo", value: Number(dashboard.summary.efectivo) },
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
        }),
        card("receivables", "timeline_list", {
          items: dashboard.receivables.items.slice(0, 6),
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
