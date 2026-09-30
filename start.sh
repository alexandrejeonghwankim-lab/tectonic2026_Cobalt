#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -x .venv/bin/python ]]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
fi
if [[ ! -x .venv/bin/reflex ]] || ! .venv/bin/python -c 'import reflex' >/dev/null 2>&1; then
    echo "Installing declared dependencies..."
    .venv/bin/python -m pip install -r requirements.txt
fi
if [[ ! -s data/customer_signals.csv || ! -s data/customers.csv || ! -s data/accounts.csv || ! -s data/insurance_claims.csv ]]; then
    echo "Generating fictional data..."
    .venv/bin/python generate_data.py
fi
echo "Open the local address shown by Reflex (usually http://localhost:3000). No login is needed. Ctrl+C stops it."
exec .venv/bin/reflex run "$@"
