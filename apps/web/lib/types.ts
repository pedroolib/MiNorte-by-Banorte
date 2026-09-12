/** Espejo TS del contrato Pydantic FinancialSummary (T0). */

export interface FinancialSummary {
  company_id: string;
  ventas: number;
  gastos: number;
  utilidad: number;
  efectivo: number;
  impuesto_estimado: number;
  cuentas_por_cobrar: number;
  gastos_sin_cfdi_count: number;
  gastos_sin_cfdi_total: number;
  updated_at: string | null;
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
