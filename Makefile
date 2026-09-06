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

# ---- Piloto (datos reales en seed/private/, jamás en git) ----
PILOTO_DIR = seed/private/piloto
PILOTO_COMPANY = company_pilot

pilot-csv:
	uv run --project apps/api python scripts/build_pilot_bbva.py \
	  --pdf "$(PILOTO_DIR)/chequera_jul2026.pdf" \
	  --cuenta acc_bbva_001 --company $(PILOTO_COMPANY) --year 2026 \
	  --saldo-inicial 463711.92 \
	  --out "$(PILOTO_DIR)/transactions_jul2026.csv" \
	  --expect "$(PILOTO_DIR)/esperado.json"

pilot-tdc-csv:
	uv run --project apps/api python scripts/build_pilot_tdc.py \
	  --xlsx "$(PILOTO_DIR)/BBVA TDC 6159 MOV JULIO 2026.xlsx" \
	  --cuenta acc_tdc_001 --company $(PILOTO_COMPANY) --year 2026 --month 7 \
	  --chequera-csv "$(PILOTO_DIR)/transactions_jul2026.csv" \
	  --out "$(PILOTO_DIR)/transactions_tdc_jul2026.csv"

pilot-tdc-load:
	uv run --project apps/api python scripts/load_pilot_tdc.py \
	  --csv "$(PILOTO_DIR)/transactions_tdc_jul2026.csv" \
	  --company $(PILOTO_COMPANY) --cuenta acc_tdc_001 \
	  --alias "TDC BBVA 6159" \
	  --expect-compras 106118.85 --expect-abonos 114860.63

pilot-cfdis:
	uv run --project apps/api python scripts/build_pilot_cfdis.py \
	  --csv "$(PILOTO_DIR)/transactions_jul2026.csv" \
	  --outdir "$(PILOTO_DIR)/cfdis" \
	  --company $(PILOTO_COMPANY) \
	  --emisor-rfc PIGP000101AB1 --emisor-nombre "PEDRO PISTONES GARCIA" \
	  --emisor-regimen 612 --cp 21000 --serie PILOTO \
	  --unpaid-n 5 --unpaid-seed 42

pilot-load:
	COMPANY_ID=$(PILOTO_COMPANY) uv run --project apps/api python scripts/load_seed.py \
	  --company $(PILOTO_COMPANY) \
	  --company-json "$(PILOTO_DIR)/IDENTIDAD.json" \
	  --accounts-json "$(PILOTO_DIR)/IDENTIDAD.json" \
	  --csv "$(PILOTO_DIR)/transactions_jul2026.csv" \
	  --cfdis-dir "$(PILOTO_DIR)/cfdis" \
	  --profile-json "$(PILOTO_DIR)/IDENTIDAD.json" \
	  --expect "$(PILOTO_DIR)/esperado_pilot.json"

# uso: make pilot-wipe COMPANY=company_001            -> dry-run (solo muestra)
#      make pilot-wipe COMPANY=company_001 CONFIRM=--confirm -> borra de verdad
pilot-wipe:
	uv run --project apps/api python scripts/wipe_company.py --company $(COMPANY) $(CONFIRM)

# Calcula y persiste matches, CxC, snapshots y alertas (requiere 003).
# --all para los 3 meses (default: último mes).
compute:
	uv run --project apps/api python scripts/compute_financials.py --all

db-test:
	uv run --project apps/api --with pytest --with httpx pytest apps/api/tests/test_supabase_repo.py -q
