#!/usr/bin/env bash
# Run any api/.venv tool with the interpreter forced to arm64 when possible.
#
# Why: api/.venv's compiled wheels (pydantic_core, numpy, scipy, ...) are arm64.
# The venv's python is a *universal* binary, so when this repo is driven from a
# Rosetta / x86_64 shell the interpreter loads as x86_64 and then can't import
# those arm64 .so files ("incompatible architecture"). Forcing `arch -arm64`
# keeps the interpreter and the installed wheels on the same architecture.
#
# `arch -arm64` is a no-op on a native arm64 shell, so this is harmless there;
# on a real Intel mac (where `arch -arm64` can't run) we fall back to running
# the tool directly.
#
# Usage:
#   ./run.sh pytest tests/test_chat_router.py -q
#   ./run.sh alembic upgrade head
#   ./run.sh python -m pytest
#   ./run.sh uvicorn app.main:app --reload
set -euo pipefail
cd "$(dirname "$0")"

if [ $# -eq 0 ]; then
  echo "usage: ./run.sh <pytest|alembic|python|uvicorn|...> [args]" >&2
  exit 2
fi

bin=".venv/bin/$1"
if [ ! -x "$bin" ]; then
  echo "run.sh: '$1' is not an executable in .venv/bin — is the venv set up?" >&2
  exit 127
fi
shift

if arch -arm64 true 2>/dev/null; then
  exec arch -arm64 "$bin" "$@"
fi
exec "$bin" "$@"
