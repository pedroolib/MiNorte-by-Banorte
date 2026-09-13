"""QR del ticket -> URL del portal de facturación (spec #3.3 caso 1).

Muchos tickets mexicanos solo imprimen el QR (sin URL legible como texto,
ej. "escanea el código para facturar"). Decodificar el QR es tan real
como leer un RFC impreso: no se inventa nada, se lee lo que ya está ahí.

Sin dependencias de sistema (zbar, etc.): usa el detector de QR incluido
en opencv-python-headless.
"""

from __future__ import annotations

import re

import numpy as np

_URL_RE = re.compile(r"^https?://", re.I)
_DOMAIN_RE = re.compile(r"^[\w.-]+\.[a-z]{2,}(/.*)?$", re.I)


def _looks_like_url(s: str) -> bool:
    s = s.strip()
    return bool(_URL_RE.match(s) or _DOMAIN_RE.match(s))


def decode_url(image_bytes: bytes) -> str | None:
    """Foto del ticket -> URL si algún QR de la imagen decodifica a una.

    None si no hay QR, no se pudo decodificar, o el contenido no parece
    una URL (ej. un QR con solo el folio: no lo forzamos como portal)."""
    import cv2

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None

    detector = cv2.QRCodeDetector()
    try:
        data, _, _ = detector.detectAndDecode(img)
    except Exception:
        data = ""
    candidates = [data] if data else []

    if not candidates:
        try:
            ok, decoded_info, _, _ = detector.detectAndDecodeMulti(img)
        except Exception:
            ok, decoded_info = False, ()
        if ok:
            candidates = [d for d in decoded_info if d]

    for candidate in candidates:
        if _looks_like_url(candidate):
            return candidate.strip()
    return None
