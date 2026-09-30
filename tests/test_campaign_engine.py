"""End-to-end proof points for the fictional, deterministic campaign engine."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import generate_data
import campaign_engine as e


class CampaignEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.campaigns = [*e.library(), e.sample('travel')]
        cls.rows = {x['customer_id']: x for x in e.population()[:2]}

    def test_fixed_seed_personas_and_raw_sensitive_details_do_not_leak(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            ages = generate_data.generate(population=100, output=out)
            self.assertEqual(sum(ages.values()), 100)
            with (out/'customer_signals.csv').open(newline='') as source:
                signals = list(csv.DictReader(source))
            self.assertEqual(len(signals), 100)
            self.assertEqual(len({x['customer_id'] for x in signals}), 100)
            self.assertEqual(signals[0]['age'], '18')
            self.assertEqual(signals[1]['claim_waiting_documents_days'], '12')
            self.assertTrue(any(int(x['age']) < 18 for x in signals))
            self.assertTrue(all(x['consent_tier'] == 'service' for x in signals if int(x['age']) < 18))
            self.assertNotIn('pharmacy', (out/'customer_signals.csv').read_text())
            self.assertNotIn('religious_donation', (out/'customer_signals.csv').read_text())
            self.assertIn('pharmacy', (out/'transactions.csv').read_text())
            self.assertIn('religious_donation', (out/'transactions.csv').read_text())
            first = (out/'customer_signals.csv').read_bytes()
            generate_data.generate(population=100, output=out)
            self.assertEqual(first, (out/'customer_signals.csv').read_bytes())

    def test_emma_and_marc_library_studio_same_engine(self):
        emma = e.persona('Emma', self.campaigns)
        marc = e.persona('Marc', self.campaigns)
        self.assertEqual(emma['title'], 'Welcome to adulthood')
        self.assertEqual(marc['title'], 'Claim needs documents')
        for result in (emma, marc):
            self.assertEqual(len([result['title']] if result['sent'] else []), 1)
            self.assertIn('Summer travel insurance', [x['title'] for x in result['matched']])
            self.assertIn('Summer travel insurance', [x['title'] for x in result['suppressed']])
            self.assertTrue(result['explanation'])
        self.assertIn('Open claim', next(x['reason'] for x in marc['suppressed'] if x['title'] == 'Summer travel insurance'))

    def test_strict_schema_forbidden_signals_and_protective_signal(self):
        spec = e.sample()
        for mutation in (
            {'extra': 'bad'},
            {'conditions': [{'signal':'health_spend_level','operator':'>','value':5}]},
            {'conditions': [{'signal':'religious_affiliation','operator':'=','value':'yes'}]},
            {'conditions': [{'signal':'financial_pressure','operator':'=','value':True}]},
            {'conditions': [{'signal':'open_insurance_claim','operator':'=','value':False}]},
            {'conditions': [{'signal':'age','operator':'>=','value':float('nan')}]},
            {'message': 'Hello {secret}'},
            {'minimum_consent':'service'},
            {'background':'https://example.org/image.png'},
            {'start_date':'2026-02-30'},
            {'combinator':'any'},
        ):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                e.validate({**spec, **mutation})
        self.assertNotIn('health_spend_level', e.META)
        self.assertNotIn('religious_affiliation', e.META)
        self.assertNotIn('pharmacy', e.META)

    def test_age_consent_claim_cooldown_and_budget(self):
        row = dict(self.rows[e.persona('Emma',self.campaigns)['customer_id']])
        travel = e.sample()
        row['age'] = '17'
        self.assertEqual(e.gate(row, travel), 'Age protection')
        row['age'] = '18'; row['consent_tier'] = 'guidance'
        self.assertEqual(e.gate(row, travel), 'Insufficient consent')
        row['consent_tier'] = 'offers'; row['open_insurance_claim'] = '1'
        self.assertIn('claim', e.gate(row, travel))
        row['open_insurance_claim'] = '0'; row['contacts_last_30d'] = '1'
        self.assertIn('budget', e.gate(row, travel))
        row['contacts_last_30d'] = '0'; row['last_contact_campaign'] = travel['id']; row['last_contact_days_ago'] = '3'
        self.assertEqual(e.gate(row, travel), 'Campaign cooldown')
        self.assertFalse(e.active(e.sample('car')))
        self.assertTrue(e.active(e.sample('car'), '2026-10-15'))
        self.assertEqual(e.gate(row, e.library()[0]), '')  # service exemption from contact budget

    def test_simplified_ui_uses_arbitrary_csv_rows(self):
        import workbench as wb
        from kbc_intent_lab.kbc_intent_lab import State
        state = State(_reflex_internal_init=True)
        state.initialize()
        state.inspect(745)
        row = wb.all_customers()[745]
        winner, audit = wb.audit_customer(row, wb.running_campaigns(), e.CLOCK)
        self.assertEqual(state.customer_id, row['customer_id'])
        self.assertEqual(state.customer_title, winner['title'] if winner else 'No campaign selected')
        self.assertEqual(len(state.customer_audit), len(audit))
        self.assertIn('row 746', state.customer_label)
        state.example('travel')
        self.assertEqual(state.label, 'Summer travel insurance')
        self.assertFalse(state.review_ready)
        self.assertEqual(len(state.audience_rules), 2)
        state.set_ai_prompt('Find a different audience')
        self.assertEqual(state.audience_rules, [])
        self.assertEqual(state._audience, {})

    def test_live_full_population_backtest_changes_with_real_csv_data(self):
        import workbench as wb
        spec = wb.build_spec('Travel tips', 'Explore optional travel cover, {first_name}.', 'default',
                             e.sample('travel')['conditions'], '2026-09-30', '2027-12-31',
                             'studio_' + 'a' * 16)
        rows = wb.all_customers()
        result = wb.backtest(spec, e.library(), rows)
        self.assertEqual(result['population'], len(rows))
        self.assertGreater(result['matched'], result['selected'])
        self.assertEqual(result['matched'], result['selected'] + result['excluded'])
        self.assertTrue(result['samples'])
        index = result['samples'][0]
        winner, audit = wb.audit_customer(rows[index-1], [*e.library(), spec], result['at'])
        self.assertEqual(winner['id'], spec['id'])
        self.assertTrue(any(a['id'] == spec['id'] and a['status'] == 'Selected' for a in audit))
        changed = dict(rows[index-1], consent_tier='service')
        winner2, audit2 = wb.audit_customer(changed, [*e.library(), spec], result['at'])
        self.assertFalse(any(a['id'] == spec['id'] and a['status'] == 'Selected' for a in audit2))

    def test_saving_campaign_will_not_reuse_example_id(self):
        import workbench as wb
        from kbc_intent_lab.kbc_intent_lab import State
        state = State(_reflex_internal_init=True)
        state.example('car')
        self.assertNotEqual(state._audience['id'], e.sample('car')['id'])
        self.assertFalse(state.review_ready)
        state.label = 'Edited title'
        spec = wb.build_spec(state.label, state.message, state.image_path,
                             state._audience['conditions'], state.start_date, state.end_date, state._audience['id'])
        self.assertEqual(spec['title'], 'Edited title')
        with self.assertRaises(ValueError):
            wb.build_spec('', state.message, state.image_path, spec['conditions'],
                          state.start_date, state.end_date, spec['id'])

    def test_imported_csv_names_optional_fields_and_live_replacement(self):
        import workbench as wb
        from kbc_intent_lab.kbc_intent_lab import State
        with tempfile.TemporaryDirectory() as folder, patch.object(wb, 'ACTIVE', Path(folder) / 'active.csv'), patch.object(wb, 'EXTRA', Path(folder) / 'extras.csv'):
            header = ('customer_id,first_name,age,city,consent_tier,monthly_surplus_3m,'
                      'savings_buffer_months,savings_balance,open_insurance_claim,'
                      'financial_pressure,contacts_last_30d\n')
            first = (header +
                'judge_a,Ada,36,Gent,offers,620,4,25000,no,no,0\n'
                'judge_b,Ben,41,Brugge,guidance,40,1,200,no,yes,0\n'
                'judge_c,Cleo,25,Liège,offers,,,,,,\n')
            self.assertEqual(wb.import_customers(first.encode()), 3)
            rows = wb.all_customers()
            self.assertEqual([wb.customer_name(row, i+1) for i,row in enumerate(rows)], ['Ada','Ben','Cleo'])
            active = wb.running_campaigns()
            decisions = [wb.audit_customer(row, active, e.CLOCK)[0] for row in rows]
            self.assertEqual(decisions[0]['id'], 'loan_information')
            self.assertIn('€620', wb.render_message(decisions[0], rows[0], 1))
            self.assertEqual(decisions[1]['id'], 'budget_buffer')
            self.assertIsNone(decisions[2])  # missing money/protective flags cannot trigger a loan
            self.assertTrue(all(not e.matches(rows[2], item) for item in active if item['id'] == 'loan_information'))
            state = State(_reflex_internal_init=True)
            state.reload_customers()
            self.assertEqual(state.dataset_size, '3')
            state.inspect(0)
            self.assertIn('Ada', state.customer_label)
            self.assertEqual(state.customer_title, 'Explore borrowing options')
            changed = (header + 'judge_x,Xavi,34,Gent,offers,35,1,50,no,no,0\n').encode()
            self.assertEqual(wb.import_customers(changed), 1)
            state.reload_customers()
            self.assertEqual(state.dataset_size, '1')
            self.assertIn('Xavi', state.customer_label)
            self.assertEqual(state.customer_title, 'Keep a comfortable buffer')
            self.assertTrue(list(Path(folder).glob('active_customers.backup.*.csv')))
            self.assertEqual(wb.reset_customers(), len(e.population()))
            self.assertEqual(len(wb.all_customers()), len(e.population()))

    def test_incomplete_or_invalid_csv_fails_without_replacing_active_data(self):
        import workbench as wb
        with tempfile.TemporaryDirectory() as folder, patch.object(wb, 'ACTIVE', Path(folder) / 'active.csv'), patch.object(wb, 'EXTRA', Path(folder) / 'extras.csv'):
            good = b'customer_id,age,consent_tier\na_ok,29,guidance\n'
            wb.import_customers(good)
            for bad in (b'age,consent_tier\n29,offers\n',
                        b'customer_id,age,consent_tier\ndup,30,offers\ndup,31,offers\n',
                        b'customer_id,age,consent_tier\nminor,16,offers\n',
                        b'customer_id,age,consent_tier,savings_balance\nbad,30,offers,NaN\n'):
                with self.subTest(bad=bad[:25]), self.assertRaises(ValueError):
                    wb.import_customers(bad)
                self.assertEqual(wb.all_customers()[0]['customer_id'], 'a_ok')
            self.assertIsNone(wb.audit_customer(wb.all_customers()[0],wb.running_campaigns(),e.CLOCK)[0])

    def test_session_not_relevant_and_optout(self):
        result = e.persona('Emma', self.campaigns)
        cid = result['customer_id']
        hidden = e.persona('Emma', self.campaigns, frozenset([cid + ':welcome_adulthood']))
        self.assertTrue(any(x['reason'] == 'Marked not relevant' for x in hidden['suppressed']))
        opted = e.persona('Emma', self.campaigns, optouts=frozenset([cid]))
        self.assertFalse(opted['sent'])
        marc = e.persona('Marc', self.campaigns)
        help_after_optout = e.persona('Marc', self.campaigns, optouts=frozenset([marc['customer_id']]))
        self.assertEqual(help_after_optout['title'], 'Claim needs documents')

    def test_backtest_counts_are_computed_and_funnel_balances(self):
        result = e.backtest(e.sample(), e.library())
        self.assertEqual(result['population'], 100000)
        self.assertGreater(result['matches'], result['selected'])
        self.assertGreater(result['removed_protected'], 0)
        self.assertGreater(result['suppressed'], 0)
        self.assertEqual(result['matches'], sum(result[k] for k in ('selected','removed_consent','removed_cooldown','removed_protected','suppressed')))
        self.assertEqual(sum(result['by_channel'].values()), result['selected'])
        self.assertLess(result['milliseconds'], 15000)

    def test_registry_saves_only_approved_named_json(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(e, 'CAMPAIGNS', Path(folder)):
            (Path(folder)/'library').mkdir()
            spec = e.sample('car') if False else json.loads((e.ROOT/'campaigns'/'car_example.json').read_text())
            e.save_approved(spec)
            self.assertEqual(e.registered()[0]['id'], 'mobility_partner')
            with self.assertRaises(ValueError):
                e.save_approved({**spec,'id':'../bad'})

    def test_llm_preflight_rejects_unapproved_endpoint_and_insecure_key(self):
        self.assertFalse(e.safe_llm_endpoint('http://127.0.0.1:9910/v1'))
        self.assertFalse(e.safe_llm_endpoint('http://169.254.169.254/v1'))
        self.assertFalse(e.safe_llm_endpoint('https://example.org:1234/v1'))
        with self.assertRaises(ValueError):
            e.llm_draft('Travel insurance', 'http://100.70.65.86:9910/v1', 'Micode/gpt-6-sol', 'not-an-actual-key')


if __name__ == '__main__': unittest.main()
