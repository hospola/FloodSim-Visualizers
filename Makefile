PYTHON ?= python3
VENV := .venv
VENV_PY := $(VENV)/bin/python
SLN := viewer_net/DanaSim.Viewer.slnx
WEB_PROJECT := viewer_net/src/DanaSim.Viewer.Web/DanaSim.Viewer.Web.csproj

.PHONY: setup setup-python setup-net run run-python run-net test test-python test-net clean

setup: setup-python setup-net

setup-python:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PY) -m pip install -U pip
	$(VENV_PY) -m pip install -r python/visualizer/requirements.txt pytest pytest-cov

setup-net:
	dotnet restore $(SLN)

run: run-net

run-python:
	$(VENV_PY) -m python.visualizer

run-net:
	dotnet run --project $(WEB_PROJECT)

test: test-python test-net

test-python:
	$(VENV_PY) -m pytest python/tests/visualizer -q

test-net:
	dotnet test $(SLN)

clean:
	rm -rf $(VENV)
