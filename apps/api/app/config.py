"""Config central (T0). No truena si faltan keys de Supabase/OpenAI/Resend.

En T0 solo verificamos que el esqueleto levanta. La conexión real a
Supabase se valida en T2.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "MiNorte API"
    ENV: str = "local"
    API_PORT: int = 8000
    TZ: str = "America/Mexico_City"

    # Single-company demo (sin auth en T0). TODO(auth): reemplazar
    # get_current_company() por Supabase Auth cuando se necesite.
    COMPANY_ID: str = "company_001"

    # Supabase cloud (solo placeholders en T0, se usa en T2)
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # IA / Email (se usan en T8-T9, solo placeholders en T0)
    OPENAI_API_KEY: str = ""
    OPENAI_REASONING_MODEL: str = "gpt-6-astra"  # Consultor/Analista
    OPENAI_FAST_MODEL: str = "gpt-5.6-sol"  # loops operativos
    # Modelo para tool-calling (algunos reasoning no aceptan function
    # tools en chat/completions). None = usa FAST_MODEL.
    OPENAI_TOOL_MODEL: str | None = None
    # API para tool-calling: "chat" (chat/completions) o "responses"
    # (/v1/responses, obligatorio para reasoning que rechaza tools en chat).
    OPENAI_TOOLS_API: str = "chat"
    # Vision (T-tickets): extracción de fotos de ticket. gpt-4o-mini es el
    # que se usa también en test_live_openai.py contra la API real.
    OPENAI_VISION_MODEL: str = "gpt-4o-mini"
    # Gemini (T-tickets, SOLO Vision + Browser Agent): alternativa a
    # OpenAI acotada a este flujo — no toca agents/llm.py (compartido con
    # Consultor/Analista/Diseñador). Vacío = sigue usando OpenAI.
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.6-flash"
    MAIL_PROVIDER: str = "log"  # log | resend
    RESEND_API_KEY: str = ""
    MAIL_FROM: str = ""  # ej. cobranza@tudominio.com (dominio verificado)


@lru_cache
def get_settings() -> Settings:
    return Settings()
