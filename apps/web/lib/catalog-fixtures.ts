import type { UISchema } from "./ui-schema";

export interface CatalogEntry {
  component: UISchema["component"];
  /** Props de ejemplo. Totales ancla verificados contra backend/tests;
   *  desgloses y series marcados "muestra" son ilustrativos para
   *  previsualizar el visual. */
  props: any;
  title: string;
  source: string;
}

/**
 * Fixtures del catálogo. Misma fuente conceptual que usará la UI final;
 * solo cambia quién elige (galería: todas; producto: la IA).
 */
export const CATALOG: CatalogEntry[] = [
  {
    component: "receivables_resolution",
    props: { count: 5, total: "76550.00" },
    title: "Cuentas por cobrar",
    source: "GET /api/receivables (5 facturas, $76,550)",
  },
  {
    component: "receipts_resolution",
    props: { count: 4, total: "2123.00" },
    title: "Gastos sin factura",
    source: "GET /api/matches?status=unmatched (4 gastos, $2,123)",
  },
  {
    component: "time_series",
    props: {
      title: "Money Flow",
      points: [
        { label: "Dom", income: 12400, expenses: 9800 },
        { label: "Lun", income: 18200, expenses: 15300 },
        { label: "Mar", income: 9600, expenses: 12100 },
        { label: "Mié", income: 14100, expenses: 8900 },
        { label: "Jue", income: 17800, expenses: 13400 },
        { label: "Vie", income: 22100, expenses: 16900 },
        { label: "Sáb", income: 10500, expenses: 9200 },
      ],
      series: "both",
      period_label: "7 días",
      footnote: "Superávit 4 de 7 días; el jueves concentra el ingreso.",
    },
    title: "Flujo de dinero (muestra semanal)",
    source: "Estructura = DashboardDailyPoint[]; serie ilustrativa",
  },
  {
    component: "banorte_best_loans",
    props: {
      amount: "400000",
      options: [
        {
          id: "cred_simple_negocios",
          nombre: "Crédito Simple Negocios",
          tasa_anual: "0.1890",
          pago_mensual: "36843.54",
          costo_total: "50122.48",
          plazo_meses: 12,
        },
        {
          id: "cred_equipamiento",
          nombre: "Crédito Equipamiento",
          tasa_anual: "0.1650",
          pago_mensual: "19680.94",
          costo_total: "82342.56",
          plazo_meses: 24,
        },
      ],
      top_ids: ["cred_simple_negocios"],
      rationale:
        "Menor costo total para tu capacidad ($100k de utilidad). El top lo elige el Analista.",
    },
    title: "Mejores créditos Banorte",
    source: "Tool banorte_compare_loans $400k (cifras del motor) + top_ids del Analista",
  },
  {
    component: "hero_number",
    props: {
      label: "Efectivo disponible",
      sublabel: "Banorte · cuenta eje",
      value: "$1,294.68",
      delta: "4 días de caja",
      tone: "negative",
    },
    title: "Número héroe",
    source: "GET /api/summary (efectivo) + signals.runway_dias",
  },
  {
    component: "multi_ring",
    props: {
      items: [
        { label: "Gasto deducible", value: 96.2 },
        { label: "Margen del mes", value: -2.0 },
      ],
      footnote: "96% deducible sostiene el flujo; el margen sigue en rojo.",
    },
    title: "Anillos múltiples",
    source: "signals.pct_gasto_deducible (0.9623) + signals.margen (-0.0200)",
  },
  {
    component: "bars_total",
    props: {
      title: "Ingresos por mes",
      total: "$1,046,497.16",
      values: [323494.19, 300638.3, 422364.67],
      labels: ["JUN", "JUL", "AGO"],
      footnote: "Agosto rebota 40% tras la caída de julio.",
    },
    title: "Barras con total",
    source: "Serie de muestra (ago verificado: $422,364.67)",
  },
  {
    component: "progress_list",
    props: {
      title: "% cobrado por cliente (top 5)",
      items: [
        { label: "CONSTRUCTORA VIA NORTE", percent: 100 },
        { label: "DISTRIBUIDORA DEL NORTE", percent: 62 },
        { label: "TRANSPORTES DEL PACIFICO", percent: 41 },
        { label: "COMERCIALIZADORA DEL BAJIO", percent: 18 },
        { label: "PEDRO A. RUIZ", percent: 0 },
      ],
      footnote: "2 de 5 clientes ya pagaron todo; 1 sin ningún pago.",
    },
    title: "Barras de progreso",
    source: "Serie de muestra (estructura = receivables por cliente)",
  },
  {
    component: "donut_total",
    props: {
      title: "Efectivo vs por cobrar",
      center_value: "$77,844.68",
      center_label: "Liquidez total",
      segments: [
        { label: "Efectivo", value: 1294.68 },
        { label: "Por cobrar", value: 76550.0 },
      ],
      footnote: "El 98% de la liquidez está por cobrar, no en caja.",
    },
    title: "Dona con total",
    source: "summary.efectivo + receivables.total_pending",
  },
  {
    component: "entity_cluster",
    props: {
      title: "Principales clientes",
      subtitle: "5 clientes activos este mes",
      items: [
        { name: "Constructora Via Norte" },
        { name: "Distribuidora del Norte" },
        { name: "Transportes del Pacifico" },
        { name: "Comercializadora del Bajio" },
        { name: "Pedro A. Ruiz" },
      ],
      action_label: "Ver todos",
      footnote: "5 clientes activos; el top concentra la cobranza.",
    },
    title: "Cluster de entidades",
    source: "GET /api/receivables (razones sociales)",
  },
  {
    component: "action_card",
    props: {
      eyebrow: "REQUIERE ATENCIÓN",
      title: "Gastos sin factura",
      body: "4 gastos necesitan una factura. Suman $2,123.00 sin CFDI asociado.",
      value: "$2,123.00",
      action_label: "Resolver",
      tone: "urgent",
    },
    title: "Tarjeta de acción",
    source: "Alerta sin_factura (titulo + detalle + total)",
  },
  {
    component: "waterfall",
    props: {
      title: "De ventas a utilidad (ago)",
      bars: [
        { label: "Ventas", value: 422364.67 },
        { label: "Proveedores", value: -285011.22 },
        { label: "Servicios", value: -68634.74 },
        { label: "Impuestos", value: -31375.0 },
        { label: "Otros", value: -45780.99 },
        { label: "Utilidad", value: -8437.28 },
      ],
      footnote: "Proveedores se lleva 2 de cada 3 pesos vendidos.",
    },
    title: "Cascada",
    source: "Estructura = signals.gasto_por_rubro; desglose ilustrativo, totales verificados (422,364.67 − … = −8,437.28)",
  },
  {
    component: "insight_text",
    props: {
      title: "Tu caja aguanta 4 días",
      body: "Con el ritmo actual de gasto, el efectivo de $1,294.68 cubre aproximadamente 4 días. Las 5 facturas por cobrar ($76,550.00) cambiarían el panorama si se cobran esta semana.",
      tone: "urgent",
      evidence: [
        "runway_dias = 4 (signals, ago-2026)",
        "cuentas_por_cobrar = $76,550.00 en 5 facturas",
        "burn_mensual = $8,437.28",
      ],
    },
    title: "Insight de texto",
    source: "Analyst_insights (T8): texto + evidencia citada",
  },
  {
    component: "metric_trend",
    props: {
      label: "Margen del mes",
      value: "-2.0%",
      change: "+2.6pp",
      values: [-4.6, -3.8, -2.0],
      tone: "urgent",
      footnote: "Mejora 3 meses seguidos pero sigue en terreno negativo.",
    },
    title: "Métrica con tendencia",
    source: "signals.margen (-0.0200) + margen_delta_pp (+0.0264); serie ilustrativa",
  },
  {
    component: "transactions_list",
    props: {
      items: [
        { id: "txn_2026080472", merchant: "BANORTE", category: "comision", date: "2026-08-31T12:00:00", amount: "400.00", type: "egreso" },
        { id: "txn_2026080473", merchant: "BANORTE", category: "comision", date: "2026-08-31T12:00:00", amount: "64.00", type: "egreso" },
        { id: "txn_2026080458", merchant: "BANORTE", category: "comision", date: "2026-08-31T12:00:00", amount: "5.00", type: "egreso" },
        { id: "txn_2026080459", merchant: "BANORTE", category: "iva_comision", date: "2026-08-31T12:00:00", amount: "0.80", type: "egreso" },
      ],
    },
    title: "Movimientos recientes",
    source: "Filas reales seed/transactions.csv (31-ago, IDs verificados)",
  },
  {
    component: "timeline_list",
    props: {
      items: [
        { id: "A-1001", customer_name: "CONSTRUCTORA VIA NORTE", due_date: "2026-09-12", issued_at: "2026-08-13", amount_pending: "18500.00", status: "open" },
        { id: "A-1002", customer_name: "DISTRIBUIDORA DEL NORTE", due_date: "2026-09-15", issued_at: "2026-08-16", amount_pending: "16200.00", status: "open" },
        { id: "A-1003", customer_name: "TRANSPORTES DEL PACIFICO", due_date: "2026-09-18", issued_at: "2026-08-19", amount_pending: "14850.00", status: "open" },
        { id: "A-1004", customer_name: "COMERCIALIZADORA DEL BAJIO", due_date: "2026-09-20", issued_at: "2026-08-21", amount_pending: "14200.00", status: "open" },
        { id: "A-1005", customer_name: "PEDRO A. RUIZ", due_date: "2026-09-25", issued_at: "2026-08-26", amount_pending: "12800.00", status: "open" },
      ],
    },
    title: "Próximos cobros",
    source: "5 clientes reales; partición ilustrativa que suma $76,550.00 exactos",
  },
  {
    component: "tax_summary",
    props: { isr_estimado: "0.00", iva_neto: "-36876.40", pct_deducible: 0.962 },
    title: "Resumen fiscal",
    source: "ISR 0 (utilidad negativa ago) + signals.iva_neto + pct_gasto_deducible (0.9623)",
  },
];
