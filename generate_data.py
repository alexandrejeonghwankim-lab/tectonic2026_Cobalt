"""Reproducible, entirely invented data. No original CSV row is consumed."""
import csv
import json
import random
import uuid
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / 'data'
TODAY = date(2026, 9, 30)  # fixed simulation clock, for reproducible windows
SIGNALS = ['customer_id', 'age', 'age_band', 'city', 'turned_18_last_30d', 'open_insurance_claim',
           'claim_waiting_documents_days', 'claim_documents_needed', 'monthly_surplus_3m', 'savings_buffer_months',
           'savings_balance', 'surplus_trend_up_3m', 'financial_pressure', 'travel_spend_12m', 'has_travel_insurance',
           'products_held', 'contacts_last_30d', 'last_contact_campaign', 'last_contact_days_ago',
           'consent_tier', 'channels_allowed', 'channel_preference', 'active']
PERSONAS = [
    dict(first_name='Emma', age=18, city='Antwerpen', tier='offers', birthday_days_ago=5,
         claim_days=0, documents=0, surplus=380, buffer=4, savings=2600, trend=1, pressure=0,
         travel=890, insured=0, contacts=0, products='youth_account|savings'),
    dict(first_name='Marc', age=44, city='Leuven', tier='offers', birthday_days_ago=120,
         claim_days=12, documents=2, surplus=240, buffer=1, savings=14500, trend=0, pressure=1,
         travel=1250, insured=0, contacts=0, products='current_account|home_insurance|savings'),
]


def band(age):
    return 'under 18' if age < 18 else '18–25' if age <= 25 else '26–64' if age < 65 else '65+'


def write_csv(path, fields, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def generate(population=100_000, profile_count=2, output=OUT):
    rng = random.Random(20260930)
    output.mkdir(parents=True, exist_ok=True)
    customers, accounts, consents, claims, history, transactions, ids = [], [], [], [], [], [], {}
    age_counts = {b: 0 for b in ('under 18', '18–25', '26–64', '65+')}
    with (output / 'customer_signals.csv').open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=SIGNALS)
        writer.writeheader()
        for i in range(population):
            cid = str(uuid.UUID(int=rng.getrandbits(128), version=4))
            if i < len(PERSONAS):
                p = PERSONAS[i]
                age, city, tier = p['age'], p['city'], p['tier']
                turned = int(age == 18 and p['birthday_days_ago'] <= 30)
                claim = int(p['claim_days'] > 0)
                claim_days, documents = p['claim_days'], p['documents']
                surplus, buffer, savings, trend, pressure = (p[k] for k in ('surplus', 'buffer', 'savings', 'trend', 'pressure'))
                travel, insured, products, contacts = (p[k] for k in ('travel', 'insured', 'products', 'contacts'))
            else:
                age = rng.randint(12, 17) if i % 13 == 0 else rng.randint(18, 25) if i % 7 == 0 else rng.randint(26, 85)
                city = rng.choice(['Antwerpen', 'Leuven', 'Brussel', 'Gent', 'Liège'])
                tier = 'service' if age < 18 else rng.choices(['service', 'guidance', 'offers'], [20, 25, 55])[0]
                turned = int(age == 18 and rng.random() < 0.08)
                claim = int(rng.random() < .035)
                claim_days = rng.randint(1, 22) if claim else 0
                documents = rng.randint(1, 3) if claim else 0
                surplus, buffer, savings = rng.randint(-250, 1000), rng.randint(0, 9), rng.randint(0, 32000)
                trend = int(rng.random() < .48)
                pressure = int(surplus < 70 and buffer < 2)
                travel, insured = rng.randint(0, 2500), int(rng.random() < .24)
                products = 'current_account|savings' if age >= 18 else 'youth_account'
                contacts = int(rng.random() < .07)
            if age < 18:
                tier = 'service'
            channels = 'app|email' if age >= 18 else 'app'
            row = dict(customer_id=cid, age=age, age_band=band(age), city=city,
                       turned_18_last_30d=turned, open_insurance_claim=claim,
                       claim_waiting_documents_days=claim_days, claim_documents_needed=documents,
                       monthly_surplus_3m=surplus, savings_buffer_months=buffer, savings_balance=savings,
                       surplus_trend_up_3m=trend, financial_pressure=pressure,
                       travel_spend_12m=travel, has_travel_insurance=insured, products_held=products,
                       contacts_last_30d=contacts, last_contact_campaign='grow_savings' if contacts else '',
                       last_contact_days_ago=10 if contacts else 999, consent_tier=tier,
                       channels_allowed=channels, channel_preference='app', active=1)
            writer.writerow(row)
            age_counts[band(age)] += 1
            if i >= min(profile_count, len(PERSONAS)):
                continue
            ids[p['first_name']] = cid
            customers.append(dict(customer_id=cid, first_name=p['first_name'], age=age, city=city,
                                  language='nl', customer_since='2018-09-01' if i == 0 else '2009-04-20'))
            accounts.append(dict(account_id=str(uuid.UUID(int=rng.getrandbits(128), version=4)), customer_id=cid,
                                 type='youth_account' if i == 0 else 'current_account',
                                 balance_eur=savings, status='active'))
            consents.append(dict(customer_id=cid, tier=tier, channels=channels, personalised_offers=int(tier == 'offers'),
                                 last_changed='2026-07-01'))
            if claim:
                claims.append(dict(claim_id=str(uuid.UUID(int=rng.getrandbits(128), version=4)), customer_id=cid,
                                   type='home_insurance', status='waiting_documents', opened_on='2026-09-11',
                                   days_waiting=claim_days, documents_needed=documents))
            history.append(dict(customer_id=cid, campaign_id='', days_ago=999, feedback='', channel=''))
            # Six months of illustrative transactions ONLY for these two people.
            for month in range(4, 10):
                entries = [('salary_or_allowance', 480 if i == 0 else 2800, 'Income'),
                           ('groceries', -110 if i == 0 else -420, 'Food store'),
                           ('travel', -140 if i == 0 else -210, 'Travel provider'),
                           ('savings', -85 if i == 0 else -120, 'Own savings transfer')]
                if i == 1:
                    entries.extend([('housing', -940, 'Housing'), ('pharmacy', -19, 'Pharmacy'),
                                    ('religious_donation', -12, 'Church donation')])
                for day, (category, amount, description) in enumerate(entries, start=3):
                    transactions.append(dict(transaction_id=str(uuid.UUID(int=rng.getrandbits(128), version=4)),
                                             customer_id=cid, booking_date=str(date(2026, month, day)),
                                             amount_eur=amount, category=category, description=description))
    write_csv(output / 'customers.csv', ['customer_id', 'first_name', 'age', 'city', 'language', 'customer_since'], customers)
    write_csv(output / 'accounts.csv', ['account_id', 'customer_id', 'type', 'balance_eur', 'status'], accounts)
    write_csv(output / 'transactions.csv', ['transaction_id', 'customer_id', 'booking_date', 'amount_eur', 'category', 'description'], transactions)
    write_csv(output / 'insurance_claims.csv', ['claim_id', 'customer_id', 'type', 'status', 'opened_on', 'days_waiting', 'documents_needed'], claims)
    write_csv(output / 'consents.csv', ['customer_id', 'tier', 'channels', 'personalised_offers', 'last_changed'], consents)
    write_csv(output / 'contact_history.csv', ['customer_id', 'campaign_id', 'days_ago', 'feedback', 'channel'], history)
    (output / 'demo_ids.json').write_text(json.dumps(ids, indent=2) + '\n')
    print('Generated', population, 'signal rows and', len(customers), 'six-month personas')
    return age_counts


if __name__ == '__main__':
    generate()
