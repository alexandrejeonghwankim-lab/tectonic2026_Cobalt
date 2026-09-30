# KBC NOVA

**Next-step Orchestration for Value and Assistance**

KBC NOVA is a local proof of concept for the Tectonic Hackathon KBC challenge. The challenge asks how KBC could better understand, support and guide more than 2.3 million customers at the right moment, in a scalable way.

This project explores a privacy-aware personalization engine: KBC teams can define a customer support intent, test it against synthetic customer signals, pass it through governance checks, and see which single message, if any, a customer should receive.

The central idea is simple: a bank should not only decide what to say. It should also know when to stay quiet.

## Why This Fits The KBC Brief

The KBC brief is not asking for another isolated feature. It asks for a proof of concept for a scalable personalization approach that strengthens the relationship between KBC and its customers.

KBC NOVA answers that with one shared engine for:

- understanding customer situations from approved signals
- respecting consent and protection rules
- preventing irrelevant or badly timed offers
- selecting one useful next step per customer
- explaining why a customer sees a message
- scaling decisions over a large synthetic population without calling AI for every customer

The demo focuses on customer trust. For example, if a customer has a stuck insurance claim, the system prioritizes help with the claim instead of showing a travel insurance offer.

## Project Context

This was built for the Tectonic Hackathon on 30 September 2026.

The official submission requires:

- a short project description
- a public GitHub repository
- a demo video under 3 minutes
- screenshots from the Aikido security audit
- a short README explaining how to run the project and what is unfinished

The judging criteria are:

- creativity
- technical ability
- fit with the challenge
- security

All data in this repository is synthetic. Do not enter real customer data.

## What The Prototype Shows

The app demonstrates a governed personalization flow:

1. Library guidance campaigns are already active.
2. A KBC employee can create or load an example customer intent.
3. The intent is converted into audience conditions over approved synthetic signals.
4. A backtest runs across 100,000 generated customer rows.
5. Governance and consent rules remove unsuitable customers.
6. Arbitration chooses the most useful message per customer.
7. The customer preview shows the winning message, silence, or suppressed alternatives.
8. Every visible outcome can be inspected through actual CSV row values and campaign rules.

Optional AI can draft an audience rule from a plain-language request, but the core decision engine is deterministic and works without AI.

## Demo Story

Use this short story for a judging demo:

> Banks usually talk to customers when it suits the bank. KBC NOVA helps the bank speak when it helps the customer, and stay quiet when it does not.

Suggested flow:

1. Open Marc in **Test customers**.
2. Show that his home-insurance claim needs documents and that other offers are suppressed.
3. Open Emma and show a life-event guidance message for turning 18.
4. Go to **Campaigns** and load the travel insurance or car/mobility example.
5. Run the backtest over all synthetic customers.
6. Inspect a winning CSV row and its audit trail.
7. Activate the campaign locally.
8. Return to customer previews and show that governance and arbitration still choose only the most appropriate message.

The most important point is not that the app can create campaigns. The important point is that all messages, library guidance and employee-created offers pass through one customer-protection engine.

## Run Locally

Requirements:

- Python 3.12
- Node.js

On Linux or macOS:

```bash
./start.sh
```

On Windows:

```bat
start.bat
```

Then open the local address shown in the terminal, normally:

```text
http://localhost:3000
```

Keep the terminal running while using the app. Press `Ctrl+C` to stop it.

There is no login and no password. This is a local demo server only. Do not expose it to the public internet.

## Main Screens

### Campaigns

Create or load an example customer intent, define the message, optionally upload an image, run a backtest and activate the campaign locally.

The AI audience box is separate from the customer-facing message. If AI is used, it receives only the audience request and the approved signal schema, not customer rows or real personal data.

### Test Customers

Inspect Emma, Marc, a random row or any CSV row. The app recomputes the decision for that row and shows:

- actual signal values
- matched campaigns
- blocked campaigns
- suppressed alternatives
- the final customer-facing message or silence
- the explanation shown to the customer

### Registry

See active campaigns and pause or resume them for local simulation.

### Governance

Review the allowed targeting signals, protection-only signals and the logic used to match, protect, choose one message and explain the outcome.

### Settings

Configure an OpenAI-compatible endpoint if you want to test AI-assisted audience drafting. The app also works with offline examples.

## Data

The generated dataset contains 100,000 synthetic customer signal rows.

Important files:

- `data/customer_signals.csv`: main synthetic signal store used for backtests and previews
- `campaigns/library/`: always-on guidance definitions
- `campaigns/registry/`: locally activated employee-created campaigns
- `campaign_engine.py`: deterministic matching, governance and arbitration logic
- `workbench.py`: app workflow logic
- `generate_data.py`: reproducible synthetic data generation

Emma and Marc are showcase rows, but they are still processed by the same logic as every other row.

## Checks

Run tests:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Compile the Reflex app:

```bash
.venv/bin/reflex compile
```

Regenerate synthetic base records:

```bash
.venv/bin/python generate_data.py
```

Regenerating data overwrites the base synthetic CSVs, not approved campaigns or uploaded images.

## Security And Privacy Approach

This prototype is designed to avoid common hackathon pitfalls:

- no real customer data
- no committed API keys
- synthetic opaque customer identifiers
- deterministic validation of AI output
- campaign rules are data, not executable code
- no credit, pricing, eligibility or insurance underwriting decisions
- forbidden sensitive targeting categories are blocked
- the AI drafting step does not receive customer rows

This is still a proof of concept, not a production banking system or legal compliance approval.

## Limitations

- No real KBC integration
- No production authentication
- No real delivery of messages, emails, calls or notifications
- No real consent synchronization
- No production-grade compliance review
- No validated transaction-derived feature pipeline
- No credit, insurance pricing or investment advice decisions

The prototype is meant to demonstrate the operating model: scalable, explainable and restrained personalization that protects the customer relationship.

