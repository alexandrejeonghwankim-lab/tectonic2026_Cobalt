"""Strict declarative campaign engine. Never evaluates generated code or raw transactions."""
import csv
import ipaddress
import json
import math
import re
import socket
import time
import urllib.parse
import urllib.request
from collections import Counter
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / 'data'
CAMPAIGNS = ROOT / 'campaigns'
CLOCK = '2026-09-30'
TIERS = {'service': 0, 'guidance': 1, 'offers': 2}
CLASS = {'service': 3, 'guidance': 2, 'offer': 1}
CATALOGUE = {
    'age': ('number', 'guidance', ['target_guidance', 'target_offers'], 'Your age makes this guidance available'),
    'turned_18_last_30d': ('bool', 'guidance', ['target_guidance'], 'You recently turned 18'),
    'open_insurance_claim': ('bool', 'service', ['service_help', 'block_offers'], 'You have an open insurance claim'),
    'claim_waiting_documents_days': ('number', 'service', ['service_help'], 'Your claim has been waiting for documents'),
    'monthly_surplus_3m': ('number', 'guidance', ['target_guidance', 'target_offers'], 'Your estimated monthly surplus'),
    'savings_buffer_months': ('number', 'guidance', ['target_guidance', 'target_offers'], 'Your estimated savings buffer'),
    'savings_balance': ('number', 'offers', ['target_offers'], 'Your available savings balance'),
    'surplus_trend_up_3m': ('bool', 'offers', ['target_offers'], 'Your recent monthly surplus trend'),
    'financial_pressure': ('bool', 'service', ['block_offers', 'prioritise_help'], 'You may benefit from help rather than offers'),
    'travel_spend_12m': ('number', 'offers', ['target_offers'], 'Your annual travel-related spending'),
    'has_travel_insurance': ('bool', 'offers', ['target_offers'], 'Whether travel cover is already held'),
    'products_held': ('string', 'service', ['service_help', 'target_guidance'], 'Your existing products'),
    'contacts_last_30d': ('number', 'service', ['contact_budget'], 'Recent messages from us'),
    'consent_tier': ('string', 'service', ['consent_gate'], 'Your messaging preferences'),
}
FORBIDDEN = {'health_spend_level', 'religious_affiliation'}
META = {key: dict(name=key, type=t, minimum_consent=tier, sensitivity='medium' if key in ('financial_pressure', 'savings_balance', 'travel_spend_12m') else 'low',
                   allowed_uses=uses, forbidden_uses=['target_offers', 'credit_decision', 'insurance_pricing'] if key == 'financial_pressure' else [], description=desc)
        for key, (t, tier, uses, desc) in CATALOGUE.items()}
REQUIRED = {'id','title','source','conditions','combinator','minimum_consent','compliance_class','priority','cooldown_days','channels','message','explanation','action','background','start_date','end_date'}
DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
UNSAFE_COPY = re.compile(r'\b(?:medical|health|pharmacy|diagnos\w*|religio\w*|church|insur\w* pricing|credit decision|eligibilit\w*)\b', re.I)

def reject_request(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 1200:
        raise ValueError('Enter a campaign idea under 1,200 characters.')
    if UNSAFE_COPY.search(text):
        raise ValueError('REJECTED: Sensitive health or religious targeting, pricing or eligibility decisions are not allowed.')

ID = re.compile(r'^[a-z][a-z0-9_]{2,39}$')

def validate(spec):
    if not isinstance(spec, dict) or set(spec) != REQUIRED:
        raise ValueError('Campaign must contain exactly the approved JSON fields.')
    if not isinstance(spec['id'], str) or not ID.fullmatch(spec['id']):
        raise ValueError('Invalid campaign ID.')
    if type(spec['source']) is not str or type(spec['combinator']) is not str or type(spec['compliance_class']) is not str or spec['source'] not in ('library', 'studio') or spec['combinator'] != 'all' or spec['compliance_class'] not in CLASS:
        raise ValueError('Unsupported source, combinator or compliance class.')
    if type(spec['minimum_consent']) is not str or spec['minimum_consent'] not in TIERS or TIERS[spec['minimum_consent']] < TIERS['offers' if spec['compliance_class'] == 'offer' else spec['compliance_class']]:
        raise ValueError('Minimum consent must cover the campaign compliance class.')
    if type(spec['priority']) is not int or not 0 <= spec['priority'] <= 10 or type(spec['cooldown_days']) is not int or not 1 <= spec['cooldown_days'] <= 365:
        raise ValueError('Priority or cooldown out of range.')
    if not isinstance(spec['channels'], list) or not spec['channels'] or len(spec['channels']) > 2 or any(type(c) is not str or c not in ('app','email') for c in spec['channels']) or len(set(spec['channels'])) != len(spec['channels']):
        raise ValueError('Invalid channels.')
    for field in ('title', 'message', 'explanation', 'action'):
        if not isinstance(spec[field], str) or not 1 <= len(spec[field]) <= 360 or any(ord(ch) < 32 and ch not in '\n\t' for ch in spec[field]):
            raise ValueError(f'Invalid {field}.')
    if not isinstance(spec['background'], str) or len(spec['background']) > 350 or not (spec['background'] == 'default' or re.fullmatch(r'/uploads/[a-f0-9]{32}\.(png|jpg|webp)', spec['background'])):
        raise ValueError('Background must be default or a safely uploaded local image.')
    for field in ('start_date', 'end_date'):
        if not isinstance(spec[field], str) or not DATE.fullmatch(spec[field]):
            raise ValueError('Dates must be YYYY-MM-DD.')
        from datetime import date
        try: date.fromisoformat(spec[field])
        except ValueError: raise ValueError('Invalid calendar date.') from None
    if spec['start_date'] > spec['end_date']:
        raise ValueError('Campaign start must precede end.')
    if not isinstance(spec['conditions'], list) or not 1 <= len(spec['conditions']) <= 8:
        raise ValueError('One to eight conditions are required.')
    if spec['compliance_class'] == 'offer' and any(c.get('signal') == 'age' and c.get('operator') in ('<','<=') and type(c.get('value')) in (int, float) and c['value'] <= 18 for c in spec['conditions'] if isinstance(c, dict)):
        raise ValueError('Offers to minors are forbidden.')
    allowed = 'target_offers' if spec['compliance_class'] == 'offer' else 'target_guidance' if spec['compliance_class'] == 'guidance' else 'service_help'
    for c in spec['conditions']:
        if not isinstance(c, dict) or set(c) != {'signal', 'operator', 'value'} or not isinstance(c['signal'], str):
            raise ValueError('Malformed condition.')
        name = c['signal']
        if name in FORBIDDEN:
            raise ValueError('Health and religious signals are forbidden.')
        if name not in META or allowed not in META[name]['allowed_uses']:
            raise ValueError(f'Signal {name} is not approved for {spec["compliance_class"]} targeting.')
        if TIERS[META[name]['minimum_consent']] > TIERS[spec['minimum_consent']]:
            raise ValueError('Signal requires a higher minimum consent tier.')
        typ = META[name]['type']
        if typ == 'number' and (c['operator'] not in ('=','>','>=','<','<=') or type(c['value']) not in (int,float) or not math.isfinite(c['value']) or abs(c['value']) > 1_000_000):
            raise ValueError('Invalid numeric condition.')
        if typ == 'bool' and (c['operator'] != '=' or type(c['value']) is not bool):
            raise ValueError('Invalid boolean condition.')
        if typ == 'string' and (c['operator'] != '=' or not isinstance(c['value'], str) or len(c['value']) > 40):
            raise ValueError('Invalid string condition.')
    # Restrict variables in template copy: no other private fields may be interpolated.
    for field in ('title','message','explanation','action'):
        if UNSAFE_COPY.search(spec[field]):
            raise ValueError('REJECTED: Sensitive medical/religious targeting or eligibility/pricing copy is not allowed.')
        cleaned = spec[field]
        for placeholder in ('first_name', 'n', 'savings_balance', 'monthly_surplus_3m', 'savings_buffer_months'):
            cleaned = cleaned.replace('{' + placeholder + '}', '')
        if '{' in cleaned or '}' in cleaned:
            raise ValueError('Copy can use only {first_name}, {n}, {savings_balance}, {monthly_surplus_3m}, or {savings_buffer_months}.')
    return spec

def safe_public_url(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        return (parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username and not parsed.password
                and not parsed.fragment and not parsed.port and not parsed.hostname.endswith(('.local','.internal'))
                and not parsed.hostname.lower() in ('localhost', 'metadata.google.internal')
                and not is_private_host(parsed.hostname))
    except (ValueError, OSError):
        return False

def is_private_host(host):
    try:
        addresses = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        return not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses)
    except (OSError, ValueError):
        return True

def safe_llm_endpoint(url):
    """Allow only the requested demo host via HTTP, otherwise public HTTPS."""
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/v1','/v1/'):
            return False
        if parsed.scheme == 'http' and parsed.hostname == '100.70.65.86' and parsed.port == 9910:
            return True
        return parsed.scheme == 'https' and parsed.port in (None, 443) and bool(parsed.hostname) and not is_private_host(parsed.hostname)
    except (ValueError, OSError):
        return False

def llm_draft(text, endpoint, model, api_key=''):
    if not isinstance(endpoint, str) or not safe_llm_endpoint(endpoint) or not isinstance(model, str) or not re.fullmatch(r'[\w./-]{1,100}', model):
        raise ValueError('LLM endpoint or model is not allowed; use the prepared examples instead.')
    reject_request(text)
    if api_key and endpoint.startswith('http://'):
        raise ValueError('Never send an API key over HTTP. Use an HTTPS endpoint.')
    example = sample('car' if re.search(r'\b(car|mobility|vehicle|toyota)\b', text, re.I) else 'travel')
    instruction = ('Return exactly one JSON object. Use this valid example schema and realistic value types: ' + json.dumps(example, separators=(',', ':')) + '. ' +
                   'Return only these exact keys: ' + ', '.join(sorted(REQUIRED)) +
                   '. source must be studio; combinator all. Only approved signals: ' + ', '.join(META) +
                   '. Make offer campaigns consent offers and class offer. Never infer health, religion, claims, financial pressure or family status to target offers. '
                   'Background must be default; approved local images are uploaded separately. No credit or insurance eligibility/pricing. '
                   'For travel requests produce summer_travel; for car/mobility requests produce mobility_partner; otherwise reject by returning {}. '
                   'Use {first_name} and optionally {n} only as placeholders. Fixed demo date 2026-09-30.')
    body = json.dumps({'model': model, 'temperature': 0, 'max_tokens': 1500, 'messages': [{'role':'system','content':instruction}, {'role':'user','content':text}]}).encode()
    if len(body) > 6000:
        raise ValueError('Request too long.')
    url = endpoint.rstrip('/') + '/chat/completions'
    req = urllib.request.Request(url, data=body, headers={'Content-Type':'application/json', **({'Authorization':'Bearer ' + api_key} if api_key else {})})
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            raise ValueError('Redirects are disabled for LLM endpoints.')
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect).open(req, timeout=30) as resp:
            if int(resp.headers.get('Content-Length','0')) > 16000:
                raise ValueError('LLM response too large.')
            payload = resp.read(16001)
            if len(payload) > 16000: raise ValueError('LLM response too large.')
            draft = json.loads(json.loads(payload)['choices'][0]['message']['content'])
        try:
            return validate(draft)
        except ValueError:
            raise ValueError('LLM returned a rule that failed governance; edit and validate a prepared draft.') from None
    except (KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError('LLM returned invalid JSON; use a prepared draft.') from None
    except Exception as exc:
        if isinstance(exc, ValueError): raise
        raise ValueError('LLM request failed; use a prepared draft or check the endpoint.') from None

def sample(key='travel'):
    with (CAMPAIGNS / ('car_example.json' if key == 'car' else 'travel_example.json')).open(encoding='utf-8') as file:
        return validate(json.load(file))

def library():
    return [validate(json.loads(p.read_text())) for p in sorted((CAMPAIGNS/'library').glob('*.json'))]

def registered():
    result = []
    for path in sorted((CAMPAIGNS/'registry').glob('*.json')):
        try:
            spec = validate(json.loads(path.read_text()))
            if spec['source'] == 'studio': result.append(spec)
        except (ValueError, KeyError, json.JSONDecodeError):
            continue
    return result

def save_approved(spec):
    validate(spec)
    if spec['source'] != 'studio': raise ValueError('Only employee studio campaigns can be saved.')
    if any(x['id'] == spec['id'] for x in library()): raise ValueError('Cannot overwrite a library campaign.')
    path = CAMPAIGNS / 'registry' / (spec['id'] + '.json')
    path.parent.mkdir(exist_ok=True)
    # atomic, with only allowlisted file name; no arbitrary paths.
    tmp = path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(spec, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)

@lru_cache(maxsize=1)
def population():
    with (DATA/'customer_signals.csv').open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

@lru_cache(maxsize=1)
def profiles():
    with (DATA/'customers.csv').open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def active(spec, at=CLOCK):
    return spec['start_date'] <= at <= spec['end_date']

def matches(row, spec, at=CLOCK):
    if not active(spec, at): return False
    for c in spec['conditions']:
        raw = row.get(c['signal'], '')
        if raw is None or str(raw).strip() == '': return False  # Unknown is never a positive match.
        typ = META[c['signal']]['type']
        value = float(raw) if typ == 'number' else raw in ('1','true','True') if typ == 'bool' else raw
        target = float(c['value']) if typ == 'number' else c['value']
        op = c['operator']
        if not {'=':lambda:value == target, '>':lambda:value > target, '>=':lambda:value >= target,
                '<':lambda:value < target, '<=':lambda:value <= target}[op](): return False
    return True

def gate(row, spec, irrelevant=frozenset(), optouts=frozenset()):
    if row['customer_id'] in optouts and spec['compliance_class'] != 'service': return 'Personalisation turned off'
    if row['customer_id'] + ':' + spec['id'] in irrelevant: return 'Marked not relevant'
    if row.get('active') != '1': return 'Inactive account'
    if int(row['age']) < 18 and spec['compliance_class'] != 'service': return 'Age protection'
    if TIERS[row['consent_tier']] < TIERS[spec['minimum_consent']]: return 'Insufficient consent'
    if not set(spec['channels']).intersection(row['channels_allowed'].split('|')): return 'No allowed channel'
    if spec['compliance_class'] == 'offer' and (row.get('open_insurance_claim') != '0' or row.get('financial_pressure') != '0'):
        return 'Open claim / financial pressure unknown or flagged; blocks offers'
    if row.get('last_contact_campaign') == spec['id'] and row.get('last_contact_days_ago') and int(row['last_contact_days_ago']) < spec['cooldown_days']:
        return 'Campaign cooldown'
    if spec['compliance_class'] != 'service' and (not str(row.get('contacts_last_30d', '')).strip() or int(row['contacts_last_30d']) >= 1):
        return 'Contact budget (one per 30 days)'
    return ''

def decision(row, campaigns, irrelevant=frozenset(), optouts=frozenset(), at=CLOCK):
    """Return winner, and every matched competitor with exact suppression reason."""
    passed, suppressed, matched = [], [], []
    for spec in campaigns:
        validate(spec)
        if not matches(row, spec, at): continue
        matched.append(spec)
        reason = gate(row, spec, irrelevant, optouts)
        if reason: suppressed.append(dict(title=spec['title'], source=spec['source'], reason=reason, id=spec['id'], passed=False))
        else: passed.append(spec)
    passed.sort(key=lambda s: (-CLASS[s['compliance_class']], -s['priority'], -max(int(row.get('claim_waiting_documents_days') or 0) if c['signal'] == 'claim_waiting_documents_days' else 1 for c in s['conditions']), s['id']))
    winner = passed[0] if passed else None
    for spec in passed[1:]:
        suppressed.append(dict(title=spec['title'], source=spec['source'], id=spec['id'], passed=True,
            reason='Higher-class help takes priority' if CLASS[winner['compliance_class']] > CLASS[spec['compliance_class']] else 'One-message contact budget / higher priority'))
    return winner, suppressed, matched

def persona(name, campaigns, irrelevant=frozenset(), optouts=frozenset()):
    if name not in ('Emma', 'Marc'):
        raise ValueError('Only the two prepared fictional personas can be viewed.')
    person = next(p for p in profiles() if p['first_name'] == name)
    row = next(r for r in population()[:2] if r['customer_id'] == person['customer_id'])
    winner, suppressed, matched = decision(row, campaigns, irrelevant, optouts)
    n = int(row['claim_documents_needed'])
    return dict(name=name, city=person['city'], age=int(row['age']), consent=row['consent_tier'], customer_id=row['customer_id'],
                title=winner['title'] if winner else 'No message right now', source=winner['source'] if winner else '',
                message=winner['message'].replace('{first_name}', name).replace('{n}', str(n)) if winner else 'We will stay quiet until there is something useful to say.',
                explanation=winner['explanation'].replace('{first_name}', name).replace('{n}', str(n)) if winner else '',
                action=winner['action'] if winner else '', background=winner['background'] if winner else 'default',
                id=winner['id'] if winner else '', matched=[dict(title=s['title'], source=s['source'], passed=not bool(gate(row,s,irrelevant,optouts)),
                                                               gate=gate(row,s,irrelevant,optouts) or 'Passed consent + governance') for s in matched],
                signals=[META[c['signal']]['description'] for c in winner['conditions']] if winner else [], suppressed=suppressed, sent=bool(winner))

def backtest(spec, live):
    validate(spec)
    counters = Counter()
    channels = Counter()
    start = time.perf_counter()
    simulation_date = max(CLOCK, spec['start_date'])
    for row in population():
        if not matches(row, spec, simulation_date): continue
        counters['matches'] += 1
        reason = gate(row, spec)
        if reason:
            counters[reason] += 1
            continue
        winner, _, _ = decision(row, [spec, *live], at=simulation_date)
        if winner and winner['id'] != spec['id']:
            counters['Other campaign won'] += 1
        elif winner:
            counters['selected'] += 1
            chosen = row['channel_preference'] if row['channel_preference'] in spec['channels'] else spec['channels'][0]
            channels[chosen] += 1
    return dict(matches=counters['matches'], selected=counters['selected'], removed_consent=counters['Insufficient consent'] + counters['Age protection'] + counters['No allowed channel'],
                removed_cooldown=counters['Campaign cooldown'] + counters['Contact budget (one per 30 days)'],
                removed_protected=counters['Open claim / financial pressure unknown or flagged; blocks offers'], suppressed=counters['Other campaign won'],
                by_channel=dict(channels), silent_pct=round(100*(counters['matches']-counters['selected'])/max(counters['matches'],1),1),
                milliseconds=round((time.perf_counter()-start)*1000), population=len(population()), simulation_date=simulation_date)
