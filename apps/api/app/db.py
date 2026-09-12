"""Cliente Supabase (PostgREST) con degradación elegante.

Sin credenciales (o sin red) devuelve None y la API usa el seed CSV local.
Así `pytest` y el dev local funcionan sin Supabase; en cuanto hay tablas
y datos, la API lee de Postgres sin cambiar código.
"""

from functools import lru_cache
from typing import Any

from app.config import get_settings


@lru_cache
def get_supabase() -> Any | None:
    s = get_settings()
    if not s.SUPABASE_URL:
        return None
    key = s.SUPABASE_SERVICE_ROLE_KEY or s.SUPABASE_ANON_KEY
    if not key:
        return None
    try:
        from supabase import create_client

        return create_client(s.SUPABASE_URL, key)
    except Exception:
        return None
