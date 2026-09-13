#!/usr/bin/env python3
"""Aplica renombres.json a los CSVs crudos -> CSVs finales (privado).

Renombra comercio (match exacto por clave de fusión) y descripcion
(reemplazo por substring, originales largos primero). Verifica que no
quede ningún nombre original en los CSVs finales.

Uso:
    uv run --project apps/api python scripts/aplicar_renombres.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

PILOTO = REPO / "seed/private/piloto"


def normaliza(c: str) -> str:
    c = re.sub(r"^\d+\s*DE\s*\d+\s+", "", c)
    c = re.sub(r"\s+A \d+ MESES.*$", "", c)
    c = re.sub(r"^\d+(INTERN\.PAGO TDC)$", r"\1", c)
    return re.sub(r"\s+", " ", c).strip()


def clave_fusion(c: str) -> str:
    k = c.upper()
    k = k.replace("CORPORATION", "CORP").replace("COMPANIA", "CIA").replace("COMPAÑIA", "CIA")
    k = re.sub(r"\bMEXICO\b", "MEX", k)
    k = re.sub(r"\b(SA|CV|S\.A\.|C\.V\.|SAS|RL|S DE RL|S\. DE R\.L\.|INC|LLC)\b\.?", "", k)
    k = re.sub(r"[^A-Z0-9 ]", "", k)
    return re.sub(r"\s+", " ", k).strip()


ALIAS_FUSION = {
    "MAXIMILIANO URIBE": "MAXIMILIANO URIBE REYES",
    "MAXIMIALNO URIBE REYES": "MAXIMILIANO URIBE REYES",
    "MARIA FERENANDA VALENZUELA VEGA": "MARIA FERNANDA VALENZUELA VEGA",
    "ELEMENT FLEET MANAGEMENT CORP MEX": "ELEMENT FLEET MANAGEMENT CORP MEXICO",
}


def main() -> None:
    mapa = json.loads((PILOTO / "renombres.json").read_text(encoding="utf-8"))
    # por_clave: clave fusion -> nuevo (resuelve alias igual que el generador)
    por_clave = {}
    for clave, v in mapa.items():
        por_clave[clave] = v["nuevo"]
    # reemplazos en descripcion: originales ordenados por largo desc
    subs: list[tuple[str, str]] = []
    vistos: set[str] = set()
    for clave, v in mapa.items():
        for o in v["originales"]:
            if o not in vistos:
                vistos.add(o)
                subs.append((o, v["nuevo"]))
    subs.sort(key=lambda t: -len(t[0]))

    funcionales = {o for clave, v in mapa.items()
                   if v["regla"] == "funcional" for o in v["originales"]}

    entradas = sorted(PILOTO.glob("transactions_ch_*.csv")) + sorted(
        PILOTO.glob("transactions_tdc_*.csv"))
    assert entradas, "sin CSVs crudos"
    total_filas = 0
    for src in entradas:
        rows = list(csv.DictReader(open(src, encoding="utf-8")))
        for r in rows:
            c = normaliza(r["comercio"])
            ck = ALIAS_FUSION.get(clave_fusion(c), clave_fusion(c))
            if ck not in por_clave:
                # funcional que no entró al mapa (VENTAS TPV etc.): intacto
                nuevo = None
            else:
                nuevo = por_clave[ck]
            if nuevo:
                r["comercio"] = nuevo
            desc = r["descripcion"]
            for o, n in subs:
                if o in desc:
                    desc = desc.replace(o, n)
            r["descripcion"] = desc
        dst = PILOTO / src.name.replace("transactions_", "transactions_final_")
        with open(dst, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        total_filas += len(rows)
        print(f"{dst.name}: {len(rows)} filas")

    # verificación: ningún original con PII en finales (salvo funcionales)
    pii = [o for clave, v in mapa.items() for o in v["originales"]
           if v["regla"] != "funcional" and len(o) >= 4]
    mal = []
    for dst in sorted(PILOTO.glob("transactions_final_*.csv")):
        texto = dst.read_text(encoding="utf-8")
        for o in pii:
            if o in texto:
                mal.append((dst.name, o))
    assert not mal, f"PII remanente: {mal[:10]}"
    print(f"OK: {total_filas} filas anonimizadas, 0 PII remanente "
          f"({len(pii)} patrones revisados)")


if __name__ == "__main__":
    main()
