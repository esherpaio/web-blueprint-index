.PHONY: commit
commit:
	git rev-parse --short HEAD

.PHONY: venv packages
venv:
	python3.12 -m venv .venv
packages:
	pip install --upgrade pip
	pip freeze | grep '^web-' | sed 's/ @.*//' | xargs -r pip uninstall -y
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

.PHONY: format format-py
format: format-py
format-py:
	ruff check . --fix
	ruff format .

.PHONY: lint lint-py
lint: lint-py
lint-py:
	ruff check .
	ruff format . --check
	mypy --install-types --non-interactive .

.PHONY: test
test:
	pytest --maxfail=1 --verbose
