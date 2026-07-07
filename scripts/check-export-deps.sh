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
#   - no mmdc        → conceptual-model mermaid diagrams render as a text
#                      relationship list instead of a real PNG in the doc
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

# --strict               → exit 1 if ANY export dep (pandoc/libreoffice) is missing.
# --require-libreoffice  → exit 1 if LibreOffice specifically is missing/broken.
#                          LibreOffice is MANDATORY: without it the PDF loses its
#                          Table of Contents + clickable citations. Can also be
#                          forced with REQUIRE_LIBREOFFICE=1 in the environment.
STRICT=0
REQUIRE_LO="${REQUIRE_LIBREOFFICE:-0}"
for arg in "$@"; do
  case "$arg" in
    --strict) STRICT=1 ;;
    --require-libreoffice|--require-soffice) REQUIRE_LO=1 ;;
  esac
done

missing=0
soffice_ok=0

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
# IMPORTANT: don't trust `command -v` alone — a brew cask symlink can survive
# after the app bundle it points to is deleted (a dangling symlink that exits
# 0 on `which` but fails the moment you run it). Actually invoke --version so a
# broken install is reported, not silently passed.
soffice_bin=""
if command -v soffice >/dev/null 2>&1; then
  soffice_bin=soffice
elif command -v libreoffice >/dev/null 2>&1; then
  soffice_bin=libreoffice
fi
if [ -n "$soffice_bin" ] && "$soffice_bin" --version >/dev/null 2>&1; then
  echo "  ✓ libreoffice (DOCX→PDF) — $("$soffice_bin" --version 2>/dev/null | head -1)"
  soffice_ok=1
elif [ -n "$soffice_bin" ]; then
  echo "  ✗ ${soffice_bin} is on PATH but BROKEN (won't run — dangling install?). Reinstall: ${SOFFICE_HINT}"
  missing=$((missing + 1))
else
  echo "  ✗ libreoffice/soffice NOT found — PDF export will degrade. Install: ${SOFFICE_HINT}"
  missing=$((missing + 1))
fi

# Mermaid CLI + its puppeteer-managed Chrome — renders the conceptual-model
# `flowchart LR` block to a PNG that pandoc embeds in the DOCX. Missing = fall
# back to a text relationship list (doc still ships), so this is INFORMATIONAL
# only — never counts toward `--strict` failure.
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MMDC="${REPO_DIR}/engine/tools/mermaid_cli/node_modules/.bin/mmdc"
if [ -x "$MMDC" ]; then
  echo "  ✓ mmdc (mermaid → PNG for conceptual model)"
  PUP_CACHE="${PUPPETEER_CACHE_DIR:-$HOME/.cache/puppeteer}"
  if [ -d "$PUP_CACHE/chrome" ] && [ -n "$(ls -A "$PUP_CACHE/chrome" 2>/dev/null || true)" ]; then
    echo "  ✓ puppeteer chrome for testing (in $PUP_CACHE/chrome)"
  else
    echo "  ○ puppeteer chrome NOT installed — mermaid → PNG will fall back to a text list."
    echo "    Install: (cd engine/tools/mermaid_cli && npx --yes puppeteer browsers install chrome)"
  fi
else
  echo "  ○ mmdc NOT installed — conceptual-model diagrams render as a text list."
  echo "    Install: (cd engine/tools/mermaid_cli && npm install)"
fi

# LibreOffice is MANDATORY when requested: the DOCX→PDF path is the ONLY way the
# PDF gets a Table of Contents + clickable citations. Without it the PDF silently
# degrades to WeasyPrint (no TOC, no citation links), so block the boot/deploy.
if [ "$REQUIRE_LO" -eq 1 ] && [ "$soffice_ok" -ne 1 ]; then
  echo "==> FATAL: LibreOffice (soffice) is REQUIRED but not usable." >&2
  echo "    The PDF export needs it for the Table of Contents + clickable citations." >&2
  echo "    Install it: ${SOFFICE_HINT}" >&2
  exit 1
fi

if [ "$missing" -gt 0 ]; then
  echo "==> ${missing} export dependency(ies) missing — DOCX/PDF will use fallback renderers."
  [ "$STRICT" -eq 1 ] && exit 1
else
  echo "==> export toolchain OK"
fi
exit 0
