.PHONY: venv packages
venv:
	python3.12 -m venv .venv
packages:
	pip install --upgrade pip
	pip freeze | grep '^web-' | sed 's/ @.*//' | xargs -r pip uninstall -y
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

.PHONY: format format_py format_html
format: format_py format_html
format_py:
	ruff check . --fix
	ruff format .
format_html:
	djlint . --reformat

.PHONY: lint lint_py lint_html
lint: lint_py lint_html
lint_py:
	ruff check .
	ruff format . --check
	mypy --install-types --non-interactive .
lint_html:
	djlint . --check

.PHONY: test
test:
	pytest --maxfail=1 --verbose