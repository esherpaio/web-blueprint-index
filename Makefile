# ACTIVATE
.PHONY: activate
activate:
	python3 -m venv .venv
	@echo "Run 'source .venv/bin/activate' manually"

# REQUIREMENTS
.PHONY: requirements
requirements:
	pip install --upgrade pip
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

# DATABASE
.PHONY: migrations migrate
migrations:
	alembic check || alembic revision --autogenerate -m ""
migrate:
	alembic upgrade head

# FORMATTING
.PHONY: format format_py format_html
format: format_py format_html
format_py:
	ruff check . --fix
	ruff format .
format_html:
	djlint . --reformat

# LINTING
.PHONY: lint lint_py lint_html
lint: lint_py lint_html
lint_py:
	ruff check .
	ruff format . --check
	mypy --install-types --non-interactive .
lint_html:
	djlint . --check

# TESTING
.PHONY: test
test:
	pytest .