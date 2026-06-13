#!/usr/bin/env bash
# Verify the system tools the M5 thesis exporter needs to produce a
# fully-formatted DOCX + PDF. These are SYSTEM packages (not pip), so they
# must be installed on whatever host runs the FastAPI process — your laptop
# in dev, the Ubuntu server in prod.
#
# Without them the exporter still runs but degrades:
#   - no pandoc      → DOCX falls back to a basic python-docx render
#                      (no Word heading styles / clean TOC / table fidelity)
#   - no libreoffice → DOCX→PDF conversion is unavailable; PDF export falls
#     (soffice)        back to weasyprint, which needs a healthy Pillow build
#
# Exit code is ALWAYS 0 (informational): a missing renderer should warn, never
# block the stack from booting. Pass --strict to exit 1 when something's
# missing (useful in CI / provisioning checks).
#
# ── Ubuntu server setup ──────────────────────────────────────────────
#   sudo apt-get update
#   sudo apt-get install -y pandoc libreoffice-writer
#   # libreoffice-writer is enough for DOCX→PDF; the full `libreoffice`
#   # metapackage also works but is much larger.
#
# ── macOS dev setup ──────────────────────────────────────────────────
#   brew install pandoc
#   brew install --cask libreoffice
# ─────────────────────────────────────────────────────────────────────

set -uo pipefail

STRICT=0
[ "${1:-}" = "--strict" ] && STRICT=1

missing=0

# Pick the right install hint for this OS so the message is copy-pasteable.
if [ "$(uname -s)" = "Darwin" ]; then
  PANDOC_HINT="brew install pandoc"
  SOFFICE_HINT="brew install --cask libreoffice"
else
  PANDOC_HINT="sudo apt-get install -y pandoc"
  SOFFICE_HINT="sudo apt-get install -y libreoffice-writer"
fi

check() {
  local bin="$1" label="$2" hint="$3"
  if command -v "$bin" >/dev/null 2>&1; then
    echo "  ✓ ${label} ($(command -v "$bin"))"
  else
    echo "  ✗ ${label} NOT found — exports will degrade. Install: ${hint}"
    missing=$((missing + 1))
  fi
}

echo "==> checking M5 export toolchain"
check pandoc   "pandoc (DOCX formatting)"        "$PANDOC_HINT"
# LibreOffice ships the binary as `soffice` (or `libreoffice` on some distros).
if command -v soffice >/dev/null 2>&1 || command -v libreoffice >/dev/null 2>&1; then
  echo "  ✓ libreoffice (DOCX→PDF)"
else
  echo "  ✗ libreoffice/soffice NOT found — PDF export will degrade. Install: ${SOFFICE_HINT}"
  missing=$((missing + 1))
fi

if [ "$missing" -gt 0 ]; then
  echo "==> ${missing} export dependency(ies) missing — DOCX/PDF will use fallback renderers."
  [ "$STRICT" -eq 1 ] && exit 1
else
  echo "==> export toolchain OK"
fi
exit 0
