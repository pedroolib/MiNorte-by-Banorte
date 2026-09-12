"""Contrato UI: doc = tipos = registry = fixtures (anti-drift).

Si agregas una tarjeta y no actualizas los 4 lados, esto falla.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TYPES = REPO / "apps/web/lib/ui-schema.ts"
REGISTRY = REPO / "apps/web/components/registry.tsx"
FIXTURES = REPO / "apps/web/lib/catalog-fixtures.ts"
DOC = REPO / "docs/ui-schema.md"


def _read(path: Path) -> str:
    assert path.exists(), f"falta {path}"
    return path.read_text(encoding="utf-8")


def test_catalogo_congelado_en_4_lados():
    tipos = set(re.findall(r'component:\s*"([a-z_]+)"', _read(TYPES)))
    registro = set(re.findall(r"(?m)^  ([a-z_]+): [A-Z]", _read(REGISTRY)))
    fixtures = set(re.findall(r'component:\s*"([a-z_]+)"', _read(FIXTURES)))
    doc = set(re.findall(r"(?m)^\| `([a-z_]+)`", _read(DOC))) - {"component"}

    assert len(tipos) >= 13, f"catálogo incompleto: {sorted(tipos)}"
    assert registro == tipos, f"registry difiere de tipos: {sorted(registro ^ tipos)}"
    assert fixtures == tipos, f"fixtures sin cubrir: {sorted(tipos - fixtures)}"
    assert doc == tipos, f"doc desactualizado: {sorted(doc ^ tipos)}"


def test_fixtures_con_props():
    src = _read(FIXTURES)
    for name in re.findall(r'component:\s*"([a-z_]+)"', _read(TYPES)):
        assert src.count(f'component: "{name}"') == 1, name
