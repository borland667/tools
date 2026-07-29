VENV ?= .venv
BIN := $(VENV)/bin
PYTHON_RUNNER := ./scripts/resolve_python.sh
VENV_CREATOR := ./scripts/create_venv.sh

.PHONY: help python-version venv install install-dev run dev test lint format typecheck check smoke clean

help:
	@printf "%s\n" \
	  "make python-version Show the project-selected Python interpreter" \
	  "make venv          Create or validate the virtual environment" \
	  "make install       Install runtime dependencies" \
	  "make install-dev   Install runtime and development dependencies" \
	  "make run           Run the router" \
	  "make dev           Run with auto-reload" \
	  "make test          Run tests" \
	  "make lint          Run Ruff checks" \
	  "make format        Format with Ruff" \
	  "make typecheck     Run mypy" \
	  "make check         Run compile, lint, tests, and type checking" \
	  "make smoke         Run API smoke tests against a running router" \
	  "make clean         Remove generated local files"

python-version:
	$(PYTHON_RUNNER) --version

venv:
	$(VENV_CREATOR) $(VENV)

install: venv
	$(BIN)/pip install -r requirements.txt

install-dev: venv
	$(BIN)/pip install -r requirements-dev.txt

run:
	$(BIN)/python omlx_auto_router.py

dev:
	ROUTER_RELOAD=true $(BIN)/python omlx_auto_router.py

test:
	$(BIN)/pytest

lint:
	$(BIN)/ruff check .

format:
	$(BIN)/ruff format .
	$(BIN)/ruff check --fix .

typecheck:
	$(BIN)/mypy omlx_auto_router.py

check:
	$(BIN)/python -m py_compile omlx_auto_router.py
	$(BIN)/ruff check .
	$(BIN)/pytest
	$(BIN)/mypy omlx_auto_router.py

smoke:
	./scripts/smoke_test.sh

clean:
	rm -rf $(VENV) __pycache__ .pytest_cache .mypy_cache .ruff_cache htmlcov dist build *.egg-info
