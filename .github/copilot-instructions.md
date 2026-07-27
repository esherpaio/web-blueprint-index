# GitHub Copilot Instructions

## What NOT to do automatically

Unless explicitly asked, never:

- **Format code** — do not run formatters (black, isort, prettier, etc.) or reformat existing code style
- **Lint code** — do not run linters or fix linting issues in code you did not change
- **Create unit tests** — do not generate test files or test cases for new or modified code
- **Create database migrations** — do not generate or run Alembic migrations for model changes
