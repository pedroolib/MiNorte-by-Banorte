.PHONY: dev dev-api dev-web test test-api typecheck-web build-web seed

dev:
	docker compose up --build

dev-api:
	uv run --project apps/api uvicorn app.main:app --reload --port 8000 --app-dir apps/api

dev-web:
	pnpm --dir apps/web dev

test:
	uv run --project apps/api --with pytest --with httpx pytest apps/api/tests -q

test-api:
	uv run --project apps/api --with pytest --with httpx pytest apps/api/tests -q

typecheck-web:
	pnpm --dir apps/web typecheck

build-web:
	pnpm --dir apps/web build

# Regenera seed/transactions.csv desde seed/private/*.pdf (PII local).
# Requiere poppler (pdftotext) y los PDFs en seed/private/.
seed:
	uv run --project apps/api --with httpx python scripts/build_seed_from_pdf.py

# Genera seed/cfdis/**/*.xml pareados con el banco (determinista).
cfdis:
	uv run --project apps/api --with httpx python scripts/build_seed_cfdis.py

# Carga el seed a Supabase (requiere 001/002 aplicados + .env).
# Idempotente: re-corrible sin duplicar.
db-load:
	uv run --project apps/api python scripts/load_seed.py

# Calcula y persiste matches, CxC, snapshots y alertas (requiere 003).
# --all para los 3 meses (default: último mes).
compute:
	uv run --project apps/api python scripts/compute_financials.py --all

db-test:
	uv run --project apps/api --with pytest --with httpx pytest apps/api/tests/test_supabase_repo.py -q
