"""QR del ticket -> URL (spec #3.3 caso 1): tickets sin URL legible como
texto, solo QR. Se prueba contra códigos QR reales generados en el momento
(determinista, sin depender de una foto real)."""

from __future__ import annotations

import io

import numpy as np
import pytest
import qrcode

from app.integrations.invoicing import qr as qr_mod


def _qr_png_bytes(payload: str) -> bytes:
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_decode_url_real_qr_con_https():
    b = _qr_png_bytes("https://www.wansoft.net/Peckers/FE.html")
    assert qr_mod.decode_url(b) == "https://www.wansoft.net/Peckers/FE.html"


def test_decode_url_real_qr_dominio_sin_protocolo():
    b = _qr_png_bytes("alsuper.com/facturacion")
    assert qr_mod.decode_url(b) == "alsuper.com/facturacion"


def test_decode_url_qr_sin_pinta_de_url_no_se_fuerza():
    """Un QR con solo un folio/código interno no es un portal: no se
    inventa ni se fuerza como si lo fuera."""
    b = _qr_png_bytes("FOLIO-45579-INTERNO")
    assert qr_mod.decode_url(b) is None


def test_decode_url_sin_qr_en_la_imagen():
    # imagen en blanco válida (PNG), sin ningún QR
    import cv2

    blank = np.full((200, 200, 3), 255, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", blank)
    assert ok
    assert qr_mod.decode_url(buf.tobytes()) is None


def test_decode_url_bytes_invalidos_no_truena():
    assert qr_mod.decode_url(b"no-es-una-imagen-de-verdad") is None
