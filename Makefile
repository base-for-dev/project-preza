# Every command needed to work on the project; `make help` lists them.
.DEFAULT_GOAL := help

setup: ## install everything and create .env
	pnpm install
	uv sync
	@test -f .env || cp .env.example .env
	@echo "Now put your inference key into .env"

start: ## API on :8000 and web on :3000 (next free port if busy)
	bash scripts/dev.sh

test: ## every Python test
	uv run pytest

lint: ## Python lint + format check, and the web type check
	uvx ruff check .
	uvx ruff format --check .
	pnpm lint

check: lint test ## what CI runs

submission: ## 3 templates x 3 layout variants into submission/ (needs `make start` running)
	uv run python evals/build_submission.py

skills-lock: ## record skill versions after you bumped one
	uv run python scripts/lock_skills.py

help: ## this list
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-12s %s\n", $$1, $$2}'

.PHONY: setup start test lint check submission skills-lock help
