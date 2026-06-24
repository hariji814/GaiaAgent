.PHONY: install test test-cov lint format type-check serve demo \
       docker-build docker-up docker-down clean all

# ── Development ──────────────────────────────────────────────────

install:
	pip install -e ".[all]"

test:
	pytest -v --tb=short

test-cov:
	pytest --cov --cov-report=html

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

type-check:
	mypy src/

# ── Running ──────────────────────────────────────────────────────

serve:
	python -m gaiaagent.cli serve --dashboard

demo:
	python main.py

# ── Docker ───────────────────────────────────────────────────────

docker-build:
	docker build -t gaiaagent .

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

# ── Maintenance ──────────────────────────────────────────────────

clean:
	rm -rf build/ dist/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov coverage.xml

# ── Aggregate ────────────────────────────────────────────────────

all: lint type-check test
