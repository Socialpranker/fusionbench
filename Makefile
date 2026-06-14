.PHONY: install test run search site all check

install:
	pip install -e ".[dev]"

test:
	pytest -q

run:
	python scripts/run_v0.py --mock --limit 100 --out runs/catalog.jsonl

search:
	python scripts/run_search.py --mock --limit 90 --out runs/catalog_search.jsonl

site:
	python scripts/build_catalog.py --runs "runs/*.jsonl" --out site/index.html

check:
	python scripts/check_setup.py

all: run site
