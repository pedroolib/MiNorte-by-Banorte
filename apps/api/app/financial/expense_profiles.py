"""Catálogo de gastos evaluables (datos, no código).

Cada tipo declara sus variables con tipo/unidad, obligatoriedad
condicional, defaults explícitos y la pregunta tailored en español.
Agregar un gasto nuevo = añadir una entrada aquí; el Consultor no cambia.
"""

from __future__ import annotations

MONEY = {"tipo": "money", "unidad": "MXN"}
PERCENT = {"tipo": "percent", "unidad": "%"}
MONTHS = {"tipo": "int", "unidad": "meses"}

EXPENSE_PROFILES: dict[str, dict] = {
    "empleado": {
        "label": "Contratación de personal",
        "variables": [
            {"nombre": "monthly_cost_total", **MONEY, "requerido": False,
             "pregunta": "¿Cuánto cuesta en total al mes (bruto + prestaciones)?"},
            {"nombre": "salary_base", **MONEY, "requerido": False,
             "pregunta": "¿Cuál es el sueldo base mensual (bruto)?"},
            {"nombre": "benefits_pct", **PERCENT, "requerido": False,
             "default": "0.30",
             "default_nota": "Prestaciones 30% sobre sueldo base.",
             "pregunta": "¿Qué % de prestaciones aplico? (default 30%)"},
            {"nombre": "contract_type", "tipo": "enum", "unidad": "",
             "requerido": False, "default": "planta",
             "default_nota": "Contrato de planta (indefinido).",
             "opciones": ["planta", "temporal"],
             "pregunta": "¿Es de planta o temporal?"},
            {"nombre": "contract_months", **MONTHS, "requerido": False,
             "requerido_si": {"campo": "contract_type", "es": "temporal"},
             "pregunta": "¿Por cuántos meses es el contrato temporal?"},
        ],
        "requerido_uno_de": [["monthly_cost_total"], ["salary_base"]],
    },
    "mercancia": {
        "label": "Compra de mercancía para reventa",
        "variables": [
            {"nombre": "purchase_cost", **MONEY, "requerido": True,
             "pregunta": "¿Cuánto cuesta la mercancía?"},
            {"nombre": "expected_margin_pct", **PERCENT, "requerido": False,
             "pregunta": "¿Qué margen esperas (en % sobre el costo)?"},
            {"nombre": "expected_revenue", **MONEY, "requerido": False,
             "pregunta": "¿En cuánto esperas venderla en total?"},
            {"nombre": "months_to_sell", **MONTHS, "requerido": False,
             "default": "3",
             "default_nota": "Venta distribuida en 3 meses.",
             "pregunta": "¿En cuántos meses la venderías? (default 3)"},
        ],
        "requerido_uno_de": [["expected_margin_pct"], ["expected_revenue"]],
    },
    "auto": {
        "label": "Compra de auto",
        "variables": [
            {"nombre": "price", **MONEY, "requerido": True,
             "pregunta": "¿Cuál es el precio del auto?"},
            {"nombre": "payment_modality", "tipo": "enum", "unidad": "",
             "requerido": True, "opciones": ["contado", "financiado"],
             "pregunta": "¿De contado o financiado?"},
            {"nombre": "down_payment", **MONEY, "requerido": False,
             "pregunta": "¿Cuánto das de enganche?"},
            {"nombre": "down_payment_pct", **PERCENT, "requerido": False,
             "default": "0.20",
             "default_nota": "Enganche 20% del precio.",
             "pregunta": "¿Qué % de enganche? (default 20%)"},
            {"nombre": "tasa_anual", "tipo": "rate", "unidad": "%",
             "requerido": False,
             "pregunta": "¿Qué tasa anual nominal te ofrecen?"},
            {"nombre": "cat_anual", "tipo": "rate", "unidad": "%",
             "requerido": False,
             "pregunta": "¿O qué CAT anual (todo incluido)?"},
            {"nombre": "months", **MONTHS, "requerido": False,
             "requerido_si": {"campo": "payment_modality", "es": "financiado"},
             "pregunta": "¿A cuántos meses?"},
            {"nombre": "monthly_insurance", **MONEY, "requerido": False,
             "default": "0",
             "default_nota": "Sin seguro proporcionado.",
             "pregunta": "¿Cuánto pagarías de seguro al mes? (0 si no aplica)"},
            {"nombre": "monthly_fuel_maintenance", **MONEY, "requerido": False,
             "default": "0",
             "default_nota": "Sin gasolina/mantenimiento proporcionado.",
             "pregunta": "¿Gasolina y mantenimiento al mes? (0 si no aplica)"},
            {"nombre": "residual_value", **MONEY, "requerido": False,
             "default": "0",
             "default_nota": "Sin valor de rescate.",
             "pregunta": "¿Valor de rescate al final? (0 si no aplica)"},
        ],
        "requerido_uno_de": [],
    },
    "terreno": {
        "label": "Compra de terreno",
        "variables": [
            {"nombre": "price", **MONEY, "requerido": True,
             "pregunta": "¿Cuál es el precio del terreno?"},
            {"nombre": "payment_modality", "tipo": "enum", "unidad": "",
             "requerido": True, "opciones": ["contado", "hipotecario"],
             "pregunta": "¿De contado o hipotecario?"},
            {"nombre": "down_payment", **MONEY, "requerido": False,
             "pregunta": "¿Cuánto das de enganche?"},
            {"nombre": "down_payment_pct", **PERCENT, "requerido": False,
             "default": "0.20",
             "default_nota": "Enganche 20% del precio.",
             "pregunta": "¿Qué % de enganche? (default 20%)"},
            {"nombre": "tasa_anual", "tipo": "rate", "unidad": "%",
             "requerido": False,
             "pregunta": "¿Qué tasa anual nominal te ofrecen?"},
            {"nombre": "cat_anual", "tipo": "rate", "unidad": "%",
             "requerido": False,
             "pregunta": "¿O qué CAT anual (todo incluido)?"},
            {"nombre": "months", **MONTHS, "requerido": False,
             "requerido_si": {"campo": "payment_modality", "es": "hipotecario"},
             "pregunta": "¿A cuántos meses?"},
            {"nombre": "monthly_costs", **MONEY, "requerido": False,
             "default": "0",
             "default_nota": "Sin predial/mantenimiento proporcionado.",
             "pregunta": "¿Predial o mantenimiento mensual? (0 si no aplica)"},
        ],
        "requerido_uno_de": [],
    },
    "construccion": {
        "label": "Construcción por etapas o presupuesto",
        "variables": [
            {"nombre": "total_budget", **MONEY, "requerido": True,
             "pregunta": "¿Cuál es el presupuesto total?"},
            {"nombre": "duration_months", **MONTHS, "requerido": True,
             "pregunta": "¿En cuántos meses se ejecuta?"},
            {"nombre": "upfront_amount", **MONEY, "requerido": False,
             "default": "0",
             "default_nota": "Sin anticipo inicial.",
             "pregunta": "¿Hay anticipo inicial? (0 si no)"},
        ],
        "requerido_uno_de": [],
    },
    "renta": {
        "label": "Renta de local u oficina",
        "variables": [
            {"nombre": "monthly_rent", **MONEY, "requerido": True,
             "pregunta": "¿Cuánto es la renta mensual?"},
            {"nombre": "deposit", **MONEY, "requerido": False,
             "default": "one_month_rent",
             "default_nota": "Depósito = 1 mes de renta.",
             "pregunta": "¿Depósito? (default: 1 mes)"},
            {"nombre": "term_months", **MONTHS, "requerido": False,
             "default": "12",
             "default_nota": "Contrato a 12 meses.",
             "pregunta": "¿A cuántos meses? (default 12)"},
            {"nombre": "annual_increase_pct", **PERCENT, "requerido": False,
             "default": "0",
             "default_nota": "Sin incremento anual.",
             "pregunta": "¿Incremento anual? (default 0%)"},
        ],
        "requerido_uno_de": [],
    },
    "maquinaria": {
        "label": "Compra de maquinaria o equipo",
        "variables": [
            {"nombre": "price", **MONEY, "requerido": True,
             "pregunta": "¿Cuál es el precio del equipo?"},
            {"nombre": "payment_modality", "tipo": "enum", "unidad": "",
             "requerido": True, "opciones": ["contado", "financiado"],
             "pregunta": "¿De contado o financiado?"},
            {"nombre": "down_payment", **MONEY, "requerido": False,
             "pregunta": "¿Cuánto das de enganche?"},
            {"nombre": "down_payment_pct", **PERCENT, "requerido": False,
             "default": "0.20",
             "default_nota": "Enganche 20% del precio.",
             "pregunta": "¿Qué % de enganche? (default 20%)"},
            {"nombre": "tasa_anual", "tipo": "rate", "unidad": "%",
             "requerido": False,
             "pregunta": "¿Qué tasa anual nominal te ofrecen?"},
            {"nombre": "cat_anual", "tipo": "rate", "unidad": "%",
             "requerido": False,
             "pregunta": "¿O qué CAT anual (todo incluido)?"},
            {"nombre": "months", **MONTHS, "requerido": False,
             "requerido_si": {"campo": "payment_modality", "es": "financiado"},
             "pregunta": "¿A cuántos meses?"},
            {"nombre": "monthly_maintenance", **MONEY, "requerido": False,
             "default": "0",
             "default_nota": "Sin mantenimiento proporcionado.",
             "pregunta": "¿Mantenimiento mensual? (0 si no aplica)"},
            {"nombre": "monthly_benefit", **MONEY, "requerido": False,
             "default": "0",
             "default_nota": "Sin ahorro/ingreso atribuible proporcionado.",
             "pregunta": "¿Cuánto ahorra o genera al mes? (0 si no aplica)"},
        ],
        "requerido_uno_de": [],
    },
}


def list_expense_types() -> list[dict]:
    return [{"tipo": k, "label": v["label"]} for k, v in EXPENSE_PROFILES.items()]


def get_profile(expense_type: str) -> dict:
    if expense_type not in EXPENSE_PROFILES:
        raise ValueError(
            f"tipo inválido: {expense_type!r}; válidos: {sorted(EXPENSE_PROFILES)}")
    return EXPENSE_PROFILES[expense_type]
