#!/usr/bin/env python3
"""Genera seed/transactions.csv desde estados Banorte reales anonimizados.

Uso:
    uv run --project apps/api python scripts/build_seed_from_pdf.py

Lee seed/private/enlace_versatil_2023.pdf (PII, gitignored), toma los meses
ENE-MAR 2023 de la cuenta Enlace, los anonimiza (nombres, RFC, CLABE, cuentas,
tarjetas y teléfonos ficticios; MONTOS Y PATRONES REALES) y los desplaza a
JUN-AGO 2026. Valida que los totales mensuales cuadren al centavo.

Reglas de anonimización (una sola vía, nada real va al repo):
- CAFÉ NORTEÑO SA DE CV / CNM160812AB1 como empresa propia.
- Terceros mapeados 1:1 a ficticios estables (mismo real → mismo ficticio).
- Referencias/rastreos/PO se conservan (no son PII, dan realismo).
"""

from __future__ import annotations

import csv
import calendar
import random
import re
import sys
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))

from app.integrations.banking import banorte_pdf as bp  # noqa: E402
from app.integrations.banking.banorte_csv import clasificar  # noqa: E402

PDF = REPO / "seed" / "private" / "enlace_versatil_2023.pdf"
OUT = REPO / "seed" / "transactions.csv"

EMPRESA = "CAFE NORTENO SA DE CV"
RFC_PROPIO = "CNM160812AB1"
CLABE_PROPIA_BANORTE = "012580001234567890"
CUENTA_PROPIA = "1034567890"

# Mes real -> mes demo (mismo día, año 2026)
MES = {1: 6, 2: 7, 3: 8}
ANIO = 2026

# Totales reales de validación (dep exacto; ret incluye comisiones+IVA
# que el banco reporta por separado en el resumen).
ESPERADO = {
    6: ("323494.19", "335370.77"),
    7: ("300638.30", "314579.70"),
    8: ("421664.79", "430102.07"),
}

RFC_RE = re.compile(r"(?<![A-Z0-9])([A-ZÑ&]{3,4})\s?(\d{6})([A-Z0-9]{3})(?![A-Z0-9])")

# Pools ficticios (formato válido, contenido inventado)
CLIENTES = [  # (nombre, rfc) — receptores de SPEI
    ("CONSTRUCTORA VIA NORTE SA DE CV", "CVN190830M83"),
    ("DISTRIBUIDORA DEL NORTE SA DE CV", "DNO200415KX1"),
    ("COMERCIALIZADORA DEL BAJIO SA DE CV", "CBA170221B46"),
    ("TRANSPORTES DEL PACIFICO SA DE CV", "TPA180317G71"),
    ("MAQUINARIA INDUSTRIAL DEL NORTE SA DE CV", "MIN160126X07"),
    ("LOGISTICA Y ACEROS DEL CENTRO SA DE CV", "LOG090317G72"),
    ("INSUMOS Y REFACCIONES DEL VALLE SA DE CV", "IRV160126X07"),
    ("GRUPO COMERCIAL ORIENTE SA DE CV", "GCO180101AB1"),
]
PERSONAS = [  # beneficiarios físicos
    "FRANCISCO J. MORALES", "GUADALUPE PEREZ", "ARMANDO MORALES",
    "ISAAC R. LUNA", "ELISA MENDEZ", "MARTIN MEDINA", "ANDRES M. DIEZ",
    "JORGE L. CAMPOS", "MARIA F. SOTO", "CARLOS R. VEGA", "LUCIA FERNANDEZ",
    "PEDRO A. RUIZ", "SOFIA HERNANDEZ", "DIEGO TORRES", "ANA L. MENDOZA",
]
RFCS_PERSONA = [
    "MEJF800101AB1", "PEGL850309CD2", "MOPA791027EF3", "MERE850922GH4",
    "LUCI920425IJ5", "MEDA950619KL6", "CENP050211MN7", "BALR810513OP8",
    "FFRJ810330QR9", "INFJ891031ST1", "VLEJ060918UV2", "PFLJ860506WX3",
    "GALA890228YZ4", "VCOJ160727AB5", "DCEJ960513CD6", "PEMJ810623EF7",
]
RFCS_COMERCIO = [  # comercios con tarjeta
    "SUN850309AA1", "GAS070423BB2", "GAS061031CC3", "SUP810525DD4",
    "MER210503EE5", "MER991006FF6", "PAY150323GG7", "APP920820HH8",
    "DHL880115II9", "SEG971124JJ1", "COS910715KK2", "TEL670000LL3",
]
COMERCIOS_KEYWORD = [  # (regex, reemplazo)
    (r"SUPER MANUEL", "SUPER LA CANASTA"),
    (r"GASOL ARANDI|GASOL PABA LA PLATANER", "GASOL SANTA FE"),
    (r"LEY EXPRESS AGUARUTO I", "SUPER EXPRESS AVIACION"),
    (r"REFAC EL CHAPO", "REFACCIONES EL FARO"),
    (r"JUGUET CASA STORE", "JUGUETERIA LUDOTECA"),
    (r"POTENCIA FLUIDA SA DE C", "POTENCIA HIDRAULICA DEL NORTE SA DE CV"),
    (r"PREMIER FARNELL MEXICO", "ELECTRONICA INDUSTRIAL MX"),
    (r"NEWARK ELEMENT 14", "ELECTRONICA INDUSTRIAL MX"),
    (r"VOLKSWAGEN LEASING", "ARRENDADORA DE AUTOS DEL BAJIO"),
    (r"SEGUROS BANORTE", "SEGUROS DEL NORTE"),
    (r"UPS SERVICIOS DE MEXICO", "PAQUETERIA EXPRESS DEL NORTE"),
]
RFC_BANCO = "BNO930209CC1"
# Todos los RFC ficticios: el reemplazo suelto (paso 9) nunca los toca.
FICTICIOS = (
    {RFC_PROPIO, RFC_BANCO}
    | {rfc for _, rfc in CLIENTES}
    | set(RFCS_PERSONA)
    | set(RFCS_COMERCIO)
)


class Anonimizador:
    def __init__(self) -> None:
        self.rng = random.Random(42)
        self.map_rfc: dict[str, str] = {}
        self.map_txt: dict[str, str] = {}
        self.map_dig: dict[str, str] = {}
        self._i_cli = self._i_per = self._i_com = self._i_rfcp = 0

    # -- mapeos estables 1:1 --
    def rfc_cliente(self, real: str) -> str:
        if real not in self.map_rfc:
            nombre, rfc = CLIENTES[self._i_cli % len(CLIENTES)]
            self._i_cli += 1
            self.map_rfc[real] = rfc
            self.map_txt.setdefault(f"__CLI_{real}", nombre)
        return self.map_rfc[real]

    def rfc_persona(self, real: str) -> str:
        if real not in self.map_rfc:
            self.map_rfc[real] = RFCS_PERSONA[self._i_rfcp % len(RFCS_PERSONA)]
            self._i_rfcp += 1
        return self.map_rfc[real]

    def rfc_comercio(self, real: str) -> str:
        if real not in self.map_rfc:
            self.map_rfc[real] = RFCS_COMERCIO[self._i_com % len(RFCS_COMERCIO)]
            self._i_com += 1
        return self.map_rfc[real]

    def persona(self, real: str) -> str:
        real = real.strip()
        if real not in self.map_txt:
            self.map_txt[real] = PERSONAS[self._i_per % len(PERSONAS)]
            self._i_per += 1
        return self.map_txt[real]

    def digitos(self, real: str, prefijo: int = 0) -> str:
        """CLABE/cuenta/tarjeta/teléfono -> ficticios misma longitud.

        prefijo conserva los primeros N dígitos (ej. código de banco
        en CLABEs de 18).
        """
        if real not in self.map_dig:
            self.map_dig[real] = real[:prefijo] + "".join(
                str(self.rng.randint(0, 9)) for _ in range(len(real) - prefijo)
            )
        return self.map_dig[real]

    # -- pasadas sobre el texto --
    def anonimizar(self, desc: str) -> str:
        d = desc
        # 1. empresa propia ("INDUSTRIAL ES HMM" y "INDUSTRIALES HMM")
        d = re.sub(r"SERVICIOS INDUSTRIAL(?:ES)?(?: ES)?(?: HMM)?(?: SA DE CV)?",
                   EMPRESA, d)
        d = d.replace("SIH1311152C0", RFC_PROPIO)
        d = d.replace("012680001953072013", CLABE_PROPIA_BANORTE)
        d = re.sub(r"\b0211807410\b", CUENTA_PROPIA, d)
        # 2. comercios por keyword (antes de tocar RFCs sueltos)
        for pat, rep in COMERCIOS_KEYWORD:
            d = re.sub(pat, rep, d)
        # 3. CLIENTE ... DE LA CLABE ... CON RFC ... (SPEI recibido)
        def _cli(m: re.Match) -> str:
            nombre, clabe, rfc = m.group(1), m.group(2), m.group(3).replace(" ", "")
            if rfc == RFC_PROPIO or "TRASPASO INTERNO" in d.upper():
                return (f"CLIENTE {EMPRESA} DE LA CLABE {CLABE_PROPIA_BANORTE} "
                        f"CON RFC {RFC_PROPIO}")
            if re.search(r"\bS\.?A\.?( DE C\.?V\.?)?\b", nombre):
                rfc_f = self.rfc_cliente(rfc)
                nom_f = self.map_txt[f"__CLI_{rfc}"]
            else:  # cliente persona física
                rfc_f = self.rfc_persona(rfc)
                nom_f = self.persona(nombre.title())
            return f"CLIENTE {nom_f} DE LA CLABE {self.digitos(clabe, 3)} CON RFC {rfc_f}"
        d = re.sub(r"CLIENTE (.+?) DE LA CLABE (\d{16,18}) CON RFC ([A-Z0-9]{12,13})(?![A-Z0-9])",
                   _cli, d)
        # 4. BENEF:xxx (DATO NO VERIF...) (SPEI enviado a personas)
        def _ben(m: re.Match) -> str:
            nom = m.group(1).strip()
            if nom.upper().startswith("CONTADO"):
                return "BENEF:Mostrador (DATO NO VERIF POR ESTA INST)"
            return f"BENEF:{self.persona(nom)} (DATO NO VERIF POR ESTA INST)"
        d = re.sub(r"BENEF:([^(]+?)\s*\(DATO NO VERIF POR ESTA INST\)", _ben, d)
        # 5. AL R.F.C. XXXXXXXXX (traspasos a terceros)
        def _alrfc(m: re.Match) -> str:
            return f"AL R.F.C. {self.rfc_persona(m.group(1))}"
        d = re.sub(r"AL R\.F\.C\. ([A-Z0-9]{12,13})", _alrfc, d)
        # 6. A LA CUENTA: NNNNNNNNNN (10 dígitos)
        def _cta(m: re.Match) -> str:
            return f"A LA CUENTA: {self.digitos(m.group(1))}"
        d = re.sub(r"A LA CUENTA: (\d{10})\b", _cta, d)
        # 7. CTA/CLABE: 16 dígitos / CLABE 18 dígitos restantes
        # (en CLABEs se conserva el código de banco: 012 BBVA, 072 Banorte…)
        d = re.sub(r"\b(\d{3})\d{15}\b", lambda m: self.digitos(m.group(), 3), d)
        d = re.sub(r"\b\d{16}\b", lambda m: self.digitos(m.group()), d)
        # 8. tarjetas 493172... ya cubiertas por (7); teléfonos TELCEL 66XXXXXXXX
        d = re.sub(r"\b(66\d{8})\b", lambda m: "667" + self.digitos(m.group()[3:]), d)
        # 9. RFCs sueltos restantes -> según contexto (con fronteras estrictas
        # para no comer "TERCEROS 0000020123", "CLABE 0120...", "MBAN010023...")
        def _rfc(m: re.Match) -> str:
            real = m.group().replace(" ", "")
            if real in FICTICIOS or real in self.map_rfc.values():
                return m.group()  # ya ficticio: no tocar
            if real in self.map_rfc:
                return self.map_rfc[real]
            if real == "BMN930209927":
                self.map_rfc[real] = RFC_BANCO
                return RFC_BANCO
            # heurística: tarjeta/comercio
            return self.rfc_comercio(real)
        d = RFC_RE.sub(lambda m: _rfc(m), d)
        return re.sub(r"\s+", " ", d).strip()


def extraer_comercio_y_rfc(desc: str) -> tuple[str, str]:
    """Comercio y RFC desde la descripción ya anonimizada."""
    m = re.search(r"CLIENTE (.+?) DE LA CLABE", desc)
    if m:
        r = re.search(r"CON RFC ([A-Z0-9]{12,13})", desc)
        return m.group(1).strip(), (r.group(1) if r else "")
    m = re.search(r"BENEF:(.+?) \(DATO", desc)
    if m:
        r = re.search(r"RFC: ([A-Z0-9]{12,13}|ND)", desc)
        rfc = r.group(1) if r and r.group(1) != "ND" else ""
        return m.group(1).strip(), rfc
    m = re.search(r"AL R\.F\.C\. ([A-Z0-9]{12,13})", desc)
    if m:
        return "TERCERO " + m.group(1)[:6], m.group(1)
    m = re.search(r"LEYENDA: (.+?) (?:REF|CVE)", desc)
    if m:
        r = re.search(r"RFC[:\s]+([A-Z0-9]{12,13})", desc)
        return m.group(1).strip()[:40], (r.group(1) if r else "")
    m = re.search(r"^(.+?) RFC[:\s]", desc)
    if m and len(m.group(1)) < 45:
        r = re.search(r"RFC[:\s]+([A-Z0-9]{12,13})", desc)
        return m.group(1).strip(), (r.group(1) if r else "")
    if "PAGO REFERENCIADO" in desc:
        return "PAGO DE IMPUESTOS", ""
    if "IMSS" in desc:
        return "IMSS", ""
    if "COMISION" in desc or "I.V.A." in desc or "MEMBRESIA" in desc:
        return "BANORTE", RFC_BANCO
    return desc[:40].strip(), ""


def main() -> None:
    movs = bp.parsear_texto(bp.extraer_texto(PDF), cuentas={"0211807410"})
    bp.resolver_ambiguos(movs)
    errores = bp.validar_cadena(movs)
    assert not errores, errores[:5]

    anon = Anonimizador()
    filas: list[dict] = []
    seq = 0
    for m in movs:
        if m.es_saldo_anterior or m.fecha.month not in MES:
            continue
        mes = MES[m.fecha.month]
        # ENE 31 -> JUN 31 no existe: se recorta al fin de mes
        dia = min(m.fecha.day, calendar.monthrange(ANIO, mes)[1])
        seq += 1
        desc = anon.anonimizar(m.descripcion)
        comercio, rfc = extraer_comercio_y_rfc(desc)
        filas.append({
            "id": f"txn_2026{mes:02d}{seq:04d}",
            "company_id": "company_001",
            "account_id": "acc_eje_001",
            "fecha": f"{ANIO}-{mes:02d}-{dia:02d}T12:00:00-06:00",
            "descripcion": desc,
            "comercio": comercio,
            "rfc": rfc,
            "tipo": "ingreso" if m.deposito > 0 else "egreso",
            "deposito": str(m.deposito),
            "retiro": str(m.retiro),
            "saldo": str(m.saldo),
            "es_interno": "1" if "TRASPASO INTERNO" in desc.upper() else "0",
            "categoria": clasificar(desc),
        })

    # validación: totales mensuales idénticos a los reales
    for mes, (dep_esp, ret_esp) in ESPERADO.items():
        fm = [f for f in filas if f["fecha"][5:7] == f"{mes:02d}"]
        dep = sum((Decimal(f["deposito"]) for f in fm), Decimal("0"))
        ret = sum((Decimal(f["retiro"]) for f in fm), Decimal("0"))
        assert str(dep) == dep_esp, (mes, dep, dep_esp)
        assert str(ret) == ret_esp, (mes, ret, ret_esp)
        print(f"mes {mes}: {len(fm)} movs dep={dep} ret={ret} OK")

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    print(f"escrito {OUT} ({len(filas)} filas)")

    # reporte de categorías + PII sanity (ningún RFC/nombre real debe sobrevivir)
    reales = ["MUL971030M83", "SERVICIOS INDUSTRIAL", "SIH1311152C0",
              "012680001953072013", "0211807410", "Francisc", "Lupita",
              "SUPER MANUEL", "RUMJ8503097J4", "GASOL ARANDI"]
    texto = OUT.read_text(encoding="utf-8")
    for r in reales:
        assert r not in texto, f"PII sobrevivió: {r}"
    print("PII check OK")


if __name__ == "__main__":
    main()
