#KBC NOVA: Next-step, Orchestration for Value and Assistance

**Start:** on Linux run `./start.sh`; on Windows double-click `start.bat` (or run it in Command Prompt). Windows uses its own `.venv-win` environment; Windows startup has not been tested on a Windows machine., Open the local address shown (normally `http://localhost:3000`). **No access code or sign-in.** Ctrl+C stops it. This is a local demonstration: never expose it publicly or enter real customer data. Python 3.12 and Node.js are needed; the launcher installs the declared dependency if missing. See [GUIDE.md](GUIDE.md) for every button and the in-app Help page for a short overview.

## Demo in 2 minutes

1. **Campaigns:** click **Travel insurance example** to load an offline audience without waiting for AI. The **label** and **message** are editable; optional image and dates are below. Click **Run backtest on all synthetic customers**. Watch the progress indicator. The reach funnel is computed from `data/customer_signals.csv` and all currently running campaigns. Click one of the winning CSV sample rows to see the matching inputs and the complete audit. Back on Campaigns, click **Activate locally in registry** to save the campaign and participate in future decisions; no notifications are delivered.
2. **Test customers:** open Emma (row 1), Marc (row 2), random row or any numbered CSV row; browse the list. The winner and each campaign's actual filter result are recomputed on that row. Try **Simulate this change** (e.g. change savings balance), then **Reset to CSV values**. The simulation never edits the CSV.
3. **Campaigns:** fill the label, message and **AI audience request** (a separate text box describing who should see the offer, e.g. “Adults 18 to 29 with at least €18,000 in savings and an increasing monthly surplus, October–November”). Click **Draft audience with AI**; a spinner and disabled button indicate a request in progress (up to 60 seconds). The AI proposes filters *only*; review them and the assumptions, then backtest and activate. **Car/mobility example** is an offline backup. Configure the keyless endpoint/model or an HTTPS compatible endpoint in Settings.
4. **Registry:** see and pause/resume campaigns; service guidance and employee campaigns share the same one-message decision engine. **Governance** explains why a customer matched, was blocked, or got silence.

## What is computed, what is example data?

- `generate_data.py` makes **100,000 invented signal rows** with a fixed seed. Emma and Marc are the first two **showcase rows**; every other row also passes through exactly the same `campaign_engine.matches`, `gate`, and `decision`. A row number on Test customers corresponds to the line number (after header) in `data/customer_signals.csv`. The generator does **not** read `BankCustomerData.csv`. An older `data/signals.csv` and `intent_engine.py` from the prior prototype are unused.
- Three always-on *example definitions* live in `campaigns/library/`. Travel and mobility *example definitions* live in `campaigns/travel_example.json` and `campaigns/car_example.json`. They are templates, not hard-coded decisions, counts or customer outcomes. The exact campaign message and audience rules are editable. Employee-approved campaigns are saved to `campaigns/registry/`; pausing is stored in `campaigns/status.json`.
- The backtest **iterates over every customer row** and reports match, eligible, selected and suppressed counts, plus winning row numbers. The preview displays the selected CSV row's actual values next to all candidate campaign conditions. An image must be a locally uploaded PNG/JPEG/WebP below 2 MB; it is used as the selected campaign's background.
- Optional AI is used **once to draft an audience**, not once per customer. It receives only the contents of the separate AI audience box and a schema of approved signal names; not CSV rows, customer data or the customer-facing message. Its output is untrusted and must pass the deterministic validator. It cannot add unknown fields, executable code, health/religious targeting, credit decisions or unsupported data sources. If AI fails, the page shows an error and you can load an offline example.
- The fixed demo clock is **2026-09-30**. A future-dated campaign can be backtested at its start date but only appears in customer decisions once that date is selected for the winning sample preview. No actual delivery, consent synchronisation, prediction, or production identity management is implemented. There is **no authentication**; run this only on your own machine. Simulated historical balances/trends are not real market prices or verified predictions.

## Reproduce checks

- Tests: `.venv/bin/python -m unittest discover -s tests -v`
- Reflex compile: `.venv/bin/reflex compile`
- Regenerate invented base records: `.venv/bin/python generate_data.py` (this overwrites the base synthetic CSVs, not approved campaigns or uploaded images).

The prototype is a proof of concept, not a live bank integration or a compliance approval. Each visible result can be traced to a synthetic CSV row, an approved campaign JSON definition, and deterministic Python logic.

## Swap the dataset and see real differences

In **Test customers**, select a UTF-8 CSV and click **Import selected CSV**, or replace `data/customer_signals.csv` on disk and click **Reload CSV from disk**. Required headers: `customer_id`, `age`, `consent_tier` (`service`, `guidance`, `offers`); optional: `first_name`, `city` and any approved synthetic signal fields visible in Governance. Upload is limited to 32 MB and 150,000 rows. The customer list, name, decisions and all subsequent backtests use the active file; **Restore original dataset** returns to the 100,000-row sample. Missing financial or protective fields cannot trigger an offer.

The always-on library now includes a **budget-buffer tip**, **goal-specific savings tip**, and **borrowing information** for adults whose synthetic surplus, savings and buffer cross explicit thresholds. The customer preview inserts actual synthetic amounts; it never claims loan approval, rates or affordability. To see contrasting results in the original CSV, inspect rows **5 (borrowing information), 17 (budget), 7 (savings), 1 (Emma), 2 (Marc)**. Results are recalculated from the CSV, not special-cased on row numbers.
