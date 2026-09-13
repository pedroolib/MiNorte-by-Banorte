"""Tools MCP (T8): fuente única para agentes y clientes MCP externos.

Cada tool es una función pura sobre app.data + engine + repos, con schema
JSON estricto (compatible OpenAI strict + MCP inputSchema). Sin LLM aquí.
Montos como string (Decimal JSON). Fuentes mock marcadas source=mock_*.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from app import data
from app.agents.llm import ToolDef
from app.config import get_settings
from app.financial import engine as en
from app.financial import reconcile as rc
from app.financial.categorias import RUBROS
from app.operator import collections as op

OBJ = {"type": "object", "properties": {}, "required": [],
       "additionalProperties": False}


def _schema(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required,
            "additionalProperties": False}


def _s(v) -> str:
    return str(v)


def _deep(v):
    from decimal import Decimal as _D
    if isinstance(v, _D):
        return str(v)
    if isinstance(v, dict):
        return {kk: _deep(vv) for kk, vv in v.items()}
    if isinstance(v, (list, tuple)):
        return [_deep(x) for x in v]
    return v


def _month_arg(month: str | None) -> tuple[int, int]:
    month = month or data.latest_month()
    a, m = map(int, month.split("-"))
    return a, m


# ---------- banking ----------

def banorte_get_transactions(month: str | None = None, categoria: str | None = None,
                             tipo: str | None = None, limit: int | None = 200) -> list[dict]:
    out = []
    tope = max(1, min(limit or 200, 500))
    for t in data.get_transactions():
        if month and t.date.strftime("%Y-%m") != month:
            continue
        if categoria and t.categoria != categoria:
            continue
        if tipo and t.type != tipo:
            continue
        out.append({"id": t.id, "fecha": t.date.isoformat(), "descripcion": t.description,
                    "comercio": t.merchant_name, "tipo": t.type, "monto": _s(t.amount),
                    "saldo": _s(t.balance) if t.balance is not None else None,
                    "categoria": t.categoria, "rubro": t.rubro})
        if len(out) >= tope:
            break
    return out


def banorte_get_balance() -> dict:
    txns = sorted(data.get_transactions(), key=lambda t: (t.date, t.id))
    ult = txns[-1]
    return {"saldo": _s(ult.balance), "fecha": ult.date.isoformat(),
            "source": "mock_banorte"}


def _credit_options() -> list[dict]:
    for base in (Path.cwd(), Path(__file__).resolve().parents[3]):
        p = base / "seed" / "credit_options.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return []


def banorte_get_credit_options() -> dict:
    """Catálogo mock (spec #10): no son ofertas reales contratables hoy."""
    return {"source": "mock_banorte", "nota": "catálogo demostrativo",
            "items": _credit_options()}


def banorte_compare_loans(amount: str, months: int | None = None) -> dict:
    txns = data.get_transactions()
    a, m = _month_arg(None)
    inc = en.income_statement(txns, a, m)
    r = en.compare_credit_options(inc["utilidad"], Decimal(amount),
                                  _credit_options(), months)
    r["utilidad_mensual"] = _s(inc["utilidad"])
    r["amount"] = _s(r["amount"])
    for f in r["ranking"]:
        for k in ("pago_mensual", "total_intereses", "comision_apertura",
                  "costo_total", "cobertura"):
            f[k] = _s(f[k]) if f[k] is not None else None
    if r["recomendada"]:
        rec = dict(r["recomendada"])
        r["recomendada"] = rec
    return r


# ---------- fiscal ----------

def sat_list_cfdis(tipo: str | None = None, limit: int | None = 50) -> list[dict]:
    out = []
    tope = max(1, min(limit or 50, 200))
    for c in data.get_cfdis():
        if tipo in ("emitido", "recibido") and c.tipo != tipo:
            continue
        out.append({"uuid": c.uuid, "tipo": c.tipo, "total": _s(c.total),
                    "fecha_emision": c.fecha_emision.isoformat(),
                    "emisor": c.emisor_nombre, "receptor": c.receptor_nombre,
                    "folio": f"{c.serie or ''}-{c.folio or ''}".strip("-")})
        if len(out) >= tope:
            break
    return out


def sat_get_cfdi(uuid: str) -> dict:
    for c in data.get_cfdis():
        if c.uuid.lower() == uuid.lower():
            return c.model_dump(mode="json")
    raise ValueError(f"CFDI no existe: {uuid}")


# ---------- financial ----------

def get_financial_summary(month: str | None = None) -> dict:
    from app.repositories import financial_repo as fr

    company_id = get_settings().COMPANY_ID
    month = month or data.latest_month()
    sb = None
    try:
        from app.db import get_supabase
        sb = get_supabase()
    except Exception:
        pass
    if sb is not None:
        try:
            snap = fr.fetch_snapshot(sb, company_id, month)
            if snap:
                return {"month": month, **{k: _s(snap[k]) for k in
                        ("ventas", "gastos", "utilidad", "efectivo",
                         "impuesto_estimado", "cxc_total", "flujo_neto")}}
        except Exception:
            pass
    txns = data.get_transactions()
    a, m = map(int, month.split("-"))
    fm = [t for t in txns if (t.date.year, t.date.month) == (a, m)]
    ventas = sum((t.amount for t in fm if t.type == "ingreso"), Decimal("0"))
    gastos = sum((t.amount for t in fm if t.type == "egreso"), Decimal("0"))
    ordenados = sorted(txns, key=lambda t: (t.date, t.id))
    return {"month": month, "ventas": _s(ventas), "gastos": _s(gastos),
            "utilidad": _s(ventas - gastos),
            "efectivo": _s(ordenados[-1].balance or Decimal("0"))}


def get_cash_flow(month: str | None = None) -> dict:
    a, m = _month_arg(month)
    cf = en.cash_flow(data.get_transactions(), a, m)
    return {"month": f"{a}-{m:02d}", **{k: _s(v) for k, v in cf.items()}}


def get_months_with_data() -> dict:
    """Meses YYYY-MM con transacciones. Úsala antes de analizar un mes:
    un mes fuera de esta lista NO tiene datos (no lo analices ni compares)."""
    meses = sorted({f"{t.date.year}-{t.date.month:02d}"
                    for t in data.get_transactions()})
    return {"months": meses, "latest": meses[-1] if meses else None}


def project_next_month(month: str | None = None) -> dict:
    """Proyección determinista del mes siguiente (run-rate + promedio).

    ÚNICA fuente válida para hablar de futuro: trae utilidad/ventas/
    gastos proyectados + método + confianza + supuestos + meses base.
    Sin llamar esta tool, PROHIBIDO proyectar.
    """
    a, m = _month_arg(month)
    p = en.project_next_month(data.get_transactions(), data.get_cfdis(),
                              data.get_matches(), a, m)

    def _j(v):
        if isinstance(v, Decimal):
            return str(v)
        if isinstance(v, list):
            return [_j(x) for x in v]
        return v

    return {k: _j(v) for k, v in p.items()}


def get_signals(month: str | None = None) -> dict:
    a, m = _month_arg(month)
    s = en.signals(data.get_transactions(), data.get_cfdis(),
                   data.get_matches(), a, m)

    def _j(v):
        if isinstance(v, Decimal):
            return str(v)
        if isinstance(v, dict):
            return {kk: _j(vv) for kk, vv in v.items()}
        if isinstance(v, (list, tuple)):
            return [_j(x) for x in v]
        return v

    out = {"month": f"{a}-{m:02d}", "signals": {k: _j(v) for k, v in s.items()},
           "brief": en.brief_mensual(s, a, m)}
    if not s.get("tiene_datos"):
        out["advertencia"] = (f"{a}-{m:02d} sin movimientos; "
                              f"último mes con datos: {data.latest_month()}")
    return out


def metric_catalog() -> list[dict]:
    """Catálogo auto-generado desde engine (una entrada por señal)."""
    return en.metric_catalog()


def get_metric(name: str, month: str | None = None) -> dict:
    """Una métrica por nombre. Desconocida -> error con el catálogo."""
    a, m = _month_arg(month)
    s = en.signals(data.get_transactions(), data.get_cfdis(),
                   data.get_matches(), a, m)
    if name not in s:
        disponibles = sorted(metric_catalog(), key=lambda e: e["nombre"])
        raise ValueError(
            f"métrica inexistente: {name!r}. Disponibles: "
            + ", ".join(e["nombre"] for e in disponibles))
    meta = next(e for e in metric_catalog() if e["nombre"] == name)
    return {"name": name, "month": f"{a}-{m:02d}",
            "value": _deep(s[name]),
            "unidad": meta["unidad"], "familia": meta["familia"],
            "descripcion": meta["descripcion"]}


def get_open_receivables() -> dict:
    recs = rc.detectar_cxc(data.get_cfdis(), data.get_matches(),
                           get_settings().COMPANY_ID)
    por_uuid = {c.uuid: c for c in data.get_cfdis()}
    out = []
    for r in recs:
        c = por_uuid.get(r.cfdi_id)
        out.append({"id": r.id, "cfdi_uuid": r.cfdi_id, "customer": r.customer_name,
                    "customer_rfc": r.customer_rfc,
                    "amount_pending": _s(r.amount_pending),
                    "issued_at": r.issued_at.isoformat(),
                    "due_date": r.due_date.isoformat() if r.due_date else None,
                    "folio": f"{c.serie or ''}-{c.folio or ''}".strip("-") if c else ""})
    total = sum((r.amount_pending or Decimal("0") for r in recs), Decimal("0"))
    return {"items": out, "count": len(out), "total": _s(total)}


def get_merchants(rubro: str | None = None, min_total: str | None = None,
                  limit: int | None = 50, month: str | None = None) -> list[dict]:
    """Nivel 1: detalle por comercio (filtrable). El agente decide cuántos."""
    a, m = _month_arg(month)
    filas = en.merchants_por_rubro(data.get_transactions(), a, m, rubro,
                                   Decimal(min_total) if min_total else 0,
                                   int(limit or 50))
    return [{**f, "total": _s(f["total"])} for f in filas]


def get_merchant_detail(nombre: str, month: str | None = None) -> dict:
    """Nivel 2: serie mensual + recurrencia de un comercio (caza-fugas)."""
    a, m = _month_arg(month)
    d = en.merchant_detail(data.get_transactions(), nombre, a, m)
    d["serie"] = [{**s, "total": _s(s["total"])} for s in d["serie"]]
    d["ticket_promedio_mensual"] = _s(d["ticket_promedio_mensual"])
    d["total_periodo"] = _s(d["total_periodo"])
    return d


def get_variables_gasto(expense_type: str | None = None) -> dict:
    """Checklist del gasto (qué preguntar). Sin cálculos."""
    from app.financial.expense_evaluation import variables_checklist

    return variables_checklist(expense_type)


def _deep_str(obj):
    from decimal import Decimal as _D

    if isinstance(obj, _D):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _deep_str(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_deep_str(v) for v in obj]
    return obj


def evaluar_gasto(expense_type: str, variables: list | None = None,
                  month: str | None = None, horizon_months: int | None = None,
                  etapas: list | None = None) -> dict:
    """Evalúa CUALQUIER gasto: valida, calcula y dictamina.

    Faltantes -> error 'falta: ...' (el modelo repregunta, máx 2 rondas).
    Nunca adivina: defaults siempre declarados en 'supuestos'.
    """
    from app import data as _data
    from app.financial.expense_evaluation import evaluar_gasto as _ev

    txns = _data.get_transactions()
    r = _ev(txns, expense_type, variables or [], month=month,
            horizon_months=horizon_months, etapas=etapas)
    return _deep_str(r)


# ---------- operations lectura ----------

def get_customer_contact(customer_rfc: str) -> dict:
    from app.db import get_supabase
    from app.repositories import collections_repo as col

    sb = get_supabase()
    if sb is None:
        raise ValueError("directorio no disponible (sin Supabase)")
    try:
        c = col.get_contact(sb, get_settings().COMPANY_ID, customer_rfc)
    except Exception as e:
        raise ValueError(f"directorio no disponible ({e})")
    if not c or not c.get("email"):
        return {"tiene_email": False,
                "detalle": "sin correo en el directorio: captúralo antes de enviar"}
    return {"tiene_email": True, "email": c["email"],
            "customer_name": c.get("customer_name", "")}


def extract_receipt(image_base64: str, mime: str = "image/jpeg") -> dict:
    """Ticket real (foto en base64) -> extracción Vision (spec #19)."""
    import base64

    from app.integrations.invoicing import vision

    return vision.extract_receipt(base64.b64decode(image_base64), mime)


def match_receipt_to_transaction(extraction: dict) -> list[dict]:
    """Candidatos de match ticket<->movimiento (misma fórmula que
    `reconcile.py`, no se reimplementa el score)."""
    from app.operator import receipts as op_receipts

    cands = op_receipts.match_candidates(extraction, data.get_transactions())
    return [_deep(c) for c in cands]


def get_fiscal_profile() -> dict:
    """Perfil fiscal del receptor (spec #11: autorización delegada)."""
    from app.operator import receipts as op_receipts

    return op_receipts.get_fiscal_profile()


def prepare_invoice_request(extraction: dict, uso_cfdi: str = "G03") -> dict:
    """Payload real para el Browser Agent. Nunca inventa datos: lo que
    Vision no leyó llega null (el agente debe pedirlo, no adivinarlo).

    NOTA (spec #19): el envío (`submit_invoice_request`) y la reconciliación
    final (`reconcile_cfdi`) requieren confirmación humana antes de la
    acción irreversible y viven en `POST /api/tickets/*` (con esa guarda
    de UI), no en este loop de tools sin supervisión.
    """
    from app.operator import receipts as op_receipts

    perfil = op_receipts.get_fiscal_profile()
    return op_receipts.build_invoice_payload(extraction, perfil, uso_cfdi)


def prepare_payment_reminder(receivable_id: str) -> dict:
    recs = {r["id"]: r for r in get_open_receivables()["items"]}
    if receivable_id not in recs:
        raise ValueError(f"receivable no abierto: {receivable_id}")
    r = recs[receivable_id]
    cfdis = {c.uuid: c for c in data.get_cfdis()}
    c = cfdis.get(r["cfdi_uuid"])
    return op.prepare_draft(
        {"id": r["id"], "customer_name": r["customer"],
         "amount_pending": r["amount_pending"],
         "issued_at": r["issued_at"], "due_date": r["due_date"]},
        (c.model_dump(mode="json") if c else {"uuid": "", "serie": "", "folio": ""}),
        None, {"razon_social": "CAFE NORTENO SA DE CV",
               "nombre_comercial": "Café Norteño"})


# ---------- registry ----------

def _req(*names: str) -> list[str]:
    return list(names)


TOOLS: list[dict] = []


def _t(name: str, desc: str, props: dict, required: list[str], fn):
    # OpenAI strict: required incluye TODAS las propiedades (el modelo
    # manda null en las opcionales; las impls lo tratan como ausente).
    required = list(props.keys())
    TOOLS.append({"name": name, "description": desc,
                  "parameters": {"type": "object", "properties": props,
                                 "required": required,
                                 "additionalProperties": False},
                  "fn": fn})


_STR = {"type": "string"}
_NUM = {"type": "string", "description": "Decimal como string"}
_INT = {"type": "integer"}

_t("banorte_get_transactions", "Movimientos bancarios (mock). Filtros opcionales.",
   {"month": {**_STR, "description": "YYYY-MM"},
    "categoria": _STR, "tipo": {**_STR, "description": "ingreso|egreso"},
    "limit": {**_INT, "description": "1-500"}}, [], banorte_get_transactions)
_t("banorte_get_balance", "Último saldo bancario (mock).", {}, [], banorte_get_balance)
_t("banorte_get_credit_options", "Catálogo de créditos mock (no contratables directo).",
   {}, [], banorte_get_credit_options)
_t("banorte_compare_loans", "Compara catálogo para un monto: pago, costo, cobertura.",
   {"amount": {**_NUM, "description": "monto solicitado"},
    "months": {**_INT, "description": "plazo exacto opcional"}}, ["amount"], banorte_compare_loans)
_t("sat_list_cfdis", "CFDIs por tipo (mock SAT).", {"tipo": _STR, "limit": _INT}, [], sat_list_cfdis)
_t("sat_get_cfdi", "CFDI por UUID.", {"uuid": _STR}, ["uuid"], sat_get_cfdi)
_t("get_financial_summary", "Resumen del mes (snapshot o live).",
   {"month": _STR}, ["month"], get_financial_summary)
_t("get_cash_flow", "Flujo del mes.", {"month": _STR}, [], get_cash_flow)
_t("get_months_with_data",
   "Meses YYYY-MM con transacciones + latest. Úsala antes de analizar: "
   "un mes fuera de la lista NO tiene datos (no analizar ni comparar).",
   {}, [], get_months_with_data)
_t("project_next_month",
   "Proyección determinista del mes siguiente (utilidad/ventas/gastos + "
   "método + confianza + supuestos). ÚNICA vía para hablar de futuro.",
   {"month": _STR}, [], project_next_month)
_t("get_signals", "Señales del motor para análisis.", {"month": _STR}, [], get_signals)
_t("get_metric",
   "Una métrica por nombre (ver metric_catalog). Con month resuelve ese mes.",
   {"name": {"type": "string", "description": "nombre exacto del catálogo"},
    "month": {"type": ["string", "null"], "description": "YYYY-MM o null=último"}},
   ["name", "month"], get_metric)
_t("metric_catalog",
   "Catálogo de métricas disponibles: nombre, descripción, unidad, familia.",
   {}, [], metric_catalog)
_t("get_open_receivables", "CxC abiertas con folio y vencimiento.", {}, [], get_open_receivables)
_t("get_merchants", "Nivel 1: comercios por rubro/monto. Tú decides cuántos traer.",
   {"rubro": {"type": ["string", "null"], "enum": RUBROS + [None],
              "description": "código de rubro o null para todos"},
    "min_total": _NUM, "limit": _INT, "month": _STR},
   ["rubro", "min_total", "limit", "month"], get_merchants)
_t("get_merchant_detail", "Nivel 2: serie mensual + recurrencia de un comercio.",
   {"nombre": _STR, "month": _STR}, ["nombre", "month"], get_merchant_detail)
_t("get_variables_gasto",
   "Checklist del gasto: qué variables pedir según el tipo. Úsala antes de evaluar.",
   {"expense_type": {"type": ["string", "null"],
                     "enum": ["empleado", "mercancia", "auto", "terreno",
                              "construccion", "renta", "maquinaria", None],
                     "description": "tipo o null para ver el catálogo"}},
   ["expense_type"], get_variables_gasto)
_t("evaluar_gasto",
   "Evalúa CUALQUIER gasto (empleado, mercancía, auto, terreno, construcción, "
   "renta, maquinaria): valida, calcula desembolso+flujos+amortización-ingresos "
   "y dictamina viable/ajustada/riesgosa/no_viable. "
   "Faltantes -> error 'falta: ...': repregunta tailored, máx 2 rondas, sin adivinar.",
   {"expense_type": {"type": "string",
                     "enum": ["empleado", "mercancia", "auto", "terreno",
                              "construccion", "renta", "maquinaria"]},
    "month": {"type": ["string", "null"], "description": "YYYY-MM o null=último"},
    "horizon_months": {"type": ["integer", "null"]},
    "variables": {"type": "array",
                  "description": "Variables mapeadas de lo dicho por el usuario",
                  "items": {"type": "object",
                            "properties": {
                                "nombre": {"type": "string"},
                                "valor": {"type": "string"},
                                "unidad": {"type": "string"}},
                            "required": ["nombre", "valor", "unidad"],
                            "additionalProperties": False}},
    "etapas": {"type": "array",
               "description": "Solo construcción: ministraciones por etapa",
               "items": {"type": "object",
                         "properties": {
                             "nombre": {"type": "string"},
                             "monto": {"type": "string"},
                             "mes": {"type": "integer"}},
                         "required": ["nombre", "monto", "mes"],
                         "additionalProperties": False}}},
   ["expense_type", "month", "horizon_months", "variables", "etapas"],
   evaluar_gasto)
_t("get_customer_contact", "Contacto del directorio por RFC (nunca inventa).",
   {"customer_rfc": _STR}, ["customer_rfc"], get_customer_contact)
_t("prepare_payment_reminder", "Borrador SIN enviar (el envío es endpoint con guardas).",
   {"receivable_id": _STR}, ["receivable_id"], prepare_payment_reminder)
_t("extract_receipt", "Ticket real (foto base64) -> extracción Vision: comercio, total, fecha, folio.",
   {"image_base64": _STR, "mime": _STR}, ["image_base64", "mime"], extract_receipt)
from app.integrations.invoicing.vision import EXTRACTION_SCHEMA as _EXTRACTION_OBJ  # noqa: E402

_t("match_receipt_to_transaction",
   "Candidatos de conciliación ticket<->movimiento (misma fórmula que reconcile.py).",
   {"extraction": _EXTRACTION_OBJ}, ["extraction"], match_receipt_to_transaction)
_t("get_fiscal_profile", "Perfil fiscal del receptor (RFC, régimen, email) para facturar.",
   {}, [], get_fiscal_profile)
_t("prepare_invoice_request",
   "Payload real para el Browser Agent (spec #19). El envío requiere "
   "confirmación humana vía POST /api/tickets/{id}/confirm, no este tool.",
   {"extraction": _EXTRACTION_OBJ, "uso_cfdi": _STR},
   ["extraction", "uso_cfdi"], prepare_invoice_request)


def as_tool_defs() -> list[ToolDef]:
    return [ToolDef(t["name"], t["description"], t["parameters"]) for t in TOOLS]


def execute(name: str, args: dict):
    for t in TOOLS:
        if t["name"] == name:
            return t["fn"](**(args or {}))
    raise ValueError(f"tool inexistente: {name}")
