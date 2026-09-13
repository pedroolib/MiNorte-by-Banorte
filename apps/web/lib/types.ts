/** Espejo TS del contrato Pydantic FinancialSummary (T0). */

export interface FinancialSummary {
  company_id: string;
  ventas: number | string;
  gastos: number | string;
  utilidad: number | string;
  efectivo: number | string;
  impuesto_estimado: number | string;
  cuentas_por_cobrar: number | string;
  gastos_sin_cfdi_count: number;
  gastos_sin_cfdi_total: number | string;
  updated_at: string | null;
}

export interface DashboardSeriesPoint {
  month: string;
  sales: string;
  expenses: string;
  profit: string;
  margin: string;
  cash: string;
}

export interface DashboardDailyPoint {
  date: string;
  income: string;
  expenses: string;
  balance: string | null;
  count: number;
}

export interface DashboardGroup {
  name: string;
  amount: string;
  percent: string;
}

export interface DashboardTransaction {
  id: string;
  date: string;
  description: string;
  merchant: string;
  amount: string;
  type: "ingreso" | "egreso";
  category: string;
}

export interface DashboardData {
  month: string;
  updated_at: string;
  summary: FinancialSummary;
  signals: SignalSet;
  alerts: Alert[];
  receivables: {
    total: number;
    total_pending: string;
    items: ReceivableItem[];
  };
  matches: { counts: Record<"auto" | "review" | "unmatched", number> };
  monthly: DashboardSeriesPoint[];
  daily: DashboardDailyPoint[];
  categories: DashboardGroup[];
  customers: DashboardGroup[];
  recent_transactions: DashboardTransaction[];
  activity: { date: string; count: number }[];
  cfdis: { issued: number; received: number };
}

/** Alerta del Analista (T4/T5). Totales llegan como string (Decimal JSON). */
export interface Alert {
  id: string;
  rule: string;
  severity: "info" | "warning" | "critical";
  titulo: string;
  detalle: string;
  total: string | null;
  estado: string;
  payload: { component?: string; props?: Record<string, unknown> };
}

/** Cuenta por cobrar abierta (T4/T5). */
export interface ReceivableItem {
  id: string;
  cfdi_id: string;
  customer_name: string;
  customer_rfc: string;
  amount: string;
  amount_pending: string;
  issued_at: string;
  due_date: string | null;
  status: string;
}

/** Match de conciliación (T4/T5, debug). */
export interface MatchItem {
  transaction_id: string;
  cfdi_id: string | null;
  score: string;
  amount_score: string;
  date_score: string;
  merchant_score: string;
  status: "auto" | "review" | "unmatched";
}

/** CFDI (T3). Muestra mínima para /debug. */
export interface CfdiItem {
  uuid: string;
  tipo: "emitido" | "recibido";
  emisor_nombre: string;
  receptor_nombre: string;
  total: string;
  fecha_emision: string;
  serie: string | null;
  folio: string | null;
}

/** Señales numéricas del motor para el Analista (T4/T5, sin juicio). */
export interface SignalSet {
  [key: string]: string | number | null | Record<string, string>;
}

/** Borrador de cobranza (T9). */
export interface DraftItem {
  receivable_id: string;
  to: string | null;
  contact_status: "listo" | "falta_email";
  subject: string;
  body: string;
}

/** Resultado por factura del envío (T9, parcial por diseño). */
export interface SendItem extends DraftItem {
  status: "enviada" | "bloqueada_falta_email" | "omitida_24h" | "fallida";
  detail: string;
}

/** Contacto del directorio (T9). */
export interface ContactItem {
  customer_rfc: string;
  customer_name: string;
  email: string | null;
  phone: string | null;
}

/** Perfil del negocio (T8). */
export interface CompanyProfile {
  company_id?: string;
  giro: string;
  ciudad: string;
  estado: string;
  cp: string;
  tamanio: string;
  empleados: number | null;
  modelo: string;
  notas: string;
}

/** Sugerencia detectada + origen de cada campo. */
export interface ProfileSugerencia extends CompanyProfile {
  giro_origen: string;
  tamanio_origen: string;
}

/** Chat del Consultor (T8, permanente, no generativo). */
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  tools?: string[];
}

export interface ChatResponse {
  conversation_id: string;
  respuesta: string;
  tools_usados: string[];
  llamadas?: Array<{ tool: string; args: Record<string, unknown> }>;
  tarjetas?: GenCard[];
  truncado: boolean;
}

export interface CriticalBar {
  month: string;
  pendientes: number;
  items: GenCard[];
}

export interface DrillResult {
  insight_id: string;
  month: string;
  texto: string;
  tarjetas: GenCard[];
}

export interface SavedScenario {
  id: string;
  titulo: string;
  detalle: string;
  cifras: Record<string, unknown>;
  created_at: string;
}

/** Dashboard generativo (Composition Engine). JSON listo para DynamicUI. */
export interface GenAnchor {
  metric: string;
  label: string;
  value: number | string | null;
  trend: { direction: "up" | "down" | "flat"; percentage: number } | null;
  analyst_comment: string;
}

export interface GenCard {
  insight_id: string;
  component: string;
  props: Record<string, unknown>;
  rationale: string;
}

export interface GenDashboard {
  month: string;
  week_id: string;
  anchors: GenAnchor[];
  actions: GenCard[];
  discovery: GenCard[];
  summary: string;
}

/** Ticket (spec #3.3 caso 1, TIER 2): foto real -> factura real. */

/** Lo que Vision leyó del ticket. Campo no legible = null (nunca inventado). */
export interface ReceiptExtraction {
  comercio: string | null;
  rfc_comercio: string | null;
  total: string | null;
  fecha: string | null;
  folio: string | null;
  portal_facturacion: string | null;
  confianza: "alta" | "media" | "baja";
  campos_no_legibles: string[];
}

export interface TicketDocument {
  id: string;
  company_id: string;
  mime: string;
  extraction: ReceiptExtraction;
  created_at?: string;
}

/** Candidato de match ticket<->movimiento (misma fórmula que reconcile.py). */
export interface MatchCandidate {
  transaction_id: string;
  score: string;
  amount_score: string;
  date_score: string;
  merchant_score: string;
  merchant_name: string;
  amount: string;
  date: string;
}

export type InvoiceRequestStatus =
  | "borrador"
  | "listo_para_portal"
  | "navegando"
  | "esperando_confirmacion"
  | "bloqueada_captcha"
  | "bloqueada_auth"
  | "bloqueada_datos_faltantes"
  | "bloqueada_limite_pasos"
  | "cancelada"
  | "resuelta"
  | "fallida";

/** Un paso de la bitácora del Browser Agent (para la UI: "sensación de
 * que los agentes están trabajando", spec #5). */
export interface BrowserStep {
  index: number;
  url: string;
  action: {
    action: string;
    ref: string | null;
    value: string | null;
    missing_field: string | null;
    reason: string;
  };
  result?: string;
  confirmado_por_humano?: boolean;
}

/** Elemento real de la página (rol/label/tipo) — nunca coordenadas. */
export interface PageElement {
  ref: string;
  tag: string;
  role: string;
  label: string;
  type: string;
}

/** Lo pendiente de resolver: una decisión normal (action/ref/reason,
 * +target si es irreversible), o solo un error si status=fallida. */
export interface PendingAction {
  action?: string;
  ref?: string | null;
  value?: string | null;
  missing_field?: string | null;
  reason?: string;
  target?: PageElement | null;
  error?: string;
}

export interface TicketItem {
  id: string;
  company_id: string;
  document_id: string;
  transaction_id: string | null;
  payload: Record<string, string | null>;
  status: InvoiceRequestStatus;
  steps: BrowserStep[];
  pending_action?: PendingAction | null;
  cfdi_uuid: string | null;
  created_at?: string;
  updated_at?: string;
}
