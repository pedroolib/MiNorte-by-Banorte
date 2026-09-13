"""Reconciliación determinística Banorte vs CFDI (spec #17).

Score por pareja (mismo sentido: egreso↔recibido, ingreso↔emitido):
    score = monto*0.50 + fecha*0.20 + comercio*0.30
    >= 0.85 → auto | 0.60–0.85 → review | < 0.60 → unmatched

- monto: 1.0 si exacto, decae lineal (10% de diferencia → 0).
- fecha: 1.0 mismo día, decae a 0 en ±15 días (ventana cross-mes).
- comercio: RapidFuzz token_set_ratio sobre nombres normalizados.

Asignación en dos fases (determinista, sin IA):
- Fase 1: dentro de cada grupo (dirección, monto exacto), asignación
  óptima (húngaro) sobre el score. Evita que el greedy deje fuera al
  último de un cluster de montos iguales (cada uno con su CFDI gemelo).
- Fase 2: greedy clásico para el resto (montos aproximados).
Un CFDI se usa una sola vez. Sirve para detectar CxC (emitido sin cobro).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal

from rapidfuzz import fuzz

from app.schemas.cfdi import Cfdi
from app.schemas.match import Match
from app.schemas.receivable import Receivable
from app.schemas.transaction import Transaction

AUTO = Decimal("0.85")
REVIEW = Decimal("0.60")
VENTANA_DIAS = 15

# Categorías fuera de conciliación (sin CFDI por definición)
NO_CONCILIABLE = {"comision", "iva_comision", "impuestos"}

# Comercios que no identifican contraparte (no sirven para match por nombre)
GENERIC_MERCHANTS = ("DESCONOCIDO", "VENTAS TPV", "DEPOSITO DE TERCERO")


def _nombre_util(nombre: str) -> bool:
    n = (nombre or "").strip().upper()
    if len(n) < 4 or ":" in n:
        return False
    return not (n in GENERIC_MERCHANTS
                or n.startswith("COMPRA ORDEN DE PAGO SPEI"))


def es_conciliable(t: Transaction) -> bool:
    if t.es_interno or t.categoria in NO_CONCILIABLE:
        return False
    if t.type == "ingreso":
        # Todo cobro no-interno concilia (su emitido existe por construcción
        # en match-total; antes solo spei_recibido).
        return True
    if t.source == "bbva_mock":
        # BBVA no trae RFC: se concilia por nombre (verificado en piloto)
        return _nombre_util(t.merchant_name)
    return bool(t.merchant_rfc)


def _norm(s: str) -> str:
    s = s.upper()
    s = re.sub(r"\b(SA DE CV|S\.A\. DE C\.V\.|S DE RL|DE CV)\b", " ", s)
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9Ñ ]", " ", s)).strip()


def amount_score(a: Decimal, b: Decimal) -> Decimal:
    if a == b:
        return Decimal("1")
    base = max(abs(a), abs(b))
    if base == 0:
        return Decimal("1")
    dif = abs(a - b) / base
    return max(Decimal("0"), Decimal("1") - dif * 10)


def date_score(f1: datetime, f2: datetime) -> Decimal:
    dias = abs((f1.date() - f2.date()).days)
    if dias > VENTANA_DIAS:
        return Decimal("0")
    return Decimal("1") - Decimal(dias) / Decimal(VENTANA_DIAS)


def merchant_score(n1: str, n2: str) -> Decimal:
    if not n1 or not n2:
        return Decimal("0")
    return Decimal(fuzz.token_set_ratio(_norm(n1), _norm(n2))) / 100


def score(t: Transaction, c: Cfdi) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """(total, monto, fecha, comercio)."""
    if t.type == "ingreso":
        nombre = c.receptor_nombre
    else:
        nombre = c.emisor_nombre
    am = amount_score(t.amount, c.total)
    fe = date_score(t.date, c.fecha_emision)
    co = merchant_score(t.merchant_name, nombre)
    total = am * Decimal("0.50") + fe * Decimal("0.20") + co * Decimal("0.30")
    return total, am, fe, co


def _estado(total: Decimal) -> str:
    if total >= AUTO:
        return "auto"
    if total >= REVIEW:
        return "review"
    return "unmatched"


def _hungarian(weights: list[list[float]]) -> list[int]:
    """Asignación de peso máximo (filas→columnas). Devuelve por fila la
    columna asignada o -1. O(n³), determinista (empates → índice menor)."""
    n = len(weights)
    m = len(weights[0]) if n else 0
    size = max(n, m)
    if size == 0:
        return []
    a = [[0.0] * (size + 1) for _ in range(size + 1)]
    for i in range(n):
        for j in range(m):
            a[i + 1][j + 1] = weights[i][j]
    u = [0.0] * (size + 1)
    v = [0.0] * (size + 1)
    p = [0] * (size + 1)
    way = [0] * (size + 1)
    for i in range(1, size + 1):
        p[0] = i
        j0 = 0
        minv = [float("inf")] * (size + 1)
        used = [False] * (size + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = float("inf")
            j1 = 0
            for j in range(1, size + 1):
                if used[j]:
                    continue
                cur = -a[i0][j] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(size + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    asign = [-1] * n
    for j in range(1, size + 1):
        if p[j] and p[j] <= n and j <= m and a[p[j]][j] > 0:
            asign[p[j] - 1] = j - 1
    return asign


def _en_ventana(t: Transaction, c: Cfdi) -> bool:
    return abs((t.date.date() - c.fecha_emision.date()).days) <= VENTANA_DIAS


def conciliar(txns: list[Transaction], cfdis: list[Cfdi]) -> list[Match]:
    """Concilia movimientos conciliables. Un CFDI se asigna una sola vez."""
    usados: set[str] = set()
    matches: list[Match] = []
    pendientes: list[Transaction] = []

    def _match(t: Transaction, c: Cfdi) -> None:
        total, am, fe, co = score(t, c)
        usados.add(c.uuid)
        matches.append(Match(
            transaction_id=t.id, cfdi_id=c.uuid, score=total,
            amount_score=am, date_score=fe, merchant_score=co,
            status=_estado(total),
        ))

    def _sin_match(t: Transaction, mejor=None) -> None:
        matches.append(Match(
            transaction_id=t.id, cfdi_id=None,
            score=mejor[0] if mejor else Decimal("0"),
            amount_score=mejor[2] if mejor else Decimal("0"),
            date_score=mejor[3] if mejor else Decimal("0"),
            merchant_score=mejor[4] if mejor else Decimal("0"),
            status="unmatched",
        ))

    candidatos = sorted(
        [t for t in txns if es_conciliable(t)], key=lambda t: (t.date, t.id)
    )
    por_cfdi: dict[str, list[Cfdi]] = {}
    for c in sorted(cfdis, key=lambda c: (c.fecha_emision, c.uuid)):
        por_cfdi.setdefault(c.tipo, []).append(c)

    # Fase 1: grupos (dirección, monto exacto) con asignación óptima.
    # Incluye grupos de 1 (reclama su gemelo antes del greedy inexacto,
    # que ya no puede tocar pares exactos). Así ningún gemelo es robado.
    grupos: dict[tuple[str, Decimal], list[Transaction]] = {}
    for t in candidatos:
        direccion = "emitido" if t.type == "ingreso" else "recibido"
        grupos.setdefault((direccion, t.amount), []).append(t)
    resueltos: set[str] = set()
    for (direccion, monto) in sorted(grupos):
        ts = grupos[(direccion, monto)]
        cs = [c for c in por_cfdi.get(direccion, [])
              if c.uuid not in usados and c.total == monto]
        elegibles = [t for t in ts
                     if any(_en_ventana(t, c) for c in cs)]
        if elegibles and cs:
            w = [[float(score(t, c)[0]) if _en_ventana(t, c) else 0.0
                  for c in cs] for t in elegibles]
            for t, j in zip(elegibles, _hungarian(w)):
                resueltos.add(t.id)
                if j >= 0 and score(t, cs[j])[0] >= REVIEW:
                    _match(t, cs[j])
                else:
                    pendientes.append(t)
        pendientes.extend(t for t in ts if t.id not in resueltos)

    # Fase 2: greedy para el resto, primero los más restringidos
    # (menos CFDIs viables): evita que un gemelo único lo consuma otro
    # movimiento con más alternativas. Sub-pase A: solo montos exactos
    # (el gemelo es de su dueño); sub-pase B: aproximados.
    def _viables(t: Transaction) -> int:
        direccion = "emitido" if t.type == "ingreso" else "recibido"
        return sum(
            1 for c in por_cfdi.get(direccion, [])
            if c.uuid not in usados and _en_ventana(t, c)
            and amount_score(t.amount, c.total) > 0)

    def _tiene_gemelo(t: Transaction) -> bool:
        direccion = "emitido" if t.type == "ingreso" else "recibido"
        return any(c.uuid not in usados and _en_ventana(t, c)
                   and c.total == t.amount
                   for c in por_cfdi.get(direccion, []))

    def _greedy(ts: list[Transaction], solo_exactos: bool) -> None:
        for t in sorted(ts, key=lambda t: (_viables(t), t.date, t.id)):
            direccion = "emitido" if t.type == "ingreso" else "recibido"
            mejor = None  # (total, uuid, am, fe, co)
            for c in por_cfdi.get(direccion, []):
                if c.uuid in usados:
                    continue
                if not _en_ventana(t, c):
                    continue
                if solo_exactos and c.total != t.amount:
                    continue
                total, am, fe, co = score(t, c)
                if mejor is None or total > mejor[0]:
                    mejor = (total, c.uuid, am, fe, co)
            if mejor is None or mejor[0] < REVIEW:
                if solo_exactos:
                    resto.append(t)
                else:
                    _sin_match(t, mejor)
            else:
                total, cuuid, am, fe, co = mejor
                c = next(x for x in por_cfdi[direccion] if x.uuid == cuuid)
                _match(t, c)

    resto: list[Transaction] = []
    solo_exact = [t for t in pendientes if _tiene_gemelo(t)]
    _greedy(solo_exact, solo_exactos=True)
    _greedy(resto + [t for t in pendientes if not _tiene_gemelo(t)],
            solo_exactos=False)
    return matches


def detectar_cxc(cfdis: list[Cfdi], matches: list[Match],
                 company_id: str, dias_credito: int = 30) -> list[Receivable]:
    """Emitidos sin cobro conciliado -> cuentas por cobrar abiertas."""
    cobrados = {m.cfdi_id for m in matches if m.cfdi_id}
    recs: list[Receivable] = []
    for c in cfdis:
        if c.tipo != "emitido" or c.uuid in cobrados:
            continue
        recs.append(Receivable(
            id=f"ar_{c.uuid[:8].lower()}",
            company_id=company_id,
            cfdi_id=c.uuid,
            customer_name=c.receptor_nombre,
            customer_rfc=c.receptor_rfc,
            amount=c.total,
            amount_paid=Decimal("0"),
            issued_at=c.fecha_emision,
            due_date=(c.fecha_emision + timedelta(days=dias_credito)),
            status="open",
        ))
    return recs
