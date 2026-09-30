# Button-by-button demo guide

## Start

On Linux run `./start.sh`; on Windows run `start.bat` from the project directory (Windows requires Python and Node.js). Open the localhost address shown. **There is no login and no password.** Keep the terminal running. Don't expose this demo server to the public internet. Press Ctrl+C to stop.

## Campaigns — make an offer

| Control | What it does |
|---|---|
| **Campaign label** | The title a customer will see. Required. |
| **Message the customer sees** | Your exact copy; `{first_name}` is the only optional name placeholder. Required. Changing it clears a previous backtest approval. |
| **Image** → **Upload selected image** | Pick a local PNG, JPEG or WebP under 2 MB. Upload stores it locally; it becomes the campaign background. **Remove image** returns to the plain background. Optional. |
| **AI audience request** | **Separate text box**: describe exactly *which customers* should see the campaign. This is the only free-form campaign request sent to AI; no customer data or customer message is transmitted. Required only if you use AI. |
| **Draft audience with AI** | Makes one OpenAI-compatible request. Shows **Drafting… / spinner**, disables the button and inputs during the request (up to 60 seconds), then shows readable AND filters and assumptions or an actionable error. **This does not save or activate anything.** Do not click twice. |
| **Travel insurance example / Car/mobility example** | Load offline reviewed audience conditions and example label/message. Works without AI. Each click creates a new local draft ID. Neither button activates the example or contacts customers. |
| **Optional campaign dates** | Closed by default. Click to change the start/end; the fixed simulation clock is 2026-09-30. A future campaign won't show to customers on 2026-09-30, but its backtest simulates at its start date. |
| **Run backtest on all synthetic customers** | Checks the draft against *every* real generated CSV row, ages, consent, protection, cooldown and other active campaigns. Shows spinner, selected reach and reasons. Can take several seconds. **No messages are sent.** |
| **Inspect CSV row N** | Opens a winning customer from the backtest on the *same* simulation date. Shows actual signal values and why every campaign was selected, suppressed, unmatched, or outside its dates. |
| **Activate locally in registry** | Requires a completed backtest with no edits since review. Saves this campaign's validated JSON locally and includes it in future simulated decisions. **No actual push, email, call or notification is sent.** |

The sample offers use the `offers` consent tier; under-18s cannot receive them. If AI is slow/unavailable, use **Travel insurance example** or **Car/mobility example** and continue with backtest.

## Test customers — inspect the real decision logic

- **Emma · row 1 / Marc · row 2:** examples with a life event and a claim, *not separate code paths*. Both are actual rows in `data/customer_signals.csv`.
- **Pick random CSV row:** samples any row from the actual dataset. **CSV row number → Open row:** opens the specific row number (starting at 1, excluding the header). **Previous/Next 20 rows:** browse other records and click a row to inspect it.
- **KBC app preview:** shows the single winning message or silence. **Actual signal values:** shows the selected CSV row's values. **Campaign-by-campaign audit:** shows each campaign, each filter's pass/fail and the exact value tested, plus consent/safety/priority reasons.
- **What-if signal / value → Simulate this change:** makes an **in-memory copy** of the current row, changes one allowed field and recomputes the decision. Examples: `savings_balance` + `18000`, or `consent_tier` + `service`, or `open_insurance_claim` + `yes`. **Reset to CSV values:** discards the copy; the original CSV is not modified.

## Registry, Governance, Settings, Help

- **Registry → Pause locally / Resume locally:** stops/restarts a campaign in local simulations; doesn't delete it or send any notification. The five library campaigns run automatically at startup unless paused. The other campaigns appear after **Activate locally**.
- **Governance:** a readable four-step explanation (match → protect → choose one → explain) and the live allowlist of targeting columns versus protection-only columns.
- **Settings:** the OpenAI-compatible `/v1` endpoint and model. The default keyless endpoint is `http://100.70.65.86:9910/v1` using **`gpt-6-sol`** (the prefixed alias may return HTTP 400). If your provider needs a key, enter it only with HTTPS; it stays in server session state and is not written to disk. **AI customer generation** is not needed to test arbitrary existing CSV customers.
- **Help:** a short description of each page and what the buttons do.

### Evidence and limitations

Use the actual `data/customer_signals.csv` row number and the JSON files under `campaigns/` to verify a result in `campaign_engine.py` and `workbench.py`. The backtest is computed from 100,000 invented customers, not from Emma/Marc only; the counts depend on enabled campaigns. Base CSV rows are synthetic signals, not a verified transaction-derived feature pipeline. This is not a production banking or compliance system.

## Swap customer CSV (Test customers)

Select a UTF-8 CSV (required headers `customer_id,age,consent_tier`; optional `first_name,city` and approved signal columns), then click **Import selected CSV**. This changes the active customer list, names, rule decisions and next backtest immediately. **Reload CSV from disk** detects a replaced active file; **Restore original dataset** returns to the original 100,000 synthetic customers. Missing offer/protection data fails closed. Row 5 of the original CSV illustrates borrowing information; row 17 budgeting; row 7 a savings goal. Loan information is NOT a loan decision.
