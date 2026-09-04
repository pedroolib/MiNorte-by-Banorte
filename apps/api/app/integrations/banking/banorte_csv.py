"""Loader del seed Banorte en CSV espejo → contratos Transaction.

El CSV espejo imita lo que devolvería una API interna Banorte
(columnas normalizadas, sin layout de PDF). Lo genera
scripts/build_seed_from_pdf.py a partir de estados reales anonimizados.

También expone clasificar(): categorización heurística por descripción,
reutilizable cuando el importador de PDF sea producto (T1b).
"""

from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from app.schemas.transaction import Transaction


def clasificar(descripcion: str) -> str:
    """Categoría heurística a partir de la descripción Banorte."""
    d = descripcion.upper()
    if "TRASPASO INTERNO" in d:
        return "traspaso_interno"
    if "TRASPASO A CUENTA DE TERCEROS" in d:
        return "traspaso_terceros"
    if "SPEI RECIBIDO" in d:
        return "spei_recibido"
    if "COMPRA ORDEN DE PAGO SPEI" in d:
        return "spei_enviado"
    if "DEV.SPEI" in d or "MOT DEV:" in d:
        return "devolucion"
    if "PAGO REFERENCIADO" in d and "IMPUESTO" in d:
        return "impuestos"
    if "LDC-IMSS" in d or ("IMSS" in d and "PAGO DE" in d):
        return "imss"
    if "NOMINA" in d:
        return "nomina"
    if "DOMICILIACION" in d:
        return "domiciliacion"
    if "COMISION" in d:
        return "comision"
    if "I.V.A." in d or "IVA MEMBRESIA" in d or "IVA " in d:
        return "iva_comision"
    if "MEMBRESIA" in d:
        return "comision"
    if any(k in d for k in ("MERPAGO", "MERCADO PAGO", "PAYPAL", "TELMEX",
                            "TIEMPO AIRE", "GASOL", "SUPER", "COSTCO", "OXXO",
                            "APPLE", "DHL", "SEGUROS", "TELCEL", "COMPRA")):
        return "tarjeta" if any(k in d for k in ("MERPAGO", "MERCADO PAGO",
            "PAYPAL", "TIEMPO AIRE", "GASOL", "SUPER", "COSTCO", "OXXO",
            "APPLE", "COMPRA")) else "servicios"
    return "otro"


def cargar_csv(ruta: Path, company_id: str = "company_001") -> list[Transaction]:
    """Lee seed/transactions.csv y devuelve Transactions validados."""
    txns: list[Transaction] = []
    with open(ruta, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            dep = Decimal(row["deposito"] or "0")
            ret = Decimal(row["retiro"] or "0")
            # Flujo neto firmado: las devoluciones vienen como retiro
            # negativo (el banco devuelve dinero) y son ingreso neto.
            neto = dep - ret
            if neto == 0:
                continue  # fila informativa sin flujo (no debería pasar)
            tipo = "ingreso" if neto > 0 else "egreso"
            desc = row["descripcion"]
            merch = row.get("comercio") or "DESCONOCIDO"
            cat = row.get("categoria") or clasificar(desc)
            txns.append(Transaction(
                id=row["id"],
                company_id=company_id,
                account_id=row.get("account_id") or "acc_eje_001",
                amount=abs(neto),
                currency="MXN",
                date=datetime.fromisoformat(row["fecha"]),
                description=desc,
                merchant_name=merch,
                merchant_rfc=row.get("rfc") or None,
                type=tipo,
                balance=Decimal(row["saldo"]) if row.get("saldo") else None,
                source="banorte_mock",
                es_interno=row.get("es_interno") == "1",
                categoria=cat,
                rubro=rubro_inicial(desc, merch, cat, tipo),
            ))
    return txns


def rubro_inicial(desc: str, merchant: str, categoria: str, tipo: str) -> str:
    """Rubro sin CFDI (el back-fill de compute lo refina con ClaveProdServ)."""
    from app.financial.categorias import clasificar_rubro

    return clasificar_rubro(desc, merchant, categoria, None, tipo)
