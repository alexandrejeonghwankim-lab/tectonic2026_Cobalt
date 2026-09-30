"""Live workbench operations. No persona-specific decision branches or LLM per customer."""
import csv
import json
import math
import random
import re
import secrets
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from functools import lru_cache
from datetime import date, timedelta
from pathlib import Path
import campaign_engine as engine
from generate_data import SIGNALS

ROOT = Path(__file__).resolve().parent
LABELS = {
    'age': 'Age', 'turned_18_last_30d': 'Turned 18 this month',
    'open_insurance_claim': 'Open insurance claim', 'claim_waiting_documents_days': 'Days waiting for claim documents',
    'monthly_surplus_3m': 'Average monthly money left over (€)', 'savings_buffer_months': 'Savings buffer (months)',
    'savings_balance': 'Savings balance (€)', 'surplus_trend_up_3m': 'Monthly surplus increasing over 3 months',
    'financial_pressure': 'Financial pressure flag', 'travel_spend_12m': 'Travel spending over 12 months (€)',
    'has_travel_insurance': 'Already has travel insurance', 'products_held': 'Products held',
    'contacts_last_30d': 'Messages in the last 30 days', 'consent_tier': 'Permission for messages',
}
STATUS = ROOT / 'campaigns' / 'status.json'
EXTRA = ROOT / 'data' / 'test_customers.csv'
OFFER_SIGNALS = {k:v for k,v in engine.META.items() if 'target_offers' in v['allowed_uses']}
# Business-friendly labels; explanations below always contain exact CSV values.
OP = {'=': 'is', '>': 'more than', '>=': 'at least', '<': 'less than', '<=': 'at most'}


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, encoding='utf-8', delete=False) as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        name = f.name
    Path(name).replace(path)


def paused_ids():
    if not STATUS.exists(): return set()
    return set(json.loads(STATUS.read_text()).get('paused', []))


def set_paused(cid, paused):
    if cid not in {x['id'] for x in all_campaigns()}: raise ValueError('Campaign not found.')
    ids = paused_ids()
    ids.add(cid) if paused else ids.discard(cid)
    atomic_json(STATUS, {'paused': sorted(ids)})


def all_campaigns():
    return [*engine.library(), *engine.registered()]


def running_campaigns():
    paused = paused_ids()
    return [x for x in all_campaigns() if x['id'] not in paused]


ACTIVE = ROOT / 'data' / 'active_customers.csv'
REQUIRED_COLUMNS = {'customer_id', 'age', 'consent_tier'}
# Only approved, synthetic signal columns and optional display fields enter the engine.
ALLOWED_COLUMNS = set(SIGNALS) | {'first_name'}
BOOL_COLUMNS = {'turned_18_last_30d','open_insurance_claim','surplus_trend_up_3m',
                'financial_pressure','has_travel_insurance','active'}
NUM_COLUMNS = {k for k,v in engine.META.items() if v['type'] == 'number'} | {
    'claim_documents_needed','last_contact_days_ago'}


def validate_customer(row, number):
    if not all(str(row.get(k, '') or '').strip() for k in REQUIRED_COLUMNS):
        raise ValueError(f'Row {number}: customer_id, age and consent_tier are required.')
    clean = {k: (str(row.get(k) or '').strip() if row.get(k) is not None else '') for k in ALLOWED_COLUMNS}
    if len(clean['customer_id']) > 80 or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', clean['customer_id']):
        raise ValueError(f'Row {number}: invalid opaque customer_id.')
    if not clean['age'].isdigit() or not 12 <= int(clean['age']) <= 100:
        raise ValueError(f'Row {number}: age must be 12–100.')
    if clean['consent_tier'] not in engine.TIERS:
        raise ValueError(f'Row {number}: consent_tier must be service, guidance or offers.')
    if len(clean['first_name']) > 40 or len(clean['city']) > 60:
        raise ValueError(f'Row {number}: name or city is too long.')
    for k in BOOL_COLUMNS:
        if clean[k].lower() in ('yes','true'): clean[k] = '1'
        if clean[k].lower() in ('no','false'): clean[k] = '0'
        if clean[k] and clean[k] not in ('0','1'):
            raise ValueError(f'Row {number}: {k} must be yes/no or 0/1.')
    for k in NUM_COLUMNS:
        if clean[k]:
            try: value = float(clean[k])
            except ValueError: raise ValueError(f'Row {number}: {k} must be numeric.') from None
            if not math.isfinite(value) or abs(value) > 1_000_000:
                raise ValueError(f'Row {number}: {k} is outside supported bounds.')
    if clean['contacts_last_30d'] and (float(clean['contacts_last_30d']) < 0 or not float(clean['contacts_last_30d']).is_integer()):
        raise ValueError(f'Row {number}: contacts_last_30d must be a nonnegative whole number.')
    if clean['last_contact_days_ago'] and (float(clean['last_contact_days_ago']) < 0 or not float(clean['last_contact_days_ago']).is_integer()):
        raise ValueError(f'Row {number}: last_contact_days_ago must be a nonnegative whole number.')
    if clean['age_band'] == '':
        age = int(clean['age'])
        clean['age_band'] = 'under 18' if age < 18 else '18–25' if age <= 25 else '26–64' if age < 65 else '65+'
    if int(clean['age']) < 18 and clean['consent_tier'] != 'service':
        raise ValueError(f'Row {number}: minors must use service-only consent.')
    # These non-sensitive defaults may be inferred safely. Unknown protective
    # fields remain blank: they MUST NOT turn into an offer or a positive match.
    clean['active'] = clean['active'] or '1'
    clean['channels_allowed'] = clean['channels_allowed'] or 'app'
    clean['channel_preference'] = clean['channel_preference'] or 'app'
    if set(clean['channels_allowed'].split('|')) - {'app','email'}:
        raise ValueError(f'Row {number}: channels_allowed must be app or email.')
    if clean['channel_preference'] not in ('app','email'):
        raise ValueError(f'Row {number}: invalid channel_preference.')
    if clean['last_contact_campaign'] and not re.fullmatch(r'[a-z][a-z0-9_]{2,39}', clean['last_contact_campaign']):
        raise ValueError(f'Row {number}: invalid last_contact_campaign.')
    return clean


def parse_customers(source):
    with source.open(newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(reader.fieldnames) or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError('CSV needs customer_id, age and consent_tier headers (other signal columns are optional).')
        result, seen = [], set()
        for i, row in enumerate(reader, 1):
            if i > 150_000: raise ValueError('Use 150,000 customer rows or fewer for this demo.')
            if None in row: raise ValueError(f'Row {i}: extra cells in CSV.')
            normalized = validate_customer(row, i)
            cid = normalized['customer_id']
            if cid in seen: raise ValueError(f'Row {i}: duplicate customer_id.')
            seen.add(cid)
            result.append(normalized)
    if not result: raise ValueError('CSV must contain at least one customer row.')
    return result


@lru_cache(maxsize=4)
def _read_customers(path, modified, size, extra_modified, extra_size):
    # Stats are part of the cache key: replacing a CSV updates every screen
    # and the backtest without restarting the server.
    result = parse_customers(Path(path))
    if extra_size:
        with EXTRA.open(newline='', encoding='utf-8-sig') as f:
            existing = set(row['customer_id'] for row in result)
            for i, row in enumerate(csv.DictReader(f), len(result) + 1):
                normalized = validate_customer(row, i)
                if normalized['customer_id'] in existing: raise ValueError(f'Row {i}: duplicate customer_id.')
                result.append(normalized); existing.add(normalized['customer_id'])
    return result


def all_customers():
    source = ACTIVE if ACTIVE.exists() else ROOT / 'data' / 'customer_signals.csv'
    stat = source.stat()
    extra = EXTRA.stat() if EXTRA.exists() else None
    return _read_customers(str(source), stat.st_mtime_ns, stat.st_size,
                           extra.st_mtime_ns if extra else 0, extra.st_size if extra else 0)


def import_customers(data):
    if not data or len(data) > 32_000_000: raise ValueError('Select a UTF-8 CSV up to 32 MB.')
    ACTIVE.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('wb', dir=ACTIVE.parent, delete=False) as f:
        f.write(data); candidate = Path(f.name)
    try:
        rows = parse_customers(candidate)
        # Keep an existing dataset recoverable when a judge imports another.
        if ACTIVE.exists(): ACTIVE.replace(ACTIVE.with_name('active_customers.backup.' + str(time.time_ns()) + '.csv'))
        candidate.replace(ACTIVE)
        _read_customers.cache_clear()
        return len(rows)
    finally:
        candidate.unlink(missing_ok=True)


def reset_customers():
    if ACTIVE.exists(): ACTIVE.replace(ACTIVE.with_name('active_customers.backup.' + str(time.time_ns()) + '.csv'))
    _read_customers.cache_clear()
    return len(all_customers())


def customer_name(row, number):
    if row.get('first_name'): return row['first_name']
    if ACTIVE.exists(): return f'Customer {number:,}'
    names = {p['customer_id']: p['first_name'] for p in engine.profiles()}
    return names.get(row['customer_id'], f'Customer {number:,}')


def render_message(spec, row, number):
    values = {'first_name':customer_name(row, number), 'n':row.get('claim_documents_needed',''),
              'savings_balance':row.get('savings_balance',''),
              'monthly_surplus_3m':row.get('monthly_surplus_3m',''),
              'savings_buffer_months':row.get('savings_buffer_months','')}
    message = spec['message']
    for key, value in values.items(): message = message.replace('{' + key + '}', str(value) if str(value).strip() else 'not available')
    return message


def display_value(signal, value):
    if value is None or str(value).strip() == '': return 'Unknown (not provided)'
    if engine.META.get(signal, {}).get('type') == 'bool':
        return 'Yes' if value in (True, '1', 'true', 'True') else 'No'
    return str(value)


def describe_condition(c):
    return f"{LABELS.get(c['signal'], c['signal'])} {OP[c['operator']]} {display_value(c['signal'], c['value'])}"


def condition_passes(row, c):
    kind = engine.META[c['signal']]['type']
    raw = row.get(c['signal'], '')
    if raw in (None, ''): return False
    val = float(raw) if kind == 'number' else raw in ('1','true','True') if kind == 'bool' else raw
    target = c['value']
    return {'=': lambda: val == target, '>': lambda: val > target, '>=': lambda: val >= target,
            '<': lambda: val < target, '<=': lambda: val <= target}[c['operator']]()


def audit_customer(row, campaigns, at):
    date.fromisoformat(at)
    winner, suppressed, _ = engine.decision(row, campaigns, at=at)
    reasons = {x['id']: x['reason'] for x in suppressed}
    audits = []
    for spec in campaigns:
        checks = [{ 'rule': describe_condition(c), 'actual': display_value(c['signal'], row.get(c['signal'], '') or 'Not provided'),
                    'passed': condition_passes(row, c), 'column': c['signal']} for c in spec['conditions']]
        status = 'Selected' if winner and winner['id'] == spec['id'] else 'Not matched'
        reason = 'Highest-priority eligible campaign; one message selected.' if status == 'Selected' else 'One or more audience conditions failed.'
        if not engine.active(spec, at): status, reason = 'Outside dates', f"Runs {spec['start_date']} to {spec['end_date']}"
        elif spec['id'] in reasons: status, reason = 'Suppressed', reasons[spec['id']]
        audits.append(dict(id=spec['id'], title=spec['title'], status=status, reason=reason, checks=checks))
    return winner, audits


def backtest(spec, live, rows=None, at=None):
    """All counts derive from the supplied rows, never from demonstration personas."""
    engine.validate(spec)
    live = [x for x in live if x['id'] != spec['id']]
    for other in live: engine.validate(other)
    rows = all_customers() if rows is None else rows
    at = at or max(engine.CLOCK, spec['start_date'])
    date.fromisoformat(at)
    counts = Counter(); samples = []; matched_samples = []; started = time.perf_counter()
    for i, row in enumerate(rows, 1):
        if not engine.matches(row, spec, at): continue
        counts['matched'] += 1
        if len(matched_samples) < 12: matched_samples.append(i)
        reason = engine.gate(row, spec)
        if reason:
            counts[reason] += 1
            continue
        counts['eligible'] += 1
        winner, _, _ = engine.decision(row, [spec, *live], at=at)
        if winner and winner['id'] == spec['id']:
            counts['selected'] += 1
            if len(samples) < 20: samples.append(i)
        else: counts['Other campaign takes priority'] += 1
    return dict(population=len(rows), matched=counts['matched'], eligible=counts['eligible'], selected=counts['selected'],
                excluded=counts['matched']-counts['selected'], not_matched=len(rows)-counts['matched'],
                reasons={k:v for k,v in counts.items() if k not in ('matched','eligible','selected')},
                samples=samples, matched_samples=matched_samples, at=at, milliseconds=round((time.perf_counter()-started)*1000))


def request_json(endpoint, model, key, system, prompt):
    if not isinstance(endpoint,str) or not engine.safe_llm_endpoint(endpoint):
        raise ValueError('Use the supplied keyless endpoint or a public HTTPS OpenAI-compatible endpoint ending in /v1.')
    if not re.fullmatch(r'[\w./-]{1,100}', model): raise ValueError('Enter a valid model identifier in Settings.')
    if key and not endpoint.startswith('https://'): raise ValueError('API keys require an HTTPS endpoint. Leave key empty for the supplied keyless endpoint.')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs): raise ValueError('LLM redirects are not allowed.')
    body = json.dumps({'model':model, 'temperature':0, 'max_tokens':3500, 'messages':[{'role':'system','content':system},{'role':'user','content':prompt}]}).encode()
    headers = {'Content-Type':'application/json'}
    if key: headers['Authorization'] = 'Bearer ' + key
    req = urllib.request.Request(endpoint.rstrip('/') + '/chat/completions', data=body, headers=headers)
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect).open(req, timeout=60) as response:
            raw = response.read(65_537)
        if len(raw) > 65_536: raise ValueError('LLM response is too large.')
        text = json.loads(raw)['choices'][0]['message']['content'].strip()
        if text.startswith('```'): text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text)
        return json.loads(text)
    except urllib.error.HTTPError as exc:
        raise ValueError(f'LLM returned HTTP {exc.code}. Check endpoint/model in Settings. No campaign was saved.') from None
    except (TimeoutError, urllib.error.URLError):
        raise ValueError('LLM did not respond within 60 seconds. Retry or use a labelled offline example.') from None
    except (KeyError, IndexError, TypeError, AttributeError, json.JSONDecodeError):
        raise ValueError('LLM response was not valid structured JSON. No campaign was saved; please retry.') from None


def build_spec(label, message, image, conditions, start, end, cid=None):
    spec = {**engine.sample('travel'), 'id':cid or 'studio_' + uuid.uuid4().hex[:16], 'title':label.strip(),
            'message':message.strip(), 'explanation':'You allowed offers. This campaign matches the audience conditions shown below.',
            'action':'View offer details', 'background':image, 'conditions':conditions, 'start_date':start, 'end_date':end}
    engine.validate(spec)
    if image != 'default' and not (ROOT/'assets'/image.lstrip('/')).is_file(): raise ValueError('Campaign image is missing. Upload it again.')
    return spec


def ai_audience(label, message, prompt, image, endpoint, model, key=''):
    engine.reject_request(prompt)
    # Copy is preserved exactly, not rewritten by the model; no customer data is sent.
    fields = {k:dict(type=v['type'], label=LABELS[k]) for k,v in OFFER_SIGNALS.items()}
    system = ('You translate a bank employee audience request into safe declarative filters, NOT executable code. '
              'Return ONLY JSON with exact keys conditions, start_date, end_date, assumptions. '
              'conditions is an AND list of 1-8 objects {signal, operator, value}. Approved signal catalogue: '+json.dumps(fields)+'. '
              'Numbers use = > >= < <= and numeric values; booleans use = and true/false. '
              'Dates YYYY-MM-DD; simulation today is '+engine.CLOCK+'. If no dates are requested start today and end 2027-12-31. '
              'If October-November is requested use 2026-10-01 to 2026-11-30. '
              'Never claim a car market price is researched: when price unspecified use an explicit ILLUSTRATIVE EUR 18000 savings threshold and disclose it in assumptions. '
              'surplus_trend_up_3m is a synthetic trend, NOT a future balance prediction. If request needs an unavailable signal return {"error":"explain missing signal"}. '
              'Do not infer health, religion, creditworthiness, loan approval or purchase intent. '
              'assumptions is a list of up to 5 short strings describing assumptions/ambiguities (e.g. adult age boundary). '
              'Example: {"conditions":[{"signal":"age","operator":">=","value":18},{"signal":"age","operator":"<","value":30},{"signal":"savings_balance","operator":">=","value":18000},{"signal":"surplus_trend_up_3m","operator":"=","value":true}],"start_date":"2026-10-01","end_date":"2026-11-30","assumptions":["EUR 18000 is an illustrative threshold, not a researched Brussels car price."]}')
    answer = request_json(endpoint, model, key, system, prompt)
    if not isinstance(answer,dict): raise ValueError('AI returned an invalid filter format. Retry.')
    if 'error' in answer: raise ValueError('This audience needs a signal not available in the mock dataset. Rephrase using age, savings, rising surplus, travel spend or existing travel cover.')
    if set(answer) != {'conditions','start_date','end_date','assumptions'}: raise ValueError('AI returned an incomplete filter format. Retry.')
    notes = answer['assumptions']
    if not isinstance(notes,list) or len(notes)>5 or any(not isinstance(x,str) or len(x)>400 for x in notes): raise ValueError('AI assumptions were malformed. Retry.')
    spec = build_spec(label,message,image,answer['conditions'],answer['start_date'],answer['end_date'])
    return spec, notes


BATCH_KEYS = {'age','city','savings_balance','monthly_surplus_3m','surplus_trend_up_3m','consent_tier',
              'open_insurance_claim','financial_pressure','travel_spend_12m','has_travel_insurance','contacts_last_30d'}


def validate_fake_batch(items):
    if not isinstance(items,list) or not 1 <= len(items) <= 10: raise ValueError('Expected 1–10 fake customers.')
    rows = []
    for item in items:
        if not isinstance(item,dict) or set(item) != BATCH_KEYS: raise ValueError('AI customer fields did not match the allowed schema; nothing was saved.')
        for key in ('age','contacts_last_30d'):
            if type(item[key]) is not int: raise ValueError('Age/contact count must be integers.')
        if not 12<=item['age']<=100 or not 0<=item['contacts_last_30d']<=20: raise ValueError('Age/contact count out of bounds.')
        for key in ('savings_balance','monthly_surplus_3m','travel_spend_12m'):
            value = item[key]
            if type(value) not in (int,float) or not math.isfinite(value) or not (-10000 if key=='monthly_surplus_3m' else 0)<=value<=1_000_000: raise ValueError('Invalid fake financial value.')
        for key in ('surplus_trend_up_3m','open_insurance_claim','financial_pressure','has_travel_insurance'):
            if type(item[key]) is not bool: raise ValueError('Customer flags must be booleans.')
        if item['consent_tier'] not in engine.TIERS or not isinstance(item['city'],str) or not re.fullmatch(r"[\w À-ÿ'-]{1,40}", item['city']): raise ValueError('Invalid fictional city or consent.')
        row = {k:str(v) for k,v in item.items()}
        for key in ('surplus_trend_up_3m','open_insurance_claim','financial_pressure','has_travel_insurance'): row[key] = str(int(item[key]))
        age = item['age']
        if age<18: row['consent_tier']='service'
        row.update(customer_id=str(uuid.uuid4()), age_band='under 18' if age<18 else '18–25' if age<=25 else '26–64' if age<65 else '65+',
                   turned_18_last_30d='0', claim_waiting_documents_days='12' if item['open_insurance_claim'] else '0',
                   claim_documents_needed='2' if item['open_insurance_claim'] else '0', savings_buffer_months='3',
                   products_held='current_account|savings', last_contact_campaign='', last_contact_days_ago='999',
                   channels_allowed='app|email', channel_preference='app',active='1')
        rows.append(row)
    return rows


def ai_customers(prompt, endpoint, model, key=''):
    if not prompt.strip() or len(prompt)>1200: raise ValueError('Describe the fake customer group in under 1,200 characters.')
    example = dict(age=27,city='Brussel',savings_balance=20000,monthly_surplus_3m=180,surplus_trend_up_3m=True,
                   consent_tier='offers',open_insurance_claim=False,financial_pressure=False,travel_spend_12m=400,
                   has_travel_insurance=False,contacts_last_30d=0)
    system = ('Generate exactly 10 entirely fictional customer signal records for software testing. No real people or identifiers. '
              'Return JSON {"customers":[...]} with every object having EXACTLY the keys and JSON types in this example: '+json.dumps(example)+'. '
              'Age integer 12-100; contacts_last_30d integer 0-20; savings/travel non-negative EUR; surplus -10000 to 1000000. '
              'Boolean fields must be JSON true/false. consent_tier service, guidance or offers; minors must use service. '
              'Vary the records to include positive and negative test cases. No health/religious data.')
    result = request_json(endpoint,model,key,system,prompt)
    if not isinstance(result,dict) or set(result)!={'customers'}: raise ValueError('AI returned invalid customer JSON. Nothing was saved.')
    return validate_fake_batch(result['customers'])


def append_customers(rows):
    # Only newly generated records are persisted; the 100k base CSV is never overwritten.
    fields = list(engine.population()[0])
    previous = []
    if EXTRA.exists():
        with EXTRA.open(newline='',encoding='utf-8') as f: previous=list(csv.DictReader(f))
    EXTRA.parent.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile('w',dir=EXTRA.parent,encoding='utf-8',newline='',delete=False) as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows([*previous,*rows]); name=f.name
    Path(name).replace(EXTRA)


def override_customer(row, fields):
    copy = dict(row)
    try:
        age = int(fields['age']); savings=float(fields['savings']); surplus=float(fields['surplus']); travel=float(fields['travel'])
        contacts=int(fields['contacts'])
        if not 12<=age<=100 or not all(math.isfinite(v) for v in (savings,surplus,travel)) or not 0<=savings<=1_000_000 or not -10000<=surplus<=1_000_000 or not 0<=travel<=1_000_000 or not 0<=contacts<=20: raise ValueError()
        consent=fields['consent']
        if consent not in engine.TIERS: raise ValueError()
        def flag(k):
            if fields[k] not in ('Yes','No'): raise ValueError()
            return '1' if fields[k]=='Yes' else '0'
        copy.update(age=str(age), savings_balance=str(savings), monthly_surplus_3m=str(surplus),travel_spend_12m=str(travel),
                    contacts_last_30d=str(contacts),consent_tier='service' if age<18 else consent,surplus_trend_up_3m=flag('trend'),
                    open_insurance_claim=flag('claim'), financial_pressure=flag('pressure'),has_travel_insurance=flag('insured'))
        # Do not let an old life-event flag contradict an overridden age.
        if age!=18: copy['turned_18_last_30d']='0'
        if copy['open_insurance_claim']=='0': copy['claim_waiting_documents_days']='0';copy['claim_documents_needed']='0'
        return copy
    except (ValueError,TypeError,KeyError): raise ValueError('Check age 12–100, money values, message count 0–20 and all selections.') from None
