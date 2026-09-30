# KBC NOVA

**Next-step Orchestration for Value and Assistance**

KBC NOVA is a proof of concept for a scalable, privacy-aware personalization layer for retail banking.

The project responds to the KBC challenge: how can a bank understand what customers need, respond at the right moment, and do this meaningfully for millions of people?

NOVA helps KBC coordinate customer guidance through one shared decision engine. It checks context, consent, timing and customer protection rules before selecting what a customer should receive. Sometimes that means showing a useful next step. Sometimes the most respectful decision is silence.

## Product Vision

Modern banks have many reasons to contact customers: life events, claims, savings goals, product offers, financial guidance and service reminders. Without coordination, those messages can become noisy or badly timed.

KBC NOVA turns personalization into a governed customer relationship system:

- one engine for service messages, guidance and offers
- one customer-level decision about what is most useful now
- clear reasons for why a message appears
- protection rules that block unsuitable offers
- synthetic large-scale backtesting before activation
- optional AI support for drafting audience rules

The result is a banking experience that feels proactive, personal and respectful at scale.

## What The Prototype Demonstrates

The application shows how KBC could manage personalized journeys without calling AI for every customer.

Core flow:

1. A customer intent or campaign is defined.
2. The audience is expressed as rules over approved synthetic customer signals.
3. Governance checks validate the rule.
4. A backtest runs across 100,000 synthetic customer rows.
5. Consent, protection rules and cooldowns are applied.
6. Arbitration selects the single most appropriate message per customer.
7. The customer preview shows the selected message, silence or suppressed alternatives.
8. The audit view explains the decision using the actual synthetic row values.

Example: if Marc has a home-insurance claim waiting for documents, NOVA prioritizes claim help instead of showing him a travel insurance offer. If Emma turns 18, NOVA gives her first-step banking guidance instead of a random promotion.

## Running The Project

Requirements:

- Python 3.12
- Node.js

Start the local app:

```bash
./start.sh
```

On Windows:

```bat
start.bat
```

Open the local address shown in the terminal, normally:

```text
http://localhost:3000
```

Keep the terminal running while using the application. Press `Ctrl+C` to stop it.

This is a local prototype. There is no login and no password. Do not expose the server publicly and do not enter real customer data.

## How To Try It

### 1. Inspect Customer Decisions

Open **Test customers** and select Emma, Marc, a random row or any CSV row.

The screen shows:

- the message the customer receives, if any
- the actual synthetic signal values
- every campaign considered
- why campaigns matched, failed, were blocked or were suppressed
- the final explanation shown to the customer

### 2. Backtest A Customer Intent

Open **Campaigns** and load an offline example such as travel insurance or car/mobility.

Run the backtest to evaluate the rule against all synthetic customers. The app reports reach, selected customers and suppression reasons.

### 3. Activate Locally

After a backtest, activate the campaign locally. It is saved to the local campaign registry and participates in future simulated decisions.

No real notification, email, message or customer contact is sent.

### 4. Try AI-Assisted Audience Drafting

Optionally, enter an audience request in the AI audience field. The AI is used only to draft filters over approved signal names.

The AI does not receive customer rows, real personal data or the customer-facing message. Its output must pass deterministic validation before it can be backtested or activated.

## Main Screens

**Campaigns**

Create or load a customer intent, define the message, optionally add an image, run a backtest and activate the campaign locally.

**Test customers**

Inspect customer-level outcomes and verify every decision against synthetic CSV values.

**Registry**

View active local campaigns and pause or resume them.

**Governance**

Review the matching, protection, selection and explanation logic.

**Settings**

Configure an OpenAI-compatible endpoint for optional AI-assisted audience drafting.

## Data

All data is synthetic.

The base dataset contains 100,000 generated customer signal rows. Emma and Marc are showcase rows, but they use the same decision logic as every other row.

Important files:

- `data/customer_signals.csv`: main synthetic signal store
- `campaigns/library/`: always-on guidance definitions
- `campaigns/registry/`: locally activated campaigns
- `campaign_engine.py`: matching, governance and arbitration logic
- `workbench.py`: application workflow logic
- `generate_data.py`: reproducible synthetic data generation

The app can also import another UTF-8 CSV with the required headers documented in the interface.

## Technical Approach

NOVA separates authoring from runtime decision-making.

At authoring time, a KBC employee can describe a customer intent and optionally use AI to draft audience filters. At runtime, deterministic Python logic evaluates approved rules against precomputed signals.

This keeps the core customer decision:

- auditable
- reproducible
- explainable
- independent from per-customer AI calls
- constrained to approved data fields

The decision engine combines:

- signal matching
- consent tier checks
- protection rules
- campaign cooldowns
- contact budget logic
- priority-based arbitration

## Security And Privacy Notes

The prototype is designed around privacy and restraint:

- no real customer data is used
- no API keys should be committed
- customer identifiers are synthetic
- AI output is treated as untrusted
- user-created rules are stored as data, not executed as code
- sensitive targeting categories are blocked
- financial pressure can be used for protection, not for targeting offers
- the app does not make credit, pricing, eligibility or underwriting decisions

This is a proof of concept, not a production banking system or a legal compliance approval.

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

Regenerating data overwrites the base synthetic CSV files. It does not approve campaigns or send any customer communication.

## Limitations

- no real KBC integration
- no production authentication
- no real message delivery
- no production consent synchronization
- no production compliance workflow
- no validated transaction-derived feature pipeline
- no credit, insurance pricing or investment advice decisions

KBC NOVA demonstrates the operating model: scalable personalization that protects the customer relationship by choosing the most helpful next step, or choosing not to interrupt.

