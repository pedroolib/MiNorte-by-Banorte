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
