.PHONY: install dev test lint typecheck build clean fmt bench e2e

install:
	pip install -e ".[dev]"

dev:
	docker-compose up -d
	uvicorn epochix.server.app:create_app --factory --reload --port 7860

test:
	pytest -q

lint:
	ruff check src tests
	ruff format --check src tests

fmt:
	ruff format src tests
	ruff check --fix src tests

typecheck:
	mypy --strict src/epochix

bench:
	pytest tests/benchmarks --benchmark-only --benchmark-sort=mean

e2e:
	playwright test tests/e2e

build-frontend:
	cd frontend && npm ci && npm run build
	rm -rf src/epochix/_frontend/dist
	cp -r frontend/dist src/epochix/_frontend/dist

build:
	make build-frontend
	pip install build
	python -m build

build-vsix:
	cd epochix-vscode && npm ci && npm run package

clean:
	rm -rf dist build .pytest_cache .mypy_cache __pycache__
	find src -name "*.pyc" -delete
	find src -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

prune-db:
	epochix prune --older-than 30d

smoke:
	epochix demo/pytorch_lightning.log --headless
