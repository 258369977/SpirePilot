import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch
import desktop_bridge as bridge

class DesktopBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name) / 'hybrid'
        self.root.mkdir()
        self.patch = patch.object(bridge, 'ROOT', self.root)
        self.patch.start(); self.addCleanup(self.patch.stop)
        (self.root/'config.json').write_text(json.dumps({'planner_url':'keep-endpoint','max_model_calls':123}), encoding='utf-8')

    def test_config_preserves_unexposed_fields_and_no_secret(self):
        bridge.dispatch('save-config', {'planner_model':'deepseek/test','combat_model':'typesafe/test','memory_scope':'test','key':'DO_NOT_SAVE'})
        saved = json.loads((self.root/'config.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['planner_url'],'keep-endpoint')
        self.assertEqual(saved['max_model_calls'],123)
        self.assertNotIn('DO_NOT_SAVE',(self.root/'config.json').read_text(encoding='utf-8'))

    def test_fresh_clone_uses_template_until_first_save(self):
        (self.root/'config.json').unlink()
        (self.root/'config.example.json').write_text(json.dumps({
            'planner_model': 'example-planner', 'combat_model': 'example-combat',
            'memory_scope': 'example-scope', 'planner_key_env': 'SPIRE_PLANNER_KEY',
            'combat_key_env': 'SPIRE_COMBAT_KEY'}), encoding='utf-8')
        self.assertEqual(bridge.dispatch('config', {})['planner_model'], 'example-planner')
        self.assertFalse((self.root/'config.json').exists())
        bridge.dispatch('save-config', {
            'planner_model': 'selected-planner', 'combat_model': 'example-combat',
            'memory_scope': 'example-scope'})
        self.assertEqual(bridge.dispatch('config', {})['planner_model'], 'selected-planner')
        self.assertTrue((self.root/'config.json').exists())

    def test_planner_reasoning_effort_defaults_to_low(self):
        self.assertEqual(bridge.dispatch('config', {})['planner_reasoning_effort'], 'low')

    def test_planner_reasoning_effort_is_validated_and_saved(self):
        payload = {'planner_model':'a','combat_model':'b','memory_scope':'test',
                   'planner_reasoning_effort':'medium'}
        bridge.dispatch('save-config', payload)
        self.assertEqual(bridge.dispatch('config', {})['planner_reasoning_effort'], 'medium')
        with self.assertRaisesRegex(ValueError, '思考强度'):
            bridge.dispatch('save-config', {**payload, 'planner_reasoning_effort':'extreme'})

    def test_path_escape_blocked(self):
        for name in ('..', '../elsewhere', 'a/b'):
            with self.assertRaises(ValueError): bridge.run_path(name)

    def test_old_pid_reuse_not_reported_running(self):
        (self.root/'desktop_process.json').write_text(json.dumps({'pid':123,'identity':111}))
        with patch.object(bridge,'process_identity',return_value=222):
            self.assertFalse(bridge.active()[1])

    def test_stop_does_not_kill_process(self):
        bridge.dispatch('stop',{})
        self.assertTrue((self.root/'STOP').exists())

    def test_missing_process_identity_not_reported_running(self):
        (self.root/'desktop_process.json').write_text(json.dumps({'pid':123,'identity':None}))
        with patch.object(bridge,'process_identity',return_value=None):
            self.assertFalse(bridge.active()[1])

    def test_start_refuses_existing_lock(self):
        (self.root/'controller.lock').touch()
        with self.assertRaises(ValueError): bridge.dispatch('start',{})

    def test_empty_history_is_valid(self):
        self.assertEqual(bridge.dispatch('history',{}),[])

    def test_delete_run_removes_only_selected_record(self):
        selected = self.root/'runs'/'selected'
        other = self.root/'runs'/'other'
        selected.mkdir(parents=True); other.mkdir()
        (selected/'memory.json').write_text('{}', encoding='utf-8')
        (other/'memory.json').write_text('{}', encoding='utf-8')
        result = bridge.dispatch('delete-run', {'run':'selected'})
        self.assertEqual(result, {'deleted':'selected'})
        self.assertFalse(selected.exists())
        self.assertTrue(other.exists())

    def test_delete_run_refuses_active_record(self):
        selected = self.root/'runs'/'selected'
        selected.mkdir(parents=True)
        (self.root/'desktop_process.json').write_text(json.dumps({'pid':123,'identity':111,'run':'selected'}))
        with patch.object(bridge, 'process_identity', return_value=111):
            with self.assertRaisesRegex(ValueError, '正在运行'):
                bridge.dispatch('delete-run', {'run':'selected'})
        self.assertTrue(selected.exists())

    def test_delete_run_rejects_path_escape_and_missing_record(self):
        with self.assertRaises(ValueError):
            bridge.dispatch('delete-run', {'run':'../outside'})
        with self.assertRaisesRegex(ValueError, '找不到'):
            bridge.dispatch('delete-run', {'run':'missing'})

    def test_delete_run_clears_stale_process_record(self):
        selected = self.root/'runs'/'selected'
        selected.mkdir(parents=True)
        (self.root/'desktop_process.json').write_text(json.dumps({'pid':123,'identity':111,'run':'selected'}))
        with patch.object(bridge, 'process_identity', return_value=None):
            bridge.dispatch('delete-run', {'run':'selected'})
        self.assertFalse((self.root/'desktop_process.json').exists())

    def test_two_keys_do_not_collide_with_shared_legacy_env(self):
        config = {'planner_key_env':'SAME', 'combat_key_env':'SAME'}
        with patch.dict('os.environ', {}, clear=True):
            env = bridge.model_environment(config, {'planner_key':'plan-secret', 'combat_key':'fight-secret'}, 'start')
        self.assertEqual(env['SPIRE_PLANNER_KEY'], 'plan-secret')
        self.assertEqual(env['SPIRE_COMBAT_KEY'], 'fight-secret')

    def test_review_requires_only_planner_key(self):
        with patch.dict('os.environ', {}, clear=True):
            env = bridge.model_environment({'planner_key_env':'P'}, {'planner_key':'review-secret'}, 'review')
        self.assertNotIn('SPIRE_COMBAT_KEY', env)

    def test_provider_save_roundtrip_excludes_keys(self):
        payload = {'planner_model':'a','combat_model':'b','memory_scope':'test',
                   'planner_url':'https://api.deepseek.com/chat/completions','planner_provider':'DeepSeek','planner_protocol':'chat_json',
                   'combat_url':'https://openrouter.ai/api/alpha/decisions','combat_provider':'OpenRouter','combat_protocol':'decisions',
                   'planner_key':'secret-one','combat_key':'secret-two'}
        bridge.dispatch('save-config',payload)
        saved = bridge.dispatch('config',{})
        self.assertEqual(saved['planner_protocol'],'chat_json')
        self.assertEqual(saved['combat_protocol'],'decisions')
        self.assertNotIn('secret-',json.dumps(saved))

    def test_legacy_pricing_fields_are_removed(self):
        current = json.loads((self.root/'config.json').read_text(encoding='utf-8'))
        current['planner_input_price_per_million'] = 1.25
        current['combat_output_price_per_million'] = 2
        (self.root/'config.json').write_text(json.dumps(current), encoding='utf-8')
        payload = {'planner_model':'a','combat_model':'b','memory_scope':'test',
                   'planner_input_price_per_million': 99,
                   'combat_output_price_per_million': 99}
        bridge.dispatch('save-config', payload)
        saved = bridge.dispatch('config', {})
        self.assertFalse(any('price_per_million' in key for key in saved))

    def test_openrouter_protocol_and_endpoint_must_match(self):
        base = {'planner_model':'a','combat_model':'b','memory_scope':'test',
                'planner_url':'https://openrouter.ai/api/v1/chat/completions','planner_provider':'OpenRouter','planner_protocol':'chat_schema',
                'combat_provider':'OpenRouter'}
        with self.assertRaisesRegex(ValueError, 'Decisions'):
            bridge.dispatch('save-config', {**base, 'combat_url':'https://openrouter.ai/api/v1/chat/completions', 'combat_protocol':'decisions'})
        with self.assertRaisesRegex(ValueError, '聊天接口'):
            bridge.dispatch('save-config', {**base, 'combat_url':'https://openrouter.ai/api/alpha/decisions', 'combat_protocol':'chat_schema'})

if __name__=='__main__': unittest.main()
