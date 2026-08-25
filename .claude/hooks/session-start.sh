#!/usr/bin/env bash
# SessionStart: prepara l'ambiente in modo che i comandi `mtgsocial` e il
# server MCP funzionino subito, anche in una sessione Claude Code sul web
# dove il container e' appena stato creato.
set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" || exit 0

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv >/dev/null 2>&1 || exit 0
fi

# Installa solo se manca qualcosa: le sessioni successive partono immediate.
if ! .venv/bin/python -c "import jinja2, requests, dateutil, yaml" >/dev/null 2>&1; then
  .venv/bin/pip install --quiet --disable-pip-version-check -e ".[dev,mcp]" >/dev/null 2>&1
fi

missing=()
for secret in IG_USER_ID IG_ACCESS_TOKEN; do
  [[ -z "${!secret:-}" ]] && missing+=("$secret")
done

echo "mtg-social pronto. CLI: ./.venv/bin/mtgsocial"
if (( ${#missing[@]} )); then
  echo "Nota: ${missing[*]} non impostate: la pubblicazione reale non e' disponibile in questa sessione (--dry-run funziona)."
fi
exit 0
