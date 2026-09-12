"""Hermeticidad de la suite: los tests de valores exactos corren contra el
seed local (CSV/XML commiteados), NUNCA contra el contenido vivo del DB.

Sin esto, cargar el piloto (u otro dataset) rompería tests que afirman
totales del demo ficticio. Los tests live/integración usan skipif aparte.
"""

import os

os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_ANON_KEY"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
# Dataset demo fijo: la suite no depende del COMPANY_ID del .env local
# (que apunta al piloto) ni del contenido vivo del DB.
os.environ["COMPANY_ID"] = "company_001"
