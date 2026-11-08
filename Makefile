.PHONY: setup dev test fetch eval export prod validate build up down obs k8s

PY=backend/.venv/bin/python

setup:            ## create venv and install the backend
	cd backend && uv venv -q .venv --python 3.12 && uv pip install -q --python .venv/bin/python -e ".[dev]"

dev:              ## API + UI on http://127.0.0.1:8000 (SQLite, in-process jobs)
	$(PY) -m cqa serve --port 8000

test:             ## unit tests: scoring engine, results contract, preprocessing
	cd backend && .venv/bin/python -m pytest -q

fetch:            ## make fetch GROUP=DEV
	$(PY) -m cqa fetch $(GROUP)

eval:             ## make eval GROUP=DEV
	$(PY) -m cqa evaluate $(GROUP) --parallel 4

export:           ## make export GROUP=DEV TARGET=dev
	$(PY) -m cqa export $(GROUP) $(TARGET)

prod:             ## control hour: make prod GROUP=<group_id>  (fetch → evaluate → results/prod/results.json)
	$(PY) -m cqa prod $(GROUP) --expect 10 --parallel 3

validate:         ## make validate FILE=results/prod/results.json EXPECT=10
	$(PY) -m cqa validate $(FILE) --expect $(EXPECT)

build:            ## docker image
	docker build -t cqa:latest .

up:               ## postgres + redis + api + 2 workers
	docker compose up -d --build

obs:              ## + prometheus + grafana
	docker compose --profile obs up -d

down:
	docker compose down

k8s:              ## render kubernetes manifests
	kubectl kustomize deploy/k8s
