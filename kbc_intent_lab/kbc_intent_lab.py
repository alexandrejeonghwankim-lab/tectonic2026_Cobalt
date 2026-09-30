"""KBC-inspired local synthetic campaign workbench; no login or customer deliveries."""
import asyncio
import json
import uuid
from pathlib import Path

import reflex as rx

import campaign_engine as engine
import workbench as wb

BLUE, STONE, INK, MUTED, BORDER, BG = '#0097DB', '#005D72', '#18374A', '#657F8E', '#DFEBF1', '#F4F9FB'
ROOT = Path(__file__).resolve().parent.parent


class State(rx.State):
    page: str = 'Campaigns'
    label: str = ''
    message: str = ''
    ai_prompt: str = ''
    image_path: str = 'default'
    start_date: str = '2026-09-30'
    end_date: str = '2027-12-31'
    audience_status: str = 'No audience yet. Use AI or load an offline example.'
    audience_rules: list[str] = []
    assumptions: list[str] = []
    busy: bool = False
    busy_task: str = ''
    error: str = ''
    notice: str = ''
    review_ready: bool = False
    review_rows: list[dict[str, str]] = []
    sample_indexes: list[int] = []
    sample_date: str = engine.CLOCK
    preview_date: str = engine.CLOCK
    registry_rows: list[dict[str, str]] = []
    chosen_index: int = 0
    lookup_index: str = '1'
    page_number: int = 0
    browser_rows: list[dict[str, str]] = []
    dataset_size: str = ''
    dataset_origin: str = ''
    customer_label: str = ''
    customer_id: str = ''
    customer_age: str = ''
    customer_city: str = ''
    customer_consent: str = ''
    customer_features: list[dict[str, str]] = []
    customer_title: str = ''
    customer_message: str = ''
    customer_background: str = 'default'
    customer_reason: str = ''
    customer_audit: list[dict[str, str]] = []
    what_signal: str = 'savings_balance'
    what_value: str = ''
    what_changed: bool = False
    llm_endpoint: str = 'http://100.70.65.86:9910/v1'
    llm_model: str = 'gpt-6-sol'
    key_status: str = 'No API key stored. The default endpoint is keyless.'
    _key: str = ''
    _audience: dict = {}
    _reviewed: dict = {}
    _overrides: dict = {}

    def initialize(self):
        self.refresh_registry()
        self.reload_customers()

    def reload_customers(self):
        try:
            rows = wb.all_customers()
            self.dataset_size = f'{len(rows):,}'
            self.dataset_origin = 'Imported CSV (names and rules read live)' if wb.ACTIVE.exists() else 'data/customer_signals.csv (original synthetic dataset)'
            self.page_number = 0
            self.lookup_index = '1'
            self.invalidate()
            self.inspect(0)
            self.notice = 'Loaded ' + self.dataset_size + ' actual CSV rows. Future backtests use this dataset. Nothing was sent.'
        except (ValueError, OSError, UnicodeError) as exc:
            self.error = str(exc)

    async def import_dataset(self, files: list[rx.UploadFile]):
        if self.busy: return
        if len(files) != 1:
            self.error = 'Select exactly one CSV file first.'
            return
        if not files[0].filename.lower().endswith('.csv') or (files[0].size and files[0].size > 32_000_000):
            self.error = 'Only a UTF-8 CSV under 32 MB can be imported.'
            return
        try:
            count = await asyncio.to_thread(wb.import_customers, await files[0].read())
            self.reload_customers()
            self.notice = f'Imported and evaluated {count:,} rows. Names, decisions and backtests now use the imported dataset. The original CSV is untouched.'
        except (ValueError, OSError, UnicodeError) as exc:
            self.error = str(exc)

    def restore_dataset(self):
        if self.busy: return
        try:
            wb.reset_customers()
            self.reload_customers()
            self.notice = 'Switched back to the original synthetic dataset. The prior import was moved to a backup file.'
        except (ValueError, OSError) as exc:
            self.error = str(exc)

    def go(self, page: str):
        if page not in ('Campaigns', 'Test customers', 'Registry', 'Governance', 'Settings', 'Help'):
            return
        self.page = page
        self.error = ''
        self.notice = ''
        if page == 'Registry': self.refresh_registry()
        if page == 'Test customers':
            self.chosen_index = min(self.chosen_index, len(wb.all_customers())-1)
            self.inspect(self.chosen_index)

    def set_label(self, value: str):
        if self.busy: return
        self.label = value
        self.invalidate()

    def set_message(self, value: str):
        if self.busy: return
        self.message = value
        self.invalidate()

    def set_ai_prompt(self, value: str):
        if self.busy: return
        self.ai_prompt = value
        self._audience = {}
        self.audience_rules = []
        self.assumptions = []
        self.audience_status = 'AI audience prompt changed. Click Draft audience to propose new filters.'
        self.invalidate()

    def set_start_date(self, value: str):
        if self.busy: return
        self.start_date = value
        self.invalidate()

    def set_end_date(self, value: str):
        if self.busy: return
        self.end_date = value
        self.invalidate()

    def invalidate(self):
        self.review_ready = False
        self._reviewed = {}
        self.review_rows = []
        self.sample_indexes = []
        self.error = ''

    def example(self, name: str):
        if self.busy or name not in ('travel', 'car'): return
        spec = {**engine.sample(name), 'id': 'studio_' + uuid.uuid4().hex[:16]}
        self.label, self.message = spec['title'], spec['message']
        self._audience = spec
        self.start_date, self.end_date = spec['start_date'], spec['end_date']
        self.image_path = 'default'
        self.ai_prompt = ''
        self.audience_rules = [wb.describe_condition(c) for c in spec['conditions']]
        self.assumptions = ['Offline example: these rules are from a reviewed JSON template, NOT generated by AI.']
        self.audience_status = 'Offline example loaded · edit the label and message, then backtest.'
        self.invalidate()
        self.notice = 'An offline audience is ready. No AI call was made and nothing was activated.'

    @rx.event(background=True)
    async def draft_with_ai(self):
        async with self:
            if self.busy: return
            if not self.label.strip() or not self.message.strip():
                self.error = 'Enter the campaign label and customer message first.'
                return
            if not self.ai_prompt.strip():
                self.error = 'Describe who should see this campaign in the AI audience box.'
                return
            self.busy = True
            self.busy_task = 'AI is drafting the audience · allow up to 60 seconds'
            self._audience = {}
            self.audience_rules = []
            self.assumptions = []
            self.error = ''
            self.notice = ''
            self.audience_status = 'Drafting audience with AI… this may take up to 60 seconds. Do not click again.'
            self.invalidate()
            inputs = (self.label, self.message, self.ai_prompt, self.image_path,
                      self.llm_endpoint, self.llm_model, self._key)
        try:
            spec, notes = await asyncio.to_thread(wb.ai_audience, *inputs)
        except Exception as exc:
            async with self:
                self.error = str(exc) if isinstance(exc, ValueError) else 'AI request failed. Check Settings, or use an offline example.'
                self.audience_status = 'AI did not create an audience. Nothing was saved or activated.'
                self.busy = False
                self.busy_task = ''
            return
        async with self:
            if (self.label, self.message, self.ai_prompt, self.image_path) != inputs[:4]:
                self.error = 'Campaign fields changed during the AI request. Please click Draft audience again.'
                self.busy = False
                self.busy_task = ''
                return
            self._audience = spec
            self.start_date, self.end_date = spec['start_date'], spec['end_date']
            self.audience_rules = [wb.describe_condition(c) for c in spec['conditions']]
            self.assumptions = notes
            self.audience_status = 'AI audience draft received · review the actual filters below before backtesting.'
            self.busy = False
            self.busy_task = ''
            self.notice = 'AI proposed filters; deterministic validation checked them. AI did not contact any customers.'

    async def upload_image(self, files: list[rx.UploadFile]):
        if self.busy: return
        if len(files) != 1:
            self.error = 'Choose one PNG, JPEG or WebP image smaller than 2 MB.'
            return
        f = files[0]
        if f.size is not None and f.size > 2_000_000:
            self.error = 'Image exceeds 2 MB.'
            return
        payload = await f.read()
        kind = ('png' if payload.startswith(b'\x89PNG\r\n\x1a\n') else
                'jpg' if payload.startswith(b'\xff\xd8\xff') else
                'webp' if payload.startswith(b'RIFF') and payload[8:12] == b'WEBP' else '')
        if not kind or not 0 < len(payload) <= 2_000_000:
            self.error = 'Only PNG, JPEG or WebP images smaller than 2 MB are accepted.'
            return
        target = ROOT / 'assets' / 'uploads' / (uuid.uuid4().hex + '.' + kind)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        self.image_path = '/uploads/' + target.name
        self.invalidate()
        self.notice = 'Background image uploaded. No campaign was activated.'

    def clear_image(self):
        if self.busy: return
        self.image_path = 'default'
        self.invalidate()
        self.notice = 'Using the default blue background.'

    @rx.event(background=True)
    async def backtest(self):
        async with self:
            if self.busy: return
            self.invalidate()
            if not self._audience:
                self.error = 'Create an audience with AI or load an offline example first.'
                return
            try:
                spec = wb.build_spec(self.label, self.message, self.image_path, self._audience['conditions'],
                                     self.start_date, self.end_date, self._audience['id'])
            except (ValueError, KeyError, TypeError) as exc:
                self.error = str(exc)
                return
            self.busy = True
            self.busy_task = 'Backtest is checking every CSV row · allow several seconds'
            self.notice = 'Backtest running over all synthetic CSV rows… nothing will be sent.'
        try:
            result = await asyncio.to_thread(wb.backtest, spec, wb.running_campaigns())
        except (ValueError, KeyError, TypeError, OSError) as exc:
            async with self:
                self.busy = False
                self.busy_task = ''
                self.error = str(exc)
            return
        async with self:
            self.busy = False
            self.busy_task = ''
            self._reviewed = spec
            self.review_rows = [dict(label=k, value=f'{v:,}') for k,v in (
                ('Customers actually tested', result['population']), ('Audience matches', result['matched']),
                ('Passed age, consent and protection checks', result['eligible']),
                ('Would see this campaign', result['selected']),
                ('Matched but stayed silent', result['excluded']))]
            self.sample_indexes = result['samples'][:8]
            self.sample_date = result['at']
            self.review_ready = True
            self.audience_status = 'Backtest complete · simulated on ' + result['at'] + ' against the actual CSV rows.'
            self.notice = f"Simulation took {result['milliseconds']:,} ms. Nothing was sent. Check the filters and customer examples, then activate if appropriate."

    def activate(self):
        if self.busy or not self.review_ready or not self._reviewed:
            self.error = 'Run Backtest before activating. Changes invalidate a previous review.'
            return
        try:
            spec = wb.build_spec(self.label, self.message, self.image_path, self._reviewed['conditions'],
                                 self.start_date, self.end_date, self._reviewed['id'])
            if spec != self._reviewed:
                raise ValueError('Campaign changed after backtest. Run Backtest again.')
            engine.save_approved(spec)
        except (ValueError, OSError) as exc:
            self.error = str(exc)
            return
        self.review_ready = False
        self._reviewed = {}
        self.refresh_registry()
        self.go('Registry')
        self.notice = 'Activated locally. It now participates in CSV customer decisions; NO real messages are sent.'

    def refresh_registry(self):
        paused = wb.paused_ids()
        self.registry_rows = [dict(id=x['id'], title=x['title'], source='Always-on' if x['source']=='library' else 'Employee-created',
                                   status='Paused' if x['id'] in paused else 'Running',
                                   dates=x['start_date'] + ' → ' + x['end_date'],
                                   rules=' AND '.join(wb.describe_condition(c) for c in x['conditions'])) for x in wb.all_campaigns()]

    def toggle_campaign(self, cid: str):
        try:
            new_status = cid not in wb.paused_ids()
            wb.set_paused(cid, new_status)
            self.refresh_registry()
            self.inspect(self.chosen_index)
            self.notice = ('Paused' if new_status else 'Resumed') + ' in the local registry. Customer decisions updated; nothing was delivered.'
        except ValueError as exc: self.error = str(exc)

    def browse(self):
        data = wb.all_customers()
        self.dataset_size = f'{len(data):,}'
        self.dataset_origin = 'Imported CSV (names and rules read live)' if wb.ACTIVE.exists() else 'data/customer_signals.csv (original synthetic dataset)'
        first = self.page_number * 20
        self.browser_rows = [dict(index=str(i + 1), label=wb.customer_name(row, i + 1), age=row['age'],
                                  city=row.get('city') or 'Unknown city', savings=wb.display_value('savings_balance',row.get('savings_balance','')), consent=row['consent_tier'])
                             for i,row in enumerate(data[first:first+20], first)]

    def next_page(self):
        if (self.page_number+1)*20 < len(wb.all_customers()): self.page_number += 1
        self.browse()

    def previous_page(self):
        self.page_number = max(0, self.page_number-1)
        self.browse()

    def set_lookup_index(self, value: str): self.lookup_index = value

    def lookup(self):
        try:
            index = int(self.lookup_index)
            if not 1 <= index <= len(wb.all_customers()): raise ValueError()
        except ValueError:
            self.error = f'Enter a CSV row number between 1 and {len(wb.all_customers()):,}.'
            return
        self.inspect(index-1)
        self.page_number = (index-1)//20
        self.browse()

    def random_customer(self):
        import secrets
        self.inspect(secrets.randbelow(len(wb.all_customers())))

    def inspect(self, index: int):
        rows = wb.all_customers()
        if not 0 <= index < len(rows):
            self.error = 'Customer row not found.'
            return
        self.chosen_index = index
        self.preview_date = engine.CLOCK
        self._overrides = {}
        self.what_changed = False
        self._calculate(rows[index])
        self.browse()
        self.error = ''

    def select_row(self, index: str):
        self.inspect(int(index)-1)

    def _calculate(self, row):
        winner, audit = wb.audit_customer(row, wb.running_campaigns(), self.preview_date)
        self.customer_id = row['customer_id']
        self.customer_label = wb.customer_name(row, self.chosen_index+1) + f' · row {self.chosen_index+1:,}'
        self.customer_age, self.customer_city, self.customer_consent = row['age'], row.get('city') or 'Unknown city', row['consent_tier']
        self.customer_title = winner['title'] if winner else 'No campaign selected'
        self.customer_message = wb.render_message(winner, row, self.chosen_index+1) if winner else 'The engine stays quiet for this customer.'
        self.customer_background = winner['background'] if winner else 'default'
        self.customer_reason = 'Decision simulated on ' + self.preview_date + ' using this actual CSV row and all running campaigns. Nothing was delivered.'
        self.customer_audit = [dict(title=a['title'], status=a['status'], reason=a['reason'],
                                   checks=' | '.join(('PASS' if c['passed'] else 'FAIL') + ' ' + c['rule'] + ' (actual ' + c['actual'] + ')' for c in a['checks'])) for a in audit]
        feature_keys = ('age','savings_balance','monthly_surplus_3m','surplus_trend_up_3m','travel_spend_12m',
                        'open_insurance_claim','financial_pressure','has_travel_insurance','contacts_last_30d','consent_tier')
        self.customer_features = [dict(label=wb.LABELS[k], value=wb.display_value(k,row.get(k,'')), column=k) for k in feature_keys]

    def set_what_signal(self, value: str):
        if value in ('age','savings_balance','monthly_surplus_3m','travel_spend_12m','surplus_trend_up_3m',
                     'open_insurance_claim','financial_pressure','has_travel_insurance','contacts_last_30d','consent_tier'):
            self.what_signal = value
    def set_what_value(self, value: str): self.what_value = value

    def simulate_change(self):
        row = dict(wb.all_customers()[self.chosen_index])
        field = self.what_signal
        try:
            if field == 'consent_tier':
                if self.what_value not in engine.TIERS: raise ValueError('Choose service, guidance or offers.')
                row[field] = self.what_value
            elif engine.META[field]['type'] == 'bool':
                if self.what_value.lower() not in ('yes','no'): raise ValueError('Use yes or no for this flag.')
                row[field] = '1' if self.what_value.lower() == 'yes' else '0'
            else:
                number = float(self.what_value)
                import math
                if not math.isfinite(number) or abs(number)>1_000_000: raise ValueError('Enter a realistic numeric value.')
                if field in ('age','contacts_last_30d') and (not number.is_integer() or number < (12 if field=='age' else 0) or number > (100 if field=='age' else 20)):
                    raise ValueError('Age must be 12–100; contacts must be 0–20.')
                row[field] = str(int(number) if number.is_integer() else number)
            if int(row['age'])<18: row['consent_tier']='service';row['turned_18_last_30d']='0'
            if field=='age' and int(row['age'])!=18: row['turned_18_last_30d']='0'
            if row['open_insurance_claim']=='0': row['claim_waiting_documents_days']='0'; row['claim_documents_needed']='0'
            self._calculate(row)
            self.what_changed = True
            self.notice = 'What-if simulation only: the CSV was NOT changed. Reset customer to restore its original values.'
            self.error = ''
        except (ValueError, KeyError) as exc: self.error = str(exc)

    def view_sample(self, index: int):
        self.inspect(index-1)
        self.preview_date = self.sample_date
        self._calculate(wb.all_customers()[self.chosen_index])
        self.page = 'Test customers'
        self.notice = 'This is a real CSV row selected by the backtest. Preview date matches the backtest (' + self.sample_date + '). Nothing was delivered.'

    def set_endpoint(self, value: str):
        if not self.busy: self.llm_endpoint = value
    def set_model(self, value: str):
        if not self.busy: self.llm_model = value
    def set_key(self, value: str):
        if self.busy: return
        self._key = value
        self.key_status = 'Session-only key set; never shown back in the UI.' if value else 'No API key stored. The default endpoint is keyless.'


app = rx.App(stylesheets=['/style.css'])


def small(value): return rx.text(value, color=MUTED, font_size='13px', line_height='1.6')
def eyebrow(value): return rx.text(value, color=BLUE, font_size='11px', font_weight='bold', letter_spacing='.11em')
def card(*children, **props):
    return rx.box(*children, **{'background':'white','border':f'1px solid {BORDER}','border_radius':'16px','padding':'22px', **props})
def heading(value, detail):
    return rx.vstack(eyebrow('KBC · SYNTHETIC INTENT ENGINE'), rx.heading(value, color=INK, font_size='32px'), small(detail), align_items='start', spacing='2', margin_bottom='18px')
def action(text, handler, primary=False, **props):
    return rx.button(text, on_click=handler, background=BLUE if primary else '#E8F5FA', color='white' if primary else STONE,
                     cursor='pointer', **props)
def nav(name, icon):
    return rx.button(rx.icon(icon,size=17),name,on_click=State.go(name), class_name='nav-item', width='100%',justify_content='start',
                     background=rx.cond(State.page==name,'#E8F5FA','transparent'), color=rx.cond(State.page==name,STONE,MUTED))
def shell():
    return rx.box(rx.vstack(rx.hstack(rx.box('K',padding='8px 13px',background=BLUE,color='white',border_radius='9px',font_weight='bold'),
                                      rx.vstack(rx.text('KBC',font_weight='bold',color=INK),eyebrow('INTENT ENGINE'),spacing='0'),align='center'),
                            small('LOCAL · FICTIONAL CUSTOMERS'),nav('Campaigns','sparkles'),nav('Test customers','users'),
                            nav('Registry','layers'),nav('Governance','shield-check'),nav('Settings','settings'),nav('Help','circle-help'),
                            rx.spacer(),small('No login · no real messages'),class_name='sidebar',padding='18px 12px',spacing='3'),
                  rx.box(rx.cond(State.page=='Campaigns',campaigns_page(),rx.cond(State.page=='Test customers',customers_page(),
                         rx.cond(State.page=='Registry',registry_page(),rx.cond(State.page=='Governance',governance_page(),
                         rx.cond(State.page=='Settings',settings_page(),help_page()))))),class_name='main-content'),
                  background=BG,min_height='100vh',font_family='Inter,system-ui,sans-serif')


def status():
    return rx.vstack(rx.cond(State.busy,rx.hstack(rx.spinner(size='2'),rx.text(State.busy_task,color=STONE),align='center')),
                     rx.cond(State.error!='',rx.text(State.error,color='#B42838',font_weight='bold',background='#FFF1F2',padding='10px',border_radius='9px')),
                     rx.cond(State.notice!='',rx.text(State.notice,color=STONE,background='#E7F7FD',padding='10px',border_radius='9px')),
                     width='100%',align_items='start')


def campaigns_page():
    return rx.vstack(heading('Create a campaign','Enter the label and message customers would see. Ask AI who should see it, or load an offline example.'),
        status(),
        rx.flex(card(eyebrow('1 · WHAT CUSTOMERS SEE'),
             rx.text('Campaign label',color=INK,font_weight='bold',margin_top='14px'),small('Shown as the title in the customer preview.'),
             rx.input(value=State.label,on_change=State.set_label,disabled=State.busy,placeholder='e.g. Autumn mobility offer',width='100%',margin_top='7px'),
             rx.text('Message to customer',color=INK,font_weight='bold',margin_top='18px'),small('The exact copy shown to eligible customers. {first_name} can insert a demo name.'),
             rx.text_area(value=State.message,on_change=State.set_message,disabled=State.busy,placeholder='Explore this optional offer, {first_name}.',width='100%',min_height='110px',margin_top='7px'),
             rx.text('Background image (optional)',color=INK,font_weight='bold',margin_top='17px'),
             rx.upload(rx.vstack(rx.icon('image',color=BLUE),small('Click here to select PNG, JPEG or WebP · max 2 MB'),align='center'),
                       id='campaign_image',accept={'image/png':['.png'],'image/jpeg':['.jpg','.jpeg'],'image/webp':['.webp']},
                       max_files=1,border=f'1px dashed {BLUE}',border_radius='10px',padding='14px',width='100%'),
             rx.hstack(action('Upload selected image',State.upload_image(rx.upload_files(upload_id='campaign_image')),disabled=State.busy),
                       action('Remove image',State.clear_image,disabled=State.busy),flex_wrap='wrap',margin_top='10px'),
             small('Image: ' + State.image_path),
             rx.cond(State.image_path!='default',rx.image(src=State.image_path,height='110px',object_fit='cover',border_radius='9px',margin_top='9px')),
             width='100%',flex='1',min_width='290px'),
             card(eyebrow('2 · WHO SHOULD SEE IT'),rx.text('Describe audience for AI',color=INK,font_weight='bold',margin_top='14px'),
                  small('Only the text in THIS box is sent to AI (plus the public signal schema). It proposes filters; neither customer records nor the message above are sent.'),
                  rx.text_area(value=State.ai_prompt,on_change=State.set_ai_prompt,disabled=State.busy,
                               placeholder='Example: Adults 18–29 with at least €18,000 in savings and a rising monthly surplus. Run in October–November.',
                               width='100%',min_height='120px',margin_top='7px'),
                  rx.button(rx.cond(State.busy,'Working… please wait','Draft audience with AI'),
                            on_click=State.draft_with_ai,disabled=State.busy,background=BLUE,color='white',margin_top='12px',cursor='pointer'),
                  rx.cond(State.busy,rx.hstack(rx.spinner(size='2'),small(State.busy_task),margin_top='10px')),
                  small('No connection? Load an offline audience example (no AI call):'),
                  rx.hstack(action('Travel insurance example',State.example('travel'),disabled=State.busy),action('Car/mobility example',State.example('car'),disabled=State.busy),
                            margin_top='9px',flex_wrap='wrap'),
                  rx.box(eyebrow('PROPOSED AUDIENCE'),rx.text(State.audience_status,color=STONE,margin_top='9px'),
                         rx.foreach(State.audience_rules,lambda r: rx.hstack(rx.icon('check',color='#198271',size=15),rx.text(r,color=INK,font_size='13px'),padding_y='4px')),
                         rx.foreach(State.assumptions,lambda a: small('Assumption: '+a)),
                         padding='15px',background=BG,border_radius='10px',margin_top='17px'),
                  rx.el.details(
                      rx.el.summary('Optional campaign dates · click to schedule (defaults shown below)'),
                      small('Backtest simulates at the start date if it is in the future; the campaign will not appear today until that date.'),
                      rx.hstack(rx.vstack(small('Start date · demo clock 2026-09-30'),rx.input(type='date',value=State.start_date,on_change=State.set_start_date,disabled=State.busy),align_items='start'),
                                rx.vstack(small('End date'),rx.input(type='date',value=State.end_date,on_change=State.set_end_date,disabled=State.busy),align_items='start'),
                                margin_top='10px',flex_wrap='wrap'),
                      margin_top='17px',padding='10px 12px',background=BG,border_radius='8px',width='100%'),
                  width='100%',flex='1',min_width='290px'),gap='16px',width='100%',flex_wrap='wrap'),
        card(eyebrow('3 · TEST, THEN ACTIVATE'),small('Backtest evaluates the proposed rule against every synthetic customer row, consent, safety and other running campaigns. Nothing is sent.'),
             action(rx.cond(State.busy,'Working… please wait','Run backtest on all synthetic customers'),State.backtest,primary=True,disabled=State.busy,margin_top='12px'),
             rx.cond(State.busy,rx.hstack(rx.spinner(size='2'),small('Working. This may take several seconds.'),margin_top='12px')),
             rx.cond(State.review_ready,rx.vstack(rx.foreach(State.review_rows,lambda r: rx.hstack(rx.text(r['label'],color=INK),rx.spacer(),rx.text(r['value'],color=STONE,font_weight='bold'),width='100%',border_bottom=f'1px solid {BORDER}',padding_y='9px')),
                           small('Sample winning CSV rows · click to see actual values and competing campaigns:'),
                           rx.flex(rx.foreach(State.sample_indexes,lambda i: action('Inspect CSV row '+i.to_string(),State.view_sample(i))),gap='7px',flex_wrap='wrap'),
                           action('Activate locally in registry',State.activate,primary=True),
                           small('Activate writes reviewed rules to the LOCAL simulated registry; it does not send a notification.'),width='100%',align_items='start',margin_top='14px')),
             width='100%'),spacing='4',width='100%',align_items='start')


def customers_page():
    return rx.vstack(heading('Test real synthetic rows','Every result below is recomputed from the active CSV and all running campaigns; names and results change when you import or replace it.'),status(),
      card(eyebrow('ACTIVE DATASET · COMPUTED, NOT HARDCODED'),
           rx.text(State.dataset_size+' customer rows · '+State.dataset_origin,color=STONE,font_weight='bold'),
           small('Swap the dataset to see different names, winners, audit values and backtest counts immediately. Needs customer_id, age, consent_tier; other approved signal columns are optional. Missing protection fields prevent offers.'),
           rx.upload(rx.vstack(rx.icon('file-up',size=19,color=BLUE),small('Select a replacement UTF-8 CSV · 32 MB maximum'),
                                align_items='center',padding='12px'),id='customers_csv',accept={'text/csv':['.csv']},
                     border='1px dashed #0097DB',border_radius='10px',margin_top='12px'),
           rx.hstack(action('Import selected CSV (replaces active dataset)',State.import_dataset(rx.upload_files(upload_id='customers_csv')),primary=True,disabled=State.busy),
                     action('Reload CSV from disk',State.reload_customers,disabled=State.busy),
                     action('Restore original dataset',State.restore_dataset,disabled=State.busy),flex_wrap='wrap',gap='8px',margin_top='12px'),
           small('An import keeps the previous dataset as a local backup. You can also replace data/customer_signals.csv on disk and click Reload. No real bank data, please.'),
           width='100%'),
      card(eyebrow('FIND A CUSTOMER IN THE DATASET'),
           rx.hstack(rx.input(value=State.lookup_index,on_change=State.set_lookup_index,placeholder='CSV row number',width='180px'),
                     action('Open row',State.lookup,primary=True),action('Pick random CSV row',State.random_customer),
                     rx.cond(State.dataset_origin.contains('original'),action('Emma · row 1',State.inspect(0))),
                     rx.cond(State.dataset_origin.contains('original'),action('Marc · row 2',State.inspect(1))),flex_wrap='wrap',gap='8px',margin_top='10px'),
           small('The row number is the position in the ACTIVE CSV (header excluded). No customer information is sent to AI.'),
           width='100%'),
      rx.flex(card(eyebrow('KBC APP PREVIEW · COMPUTED NOW'),rx.hstack(rx.icon('smartphone',color=BLUE),rx.text(State.customer_label,font_weight='bold',color=INK),align='center',margin_top='12px'),
                   rx.box(rx.vstack(rx.heading(State.customer_title,color=INK,size='5'),rx.text(State.customer_message,color=INK,line_height='1.6'),
                                    small('Customer age '+State.customer_age+' · '+State.customer_city+' · consent: '+State.customer_consent),
                                    small(State.customer_reason),align_items='start'),
                          background_image=rx.cond(State.customer_background=='default','none','url('+State.customer_background+')'),
                          background_size='cover',background_position='center',background_color='#E9F7FC',padding='20px',border_radius='13px',margin_top='14px'),
                   rx.cond(State.what_changed,small('WHAT-IF ONLY · not saved to CSV')),width='100%',flex='1',min_width='300px'),
              card(eyebrow('SOURCE CSV SIGNALS · ACTUAL VALUES'),small('These values feed the rules below; image and message come from the winning campaign.'),
                   rx.foreach(State.customer_features,lambda f: rx.hstack(rx.text(f['label'],color=INK,font_size='13px'),rx.spacer(),
                              rx.text(f['value'],color=STONE,font_size='13px',font_weight='bold'),width='100%',border_bottom=f'1px solid {BORDER}',padding_y='6px')),
                   small('Opaque customer ID: '+State.customer_id),width='100%',flex='1',min_width='300px'),gap='15px',width='100%',flex_wrap='wrap'),
      card(eyebrow('WHY THIS CAMPAIGN, OR WHY SILENCE?'),small('Each row shows its individual filters and actual customer values. A match may still be suppressed by consent, open claims or a stronger campaign.'),
           rx.foreach(State.customer_audit,lambda a: rx.box(rx.hstack(rx.text(a['title'],color=INK,font_weight='bold'),rx.spacer(),
                         rx.badge(a['status'],color_scheme=rx.cond(a['status']=='Selected','green','gray')),
                         width='100%',flex_wrap='wrap'),small(a['reason']),
                         small(a['checks']),
                         border_bottom=f'1px solid {BORDER}',padding_y='13px')),width='100%'),
      card(eyebrow('WHAT-IF TEST · NEVER CHANGES THE CSV'),small('Change one signal for this customer, then watch the same engine recalculate. Reset restores the original row.'),
           rx.hstack(rx.select(['age','savings_balance','monthly_surplus_3m','travel_spend_12m','surplus_trend_up_3m',
                                'open_insurance_claim','financial_pressure','has_travel_insurance','contacts_last_30d','consent_tier'],
                                value=State.what_signal,on_change=State.set_what_signal,width='220px'),
                     rx.input(value=State.what_value,on_change=State.set_what_value,placeholder='Number, yes/no or consent tier',width='230px'),
                     action('Simulate one change',State.simulate_change,primary=True),action('Reset to original CSV row',State.inspect(State.chosen_index)),
                     flex_wrap='wrap',gap='8px',margin_top='12px'),width='100%'),
      card(eyebrow('BROWSE MORE CSV ROWS'),rx.hstack(action('Previous 20',State.previous_page),action('Next 20',State.next_page),
                                                  small('Page '+(State.page_number+1).to_string()),gap='10px',align='center',margin_top='10px'),
           rx.foreach(State.browser_rows,lambda r: rx.hstack(action('Inspect #'+r['index'],State.select_row(r['index'])),
                     rx.text(r['label']+' · age '+r['age']+' · '+r['city']+' · savings €'+r['savings']+' · '+r['consent'],font_size='12px',color=INK),
                     border_bottom=f'1px solid {BORDER}',padding_y='5px',width='100%',flex_wrap='wrap')),width='100%'),
      spacing='4',width='100%',align_items='start')


def registry_page():
    return rx.vstack(heading('Campaign registry','Always-on and activated campaigns share the SAME decision engine. Pause or resume one to see decisions change immediately.'),status(),
       rx.foreach(State.registry_rows,lambda r: card(rx.hstack(rx.vstack(rx.text(r['title'],color=INK,font_weight='bold',font_size='17px'),
                       small(r['source']+' · '+r['dates']),align_items='start'),rx.spacer(),rx.badge(r['status'],color_scheme=rx.cond(r['status']=='Running','green','gray')),
                       action(rx.cond(r['status']=='Running','Pause locally','Resume locally'),State.toggle_campaign(r['id'])),align='center',flex_wrap='wrap',gap='10px'),
                   small('Audience: '+r['rules']),small('Status is stored locally. No notification is actually sent.'),width='100%')),
       action('Test any campaign against CSV customers →',State.go('Test customers'),primary=True),spacing='3',width='100%',align_items='start')


def governance_page():
    return rx.vstack(heading('How a decision is made', 'The same four steps apply to every customer and every campaign, including AI-drafted audiences.'),
      card(eyebrow('THE DECISION PATH'),
           rx.flex(*[rx.box(rx.box(str(number),background='#E7F6FC',color=STONE,font_weight='bold',
                              padding='8px 12px',border_radius='9px',width='fit-content'),
                             rx.text(name,color=INK,font_weight='bold',margin_top='10px'),small(detail),
                             padding='14px',background=BG,border_radius='11px',flex='1',min_width='185px')
                     for number,name,detail in (
                       (1,'Match','Compare each approved AND filter with columns in the selected synthetic CSV row.'),
                       (2,'Protect','Under-18s get no offers. Offers require consent and are blocked by open claims or financial pressure.'),
                       (3,'Choose one','Service help outranks guidance, then offers. Cooldowns and the contact budget can cause silence.'),
                       (4,'Explain','Test customers shows the actual input values, matched rules, winner and reasons for suppression.'))],
                   gap='12px',flex_wrap='wrap',width='100%',margin_top='16px'),width='100%'),
      card(eyebrow('ALLOWED INPUTS · THE AI MAY ONLY PROPOSE FILTERS FROM THIS LIST'),
           rx.flex(*[rx.hstack(rx.text(wb.LABELS.get(key,key),color=INK,font_size='13px'),
                               rx.spacer(),rx.badge('Can target offers' if 'target_offers' in meta['allowed_uses'] else 'Protection / help only',
                                                   color_scheme='cyan' if 'target_offers' in meta['allowed_uses'] else 'gray'),
                               background=BG,padding='10px',border_radius='8px',width='100%',align='center',flex_wrap='wrap')
                      for key,meta in engine.META.items()],gap='8px',width='100%',margin_top='16px',flex_wrap='wrap'),width='100%'),
      card(eyebrow('WHAT THIS PROTOTYPE DOES NOT DO'),
           small('No medical or religious targeting, loan decisions, insurance pricing or real deliveries. A savings threshold is an illustrative test value, not a researched car price. Rising surplus is a synthetic historical flag, not a prediction. AI drafts filters; deterministic code checks them against the CSV.'),width='100%'),
      action('Inspect real synthetic CSV decisions →',State.go('Test customers'),primary=True),
      spacing='4',width='100%',align_items='start')


def settings_page():
    return rx.vstack(heading('AI settings','Used ONLY when you click Draft audience with AI. Offline examples and all deterministic tests work without AI.'),status(),
       card(rx.text('OpenAI-compatible /v1 endpoint',color=INK,font_weight='bold'),rx.input(value=State.llm_endpoint,on_change=State.set_endpoint,width='100%'),
            rx.text('Model ID',color=INK,font_weight='bold',margin_top='17px'),rx.input(value=State.llm_model,on_change=State.set_model,width='100%'),
            rx.text('Optional API key',color=INK,font_weight='bold',margin_top='17px'),
            rx.input(type='password',placeholder='Only needed for an HTTPS endpoint',on_change=State.set_key,width='100%'),
            small(State.key_status),small('A key is held only in this demo session. HTTP with an API key is blocked. Do not send real customer data to an AI endpoint.'),width='100%'),
       action('Return to campaigns',State.go('Campaigns'),primary=True),spacing='4',width='100%',align_items='start')


def help_page():
    return rx.vstack(heading('Quick guide','Every button tells you whether it drafts, tests, activates, or only simulates.'),
       card(eyebrow('CAMPAIGNS'),small('Enter a label and customer message. Optionally upload an image. Type the audience into the dedicated AI box, then click Draft audience with AI ONCE and wait for the spinner. Or load an offline example. Read the proposed AND rules, Run backtest, inspect sample rows, then Activate locally. Edits after backtest require another backtest.'),width='100%'),
       card(eyebrow('TEST CUSTOMERS'),small('Import a replacement synthetic CSV here, or replace data/customer_signals.csv and click Reload. Required headers: customer_id, age, consent_tier. Additional approved signal columns and first_name are optional; missing financial/protection signals do not create a positive offer. Browse or pick any row; What-if never writes to disk.'),width='100%'),
       card(eyebrow('REGISTRY & GOVERNANCE'),small('Registry lists running campaigns. Pause/Resume changes local decisions immediately. Governance explains safe signals, suppression and silence. Nothing sends a notification.'),width='100%'),
       card(eyebrow('SETTINGS'),small('Set an OpenAI-compatible endpoint and model to enable AI drafting. The supplied endpoint is keyless; if it is offline, use offline examples. Do not enter a real customer prompt.'),width='100%'),
       small('More detailed button guide: GUIDE.md in the project directory.'),spacing='4',width='100%',align_items='start')


def index(): return shell()
app.add_page(index,title='KBC Intent Engine | Synthetic Workbench',on_load=State.initialize)
