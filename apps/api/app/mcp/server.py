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
    def get_signals(month: str | None = None) -> dict:
        """Señales del motor."""
        return T.get_signals(month)

    @mcp.tool()
    def get_open_receivables() -> list:
        """CxC abiertas."""
        return T.get_open_receivables()

    @mcp.tool()
    def simulate_hiring(monthly_cost: str, month: str | None = None) -> dict:
        """¿Aguanta una contratación?"""
        return T.simulate_hiring(monthly_cost, month)

    @mcp.tool()
    def simulate_loan(amount: str, annual_rate: str = "0.24", months: int = 12) -> dict:
        """Amortización + cobertura."""
        return T.simulate_loan(amount, annual_rate, months)

    @mcp.tool()
    def get_customer_contact(customer_rfc: str) -> dict:
        """Contacto del directorio (nunca inventa)."""
        return T.get_customer_contact(customer_rfc)

    @mcp.tool()
    def prepare_payment_reminder(receivable_id: str) -> dict:
        """Borrador SIN enviar."""
        return T.prepare_payment_reminder(receivable_id)
