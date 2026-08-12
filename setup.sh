#!/usr/bin/env bash
# One-shot environment bootstrap for the Board Book Generator.
#
# Creates/reuses a .venv, installs the project + dev dependencies, and
# installs the headless Chromium build Playwright needs to render the
# agenda cover page. Safe to re-run.
#
# Usage:
#   ./setup.sh

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "error: $PYTHON_BIN not found. Install Python 3.9+ first." >&2
  exit 1
fi

PY_VERSION="$("$PYTHON_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_OK="$("$PYTHON_BIN" -c 'import sys; print(1 if sys.version_info >= (3, 9) else 0)')"
if [ "$PY_OK" != "1" ]; then
  echo "error: Python 3.9+ is required (found $PY_VERSION)." >&2
  exit 1
fi
echo "Using $PYTHON_BIN ($PY_VERSION)"

if [ ! -d .venv ]; then
  echo "Creating virtualenv at .venv ..."
  "$PYTHON_BIN" -m venv .venv
else
  echo "Reusing existing .venv"
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "Upgrading pip/setuptools/wheel ..."
pip install --upgrade pip setuptools wheel -q

echo "Installing boardbook-generator + dev dependencies ..."
pip install -e ".[dev]" -q

# Fail fast, before the ~150MB Chromium download: some Python builds have a
# broken `typing` module that crashes Pydantic's JSON schema generation
# (observed with an old python.org 3.9.0 install shadowing the system Python
# in PATH). Left uncaught, this only ever surfaces as a cryptic runtime error
# deep in the app when parsing an agenda.
echo "Checking that this Python build works with Pydantic ..."
if ! python -c "from boardbook.parser.schema import ExtractedAgenda; ExtractedAgenda.model_json_schema()" >/tmp/boardbook_schema_check.log 2>&1; then
  echo
  echo "error: this Python interpreter's 'typing' module is broken and crashes" >&2
  echo "Pydantic's schema generation (used for Claude's structured outputs)." >&2
  echo >&2
  echo "Interpreter in use: $(python -c 'import sys; print(sys.executable, sys.version.split()[0])')" >&2
  echo "Error was: $(tail -1 /tmp/boardbook_schema_check.log)" >&2
  echo >&2
  echo "Recreate the venv with a different Python 3.9+ interpreter. On macOS, the" >&2
  echo "Xcode-bundled /usr/bin/python3 is usually a safe choice:" >&2
  echo "  rm -rf .venv" >&2
  echo "  PYTHON_BIN=/usr/bin/python3 ./setup.sh" >&2
  exit 1
fi
echo "OK"

echo "Installing headless Chromium for Playwright (one-time, ~150MB) ..."
playwright install chromium

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example - set ANTHROPIC_API_KEY in it before parsing agendas."
fi

echo
echo "Setup complete. Verifying the environment ..."
echo
boardbook doctor || true

echo
echo "Next steps:"
echo "  1. Activate the venv in every new terminal: source .venv/bin/activate"
echo "  2. Set ANTHROPIC_API_KEY in .env (or run: ant auth login)"
echo "  3. Launch the web app:  streamlit run app.py"
echo "     Or use the CLI:      boardbook --help"
