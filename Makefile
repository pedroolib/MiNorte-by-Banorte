.PHONY: dev dev-api dev-web test test-api typecheck-web build-web

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
