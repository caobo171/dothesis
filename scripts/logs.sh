#!/usr/bin/env bash
# DoThesis log viewer — wraps journalctl for the systemd-supervised services.
#
# Usage:
#   ./scripts/logs.sh                # last 100 lines of the API (default)
#   ./scripts/logs.sh -f             # follow API live (tail -f style)
#   ./scripts/logs.sh web            # last 100 lines of the web app
#   ./scripts/logs.sh web -f         # follow web live
#   ./scripts/logs.sh -n 300         # last 300 lines of the API
#   ./scripts/logs.sh errors         # API tracebacks/errors since last restart
#   ./scripts/logs.sh -f api web     # follow both API and web together
set -euo pipefail

LINES=100
FOLLOW=0
MODE=""              # "" | errors
UNITS=()

# --- parse args (order-independent: service names, flags, and `errors`) ---
for arg in "$@"; do
  case "$arg" in
    api)        UNITS+=("dothesis-api.service") ;;
    web)        UNITS+=("dothesis-web.service") ;;
    -f|--follow) FOLLOW=1 ;;
    errors|err) MODE="errors" ;;
    -n) :       ;;  # handled below
    *)  if [[ "$arg" =~ ^[0-9]+$ ]]; then LINES="$arg"; fi ;;
  esac
done
# `-n 300` style (value follows the flag)
prev=""
for arg in "$@"; do
  [[ "$prev" == "-n" ]] && LINES="$arg"
  prev="$arg"
done

# default to the API service when none named
[[ ${#UNITS[@]} -eq 0 ]] && UNITS=("dothesis-api.service")

# build `-u svc -u svc` args
UNIT_ARGS=()
for u in "${UNITS[@]}"; do UNIT_ARGS+=(-u "$u"); done

# need root to read another unit's journal on most setups
SUDO=""; [[ $EUID -ne 0 ]] && SUDO="sudo"

if [[ "$MODE" == "errors" ]]; then
  echo "==> errors/tracebacks for ${UNITS[*]} (since last boot)"
  $SUDO journalctl "${UNIT_ARGS[@]}" --no-pager -b \
    | grep -iE "error|traceback|exception|critical|500 internal|modulenotfound" -A20 \
    || echo "(no matching error lines)"
elif [[ $FOLLOW -eq 1 ]]; then
  echo "==> following ${UNITS[*]} live — Ctrl-C to stop"
  $SUDO journalctl "${UNIT_ARGS[@]}" -f -n "$LINES" --no-pager
else
  echo "==> last $LINES lines of ${UNITS[*]}"
  $SUDO journalctl "${UNIT_ARGS[@]}" -n "$LINES" --no-pager
fi
