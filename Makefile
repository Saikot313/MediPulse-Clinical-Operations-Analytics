export PYTHONPATH := src
PY ?= python
.PHONY: install db build report test bi provision benchmark down
install: ; $(PY) -m pip install -r requirements.txt
db:      ; docker compose up -d postgres
build:   ; $(PY) -m medipulse build --visits 20000
report:  ; $(PY) -m medipulse report
test:    ; MEDIPULSE_TEST_URL=postgresql://warehouse:warehouse@localhost:5432/medipulse_test $(PY) -m pytest -q
bi:      ; docker compose --profile bi up -d
provision: ; $(PY) metabase/provision.py
benchmark: ; $(PY) -m medipulse benchmark --visits 300000
down:    ; docker compose --profile bi --profile tools down
