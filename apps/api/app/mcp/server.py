"""MCP server MiNorte (T8): expone las tools a clientes MCP externos.

El loop de nuestros agentes usa app.mcp.tools directamente (in-process);
este servidor registra las mismas impls para terceros.
"""

from app.mcp import tools as T

try:  # mcp 2.x: FastMCP -> MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # pragma: no cover
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        FastMCP = None  # type: ignore

mcp = FastMCP("minorte") if FastMCP else None

if mcp is not None:  # pragma: no cover - transporte, no lógica

    @mcp.tool()
    def banorte_get_transactions(month: str | None = None, categoria: str | None = None,
                                 tipo: str | None = None, limit: int = 200) -> list:
        """Movimientos bancarios (mock)."""
        return T.banorte_get_transactions(month, categoria, tipo, limit)

    @mcp.tool()
    def banorte_get_balance() -> dict:
        """Último saldo bancario (mock)."""
        return T.banorte_get_balance()

    @mcp.tool()
    def banorte_get_credit_options() -> dict:
        """Catálogo de créditos mock."""
        return T.banorte_get_credit_options()

    @mcp.tool()
    def banorte_compare_loans(amount: str, months: int | None = None) -> dict:
        """Compara catálogo para un monto."""
        return T.banorte_compare_loans(amount, months)

    @mcp.tool()
    def sat_list_cfdis(tipo: str | None = None, limit: int = 50) -> list:
        """CFDIs por tipo (mock SAT)."""
        return T.sat_list_cfdis(tipo, limit)

    @mcp.tool()
    def sat_get_cfdi(uuid: str) -> dict:
        """CFDI por UUID."""
        return T.sat_get_cfdi(uuid)

    @mcp.tool()
    def get_financial_summary(month: str | None = None) -> dict:
        """Resumen del mes."""
        return T.get_financial_summary(month)

    @mcp.tool()
    def get_cash_flow(month: str | None = None) -> dict:
        """Flujo del mes."""
        return T.get_cash_flow(month)

    @mcp.tool()
    def get_months_with_data() -> dict:
        """Meses con transacciones + latest."""
        return T.get_months_with_data()

    @mcp.tool()
    def get_signals(month: str | None = None) -> dict:
        """Señales del motor."""
        return T.get_signals(month)

    @mcp.tool()
    def get_metric(name: str, month: str | None = None) -> dict:
        """Una métrica por nombre (ver metric_catalog)."""
        return T.get_metric(name, month)

    @mcp.tool()
    def metric_catalog() -> list:
        """Catálogo de métricas disponibles."""
        return T.metric_catalog()

    @mcp.tool()
    def get_open_receivables() -> dict:
        """CxC abiertas (items + count + total)."""
        return T.get_open_receivables()

    @mcp.tool()
    def get_merchants(rubro: str | None = None, min_total: str | None = None,
                      limit: int | None = 50, month: str | None = None) -> list:
        """Nivel 1: comercios por rubro/monto."""
        return T.get_merchants(rubro, min_total, limit, month)

    @mcp.tool()
    def get_merchant_detail(nombre: str, month: str | None = None) -> dict:
        """Nivel 2: serie + recurrencia de un comercio."""
        return T.get_merchant_detail(nombre, month)

    @mcp.tool()
    def get_variables_gasto(expense_type: str | None = None) -> dict:
        """Checklist del gasto."""
        return T.get_variables_gasto(expense_type)

    @mcp.tool()
    def evaluar_gasto(expense_type: str, variables: list | None = None,
                      month: str | None = None, horizon_months: int | None = None,
                      etapas: list | None = None) -> dict:
        """Evalúa cualquier gasto."""
        return T.evaluar_gasto(expense_type, variables, month, horizon_months, etapas)

    @mcp.tool()
    def get_customer_contact(customer_rfc: str) -> dict:
        """Contacto del directorio (nunca inventa)."""
        return T.get_customer_contact(customer_rfc)

    @mcp.tool()
    def prepare_payment_reminder(receivable_id: str) -> dict:
        """Borrador SIN enviar."""
        return T.prepare_payment_reminder(receivable_id)
