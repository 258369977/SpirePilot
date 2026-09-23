import copy
import io
import json
import os
import pathlib
import tempfile
import unittest
import urllib.error
from unittest.mock import patch
import game_actions
from hybrid_player import Controller, PLAN_FIELDS, RetryableProviderError, atomic_json, role_for

CONFIG = json.loads((pathlib.Path(__file__).parent / 'config.json').read_text(encoding='utf-8'))
STATE = {'state_type': 'map', 'run': {'act': 1, 'floor': 4},
         'player': {'hp': 40, 'deck': [{'name': 'Strike'}]},
         'map': {'next_options': [{'index': 0, 'type': 'RestSite'}, {'index': 1, 'type': 'Elite'}]}}
OPTIONS = [({'action': 'choose_map_node', 'index': 0}, 'Rest'), ({'action': 'choose_map_node', 'index': 1}, 'Elite')]

def planner_response(action='0'):
    return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({
        'action_id': action, 'reason': 'Heal before next boss.', 'plan': {k: 'Plan' for k in PLAN_FIELDS}})}}],
        'usage': {'cost': .001}}

class HybridTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def make(self, transport):
        config = {**CONFIG, 'experience_db': str(pathlib.Path(self.temp.name) / 'lessons.sqlite3')}
        c = Controller(config, self.temp.name, transport)
        c.stop_path = pathlib.Path(self.temp.name) / 'STOP'
        return c

    def test_atomic_json_retries_transient_windows_file_lock(self):
        target = pathlib.Path(self.temp.name) / 'memory.json'
        real_replace = os.replace
        attempts = 0
        def flaky_replace(source, destination):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise PermissionError(5, 'destination temporarily locked')
            return real_replace(source, destination)
        with patch('hybrid_player.os.replace', side_effect=flaky_replace), patch('hybrid_player.time.sleep'):
            atomic_json(target, {'value': 2})
        self.assertEqual(attempts, 3)
        self.assertEqual(json.loads(target.read_text(encoding='utf-8')), {'value': 2})
        self.assertEqual(list(target.parent.glob('.memory.json.*.tmp')), [])

    def test_atomic_json_preserves_old_file_after_persistent_lock(self):
        target = pathlib.Path(self.temp.name) / 'memory.json'
        target.write_text('{"value": 1}', encoding='utf-8')
        with patch('hybrid_player.os.replace', side_effect=PermissionError(5, 'locked')), patch('hybrid_player.time.sleep'):
            with self.assertRaises(PermissionError):
                atomic_json(target, {'value': 2})
        self.assertEqual(json.loads(target.read_text(encoding='utf-8')), {'value': 1})
        self.assertEqual(list(target.parent.glob('.memory.json.*.tmp')), [])

    def test_routing_selection_context(self):
        for t in ('monster', 'elite', 'boss', 'hand_select'):
            self.assertEqual(role_for({'state_type': t}, OPTIONS), 'combat')
        self.assertEqual(role_for({'state_type': 'card_select', 'battle': {'round': 1}}, OPTIONS), 'combat')
        self.assertEqual(role_for({'state_type': 'card_select'}, OPTIONS), 'planner')
        for t in ('map', 'card_reward', 'shop', 'rest_site', 'event'):
            self.assertEqual(role_for({'state_type': t}, OPTIONS), 'planner')

    def test_shop_exit_is_available_while_inventory_hides_proceed_button(self):
        state = {'state_type': 'shop', 'shop': {'can_proceed': False, 'items': [
            {'index': 0, 'is_stocked': True, 'can_afford': False},
        ]}, 'player': {'gold': 0}}
        options = game_actions.candidates(state)
        self.assertEqual(options, [({'action': 'proceed'}, 'Leave shop and save remaining gold')])
        self.assertEqual(role_for(state, options), 'automatic')

    def test_shop_planner_can_choose_between_purchase_and_exit(self):
        state = {'state_type': 'shop', 'shop': {'can_proceed': False, 'items': [
            {'index': 3, 'is_stocked': True, 'can_afford': True, 'name': 'item'},
        ]}, 'player': {'gold': 100}}
        options = game_actions.candidates(state)
        self.assertEqual([action['action'] for action, _ in options], ['shop_purchase', 'proceed'])
        self.assertEqual(role_for(state, options), 'planner')

    def test_missing_deck_prevents_planner_call(self):
        c = self.make(lambda *args: self.fail('Unexpected API call'))
        s = copy.deepcopy(STATE); del s['player']['deck']
        with self.assertRaisesRegex(RuntimeError, 'permanent'):
            c.decide(s, OPTIONS)

    def test_stale_state_never_executes_action_or_commits_plan(self):
        count = 0
        def transport(url, data, key):
            nonlocal count
            if url == CONFIG['planner_url']: return planner_response()
            self.assertIsNone(data, 'Must not POST game action')
            count += 1
            s = copy.deepcopy(STATE)
            if count > 1: s['player']['hp'] = 30
            return s
        c = self.make(transport)
        self.assertEqual(c.tick(), 'waiting')
        self.assertEqual(c.memory['plan']['deck_direction'], '')
        self.assertEqual(c.memory['calls']['planner'], 1)

    def test_journal_links_observation_decision_action_and_followup(self):
        calls = 0
        def transport(url, data, key):
            nonlocal calls
            if url == CONFIG['planner_url']:
                return planner_response()
            if data is not None:
                return {'status': 'ok'}
            calls += 1
            state = copy.deepcopy(STATE)
            if calls > 2:
                state['player']['hp'] = 39
            return state
        c = self.make(transport)
        self.assertEqual(c.tick(), 'acted')
        c.observe({**copy.deepcopy(STATE), 'player': {**STATE['player'], 'hp': 39}})
        self.assertEqual(c.journal.counts(), {
            'observations': 2, 'decisions': 1, 'actions': 1, 'battles': 0})
        with c.journal.connect() as db:
            row = db.execute('''SELECT d.observation_id, a.observation_id,
                                       a.settled_observation_id, a.settlement_status,
                                       d.legal_actions_json, d.usage_json
                                FROM decisions d JOIN actions a USING(decision_id)''').fetchone()
        self.assertEqual(row[0], row[1])
        self.assertTrue(row[2].startswith('observation_'))
        self.assertEqual(row[3], 'observed_changed')
        self.assertEqual(len(json.loads(row[4])), 2)
        self.assertNotIn('cost', row[5])

    def test_invalid_action_stops(self):
        c = self.make(lambda *args: planner_response('99'))
        with self.assertRaisesRegex(RuntimeError, 'unknown action'):
            c.decide(STATE, OPTIONS)

    def test_provider_billing_fields_are_not_persisted(self):
        requests = []
        def transport(url, data, key):
            requests.append(data)
            return planner_response()
        c = self.make(transport)
        c.decide(STATE, OPTIONS)
        self.assertEqual(requests[0]['max_tokens'], 32768)
        self.assertEqual(requests[0]['reasoning_effort'], 'low')
        self.assertNotIn('reported_cost_usd', c.memory)
        self.assertFalse((pathlib.Path(self.temp.name) / 'usage.json').exists())
        events = (pathlib.Path(self.temp.name) / 'events.jsonl').read_text()
        self.assertNotIn('"cost"', events)
        self.assertNotIn('reported_cost', events)

    def test_planner_reasoning_effort_is_configurable(self):
        requests = []
        c = self.make(lambda url, data, key: requests.append(data) or planner_response())
        c.config['planner_reasoning_effort'] = 'high'
        c.decide(STATE, OPTIONS)
        self.assertEqual(requests[0]['reasoning_effort'], 'high')

    def test_openrouter_does_not_request_usage_accounting(self):
        requests = []
        def transport(url, data, key):
            requests.append(data)
            return planner_response()
        c = self.make(transport)
        c.config['planner_url'] = 'https://openrouter.ai/api/v1/chat/completions'
        c.decide(STATE, OPTIONS)
        self.assertNotIn('usage', requests[0])

    def test_http_error_includes_safe_provider_detail(self):
        config = {**CONFIG, 'cross_run_memory': False}
        c = Controller(config, self.temp.name)
        c.stop_path = pathlib.Path(self.temp.name) / 'STOP'
        error = urllib.error.HTTPError('https://example.test', 400, 'Bad Request', {},
                                      io.BytesIO(b'{"error":"bad payload for secret-key"}'))
        with patch('urllib.request.urlopen', side_effect=error):
            with self.assertRaisesRegex(RuntimeError, 'bad payload') as raised:
                c.http('https://example.test', {'value': 1}, 'secret-key')
        self.assertNotIn('secret-key', str(raised.exception))

    def test_provider_network_failure_is_retryable_and_keeps_reason(self):
        config = {**CONFIG, 'cross_run_memory': False}
        c = Controller(config, self.temp.name)
        c.stop_path = pathlib.Path(self.temp.name) / 'STOP'
        error = urllib.error.URLError(ConnectionResetError('connection reset'))
        with patch('urllib.request.urlopen', side_effect=error) as request, \
                patch('hybrid_player.time.sleep'):
            with self.assertRaisesRegex(RetryableProviderError,
                                        'ConnectionResetError.*connection reset'):
                c.http('https://example.test', {'value': 1}, 'secret-key')
        self.assertEqual(request.call_count, 4)

    def test_stop_during_inference_prevents_action(self):
        c = None
        def transport(url, data, key):
            if url == CONFIG['planner_url']:
                c.stop_path.touch(); return planner_response()
            self.assertIsNone(data)
            return STATE
        c = self.make(transport)
        self.assertEqual(c.tick(), 'stopped')

    def test_plan_handoff_and_persistence(self):
        captured = []
        def transport(url, data, key):
            if url == CONFIG['planner_url']: return planner_response()
            if url == CONFIG['combat_url']:
                captured.append(data)
                return {'answers': {'action': {'choice': '0'}}}
            return {'status': 'ok'} if data else STATE
        c = self.make(transport)
        self.assertEqual(c.tick(), 'acted')
        c2 = self.make(transport)
        c2.decide({'state_type': 'monster'}, OPTIONS)
        self.assertEqual(captured[0]['state']['strategic_plan']['combat_guidance'], 'Plan')

    def test_generic_combat_json_protocol_and_key(self):
        from unittest.mock import patch
        captured = []
        def transport(url, data, key):
            captured.append((url,data,key))
            return {'choices':[{'finish_reason':'stop','message':{'content':'{"action_id":"0"}'}}]}
        c = self.make(transport)
        c.config.update(combat_protocol='chat_json', combat_url='https://example.test/chat/completions')
        with patch.dict('os.environ', {'SPIRE_COMBAT_KEY':'combat-only','SPIRE_PLANNER_KEY':'planner-only'}):
            c.decide({'state_type':'monster'}, OPTIONS)
        self.assertEqual(captured[0][2], 'combat-only')
        self.assertEqual(captured[0][1]['max_tokens'], 16384)
        self.assertEqual(captured[0][1]['response_format'], {'type':'json_object'})
        self.assertIn('legal_actions', captured[0][1]['messages'][1]['content'])

    def test_combat_token_overflow_retries_once_with_smaller_memory(self):
        requests = []
        def transport(url, data, key):
            requests.append(copy.deepcopy(data))
            if len(requests) == 1:
                raise RuntimeError('HTTP 400: {"error_type":"max_tokens_exceeded"}')
            return {'answers': {'action': {'choice': '0'}}}
        c = self.make(transport)
        c.memory['combat'] = {
            'location': {'act': 1, 'floor': 4},
            'observations': [{'round': i, 'blob': 'x' * 2500} for i in range(10)],
            'actions': [],
        }
        state = {'state_type': 'monster', 'player': {'deck': []}}
        choice, role, _ = c.decide(state, OPTIONS)
        self.assertEqual((choice, role), (0, 'combat'))
        self.assertEqual(len(requests), 2)
        first = len(json.dumps(requests[0], ensure_ascii=False).encode('utf-8'))
        second = len(json.dumps(requests[1], ensure_ascii=False).encode('utf-8'))
        self.assertLess(second, first)
        events = (pathlib.Path(self.temp.name) / 'events.jsonl').read_text(encoding='utf-8')
        self.assertIn('context_retry', events)

    def test_oversized_planner_plan_is_rejected(self):
        response = planner_response()
        content = json.loads(response['choices'][0]['message']['content'])
        content['plan']['deck_direction'] = 'x' * 301
        response['choices'][0]['message']['content'] = json.dumps(content)
        c = self.make(lambda *args: response)
        with self.assertRaisesRegex(RuntimeError, 'Invalid planner plan'):
            c.decide(STATE, OPTIONS)

    def test_game_over_has_no_action(self):
        c = self.make(lambda url, data, key: {'state_type': 'game_over', 'player': {'hp': 0}} if data is None else self.fail('Unexpected action'))
        self.assertEqual(c.tick(), 'game_over')

if __name__ == '__main__': unittest.main()
