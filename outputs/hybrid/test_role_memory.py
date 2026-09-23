import copy
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from hybrid_player import Controller
import role_memory
from experience import ExperienceStore, build_evidence
from test_hybrid import CONFIG, STATE, OPTIONS, planner_response


class RoleMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.requests = []
        self.state = copy.deepcopy(STATE)
        self.state.update(state_type='monster', battle={'round': 1, 'private_marker': 'tactics'})
        self.state['player']['hand'] = [{'name': 'private_card'}]
        self.config = {**CONFIG, 'cross_run_memory': False}
        self.c = Controller(self.config, self.root, self.transport)
        self.c.stop_path = self.root / 'STOP'

    def transport(self, url, payload, key):
        if url == CONFIG['game_url']:
            return copy.deepcopy(self.state) if payload is None else {'status': 'ok'}
        self.requests.append(payload)
        return ({'answers': {'action': {'choice': '0'}}} if url == CONFIG['combat_url']
                else planner_response())

    def fight_action(self):
        with patch('hybrid_player.action_options', return_value=[({'action': 'end_turn'}, 'End')]):
            self.assertEqual(self.c.tick(), 'acted')

    def test_automatic_combat_action_is_private_and_survives_resume(self):
        self.fight_action()
        self.assertEqual(self.c.memory['planner']['decisions'], [])
        resumed = Controller(self.config, self.root, self.transport)
        resumed.decide(self.state, OPTIONS)
        history = self.requests[-1]['state']['battle_memory']
        self.assertEqual(history['recent_actions'][0]['action']['action'], 'end_turn')
        self.assertEqual(history['observations'][0]['player']['hand'][0]['name'], 'private_card')
        self.assertNotIn('deck', history['observations'][0]['player'])

    def test_planner_sees_only_post_battle_snapshot_and_combat_resets(self):
        self.fight_action()
        self.state = copy.deepcopy(STATE)
        self.state['player'].update(hp=21, hand=[{'name': 'private_card'}])
        self.c.observe(self.state)
        self.c.observe(self.state)
        self.c.decide(self.state, OPTIONS)
        context = json.loads(self.requests[-1]['messages'][1]['content'])
        self.assertNotIn('private_card', json.dumps(context))
        self.assertNotIn('tactics', json.dumps(context))
        self.assertEqual(context['planner_decisions'], [])
        self.assertEqual(len(context['battle_reports']), 1)
        self.assertEqual(context['battle_reports'][0]['end_state']['player']['hp'], 21)
        self.assertNotIn('action_counts', context['battle_reports'][0])
        self.assertIsNone(self.c.memory['combat'])
        self.state.update(state_type='monster', battle={'round': 1})
        self.state['run']['floor'] += 1
        self.c.observe(self.state)
        self.assertEqual(self.c.memory['combat']['recent_actions'], [])

    def test_selection_overlay_and_unknown_screen_do_not_finish_fight(self):
        self.fight_action()
        self.state.update(state_type='card_select')
        self.c.observe(self.state)
        self.state = {'state_type': 'loading'}
        self.c.observe(self.state)
        self.assertIsNotNone(self.c.memory['combat'])
        self.assertEqual(self.c.memory['planner']['battle_reports'], [])

    def test_terminal_combat_message_resets_memory_on_same_floor(self):
        self.fight_action()
        ended = copy.deepcopy(self.state)
        ended['message'] = 'Combat ended. Waiting for rewards...'
        ended.pop('battle', None)
        self.c.observe(ended)
        self.assertIsNone(self.c.memory['combat'])
        self.assertEqual(len(self.c.memory['planner']['battle_reports']), 1)

        next_fight = copy.deepcopy(self.state)
        next_fight['battle'] = {'round': 1, 'turn': 'player', 'enemies': [{'name': 'Next enemy', 'hp': 10}]}
        self.c.observe(next_fight)
        self.assertEqual(len(self.c.memory['combat']['observations']), 1)
        self.assertEqual(self.c.memory['combat']['recent_actions'], [])

    def test_combat_case_keeps_tactics_while_planner_gets_only_handoff(self):
        self.c.experience = ExperienceStore(self.root / 'lessons.sqlite3')
        self.c.scope = 'test-scope'
        self.fight_action()
        ended = copy.deepcopy(STATE)
        ended['state_type'] = 'rewards'
        ended['player'].update(character='Ironclad', hp=35)
        self.c.observe(ended)
        entries = self.c.experience.list_memories()
        self.assertEqual([entry['role'] for entry in entries], ['combat'])
        facts = entries[0]['document']['facts']
        self.assertEqual(facts['action_counts'], {'end_turn': 1})
        self.c.decide(ended, OPTIONS)
        planner_context = json.loads(self.requests[-1]['messages'][1]['content'])
        self.assertNotIn('end_turn', json.dumps(planner_context))
        self.assertEqual(planner_context['battle_reports'][0]['end_resources']['hp'], 35)

    def test_combat_history_is_compact_and_bounded(self):
        self.state['player']['deck'] = [{'name': 'Verbose', 'description': 'x' * 4000}] * 20
        self.state['player']['hand'] = [{'name': 'Card', 'description': 'y' * 4000, 'index': 0}]
        for round_number in range(1, 25):
            self.state['battle']['round'] = round_number
            self.state['player']['hp'] = 80 - round_number
            self.c.observe(self.state)
        history = self.c.memory['combat']['observations']
        self.assertLessEqual(len(history), role_memory.COMBAT_HISTORY_LIMIT)
        self.assertLessEqual(role_memory.estimated_tokens(history), role_memory.COMBAT_HISTORY_TOKENS)
        self.assertNotIn('deck', history[-1]['player'])
        self.assertNotIn('description', history[-1]['player']['hand'][0])

    def test_planner_groups_duplicate_cards(self):
        state = copy.deepcopy(STATE)
        state['player']['deck'] = [
            {'id': 'STRIKE', 'name': 'Strike', 'description': 'Damage', 'is_upgraded': False},
            {'id': 'STRIKE', 'name': 'Strike', 'description': 'Damage', 'is_upgraded': False},
            {'id': 'STRIKE', 'name': 'Strike+', 'description': 'More damage', 'is_upgraded': True},
        ]
        compact = role_memory.strategic_state(state)
        self.assertEqual([card['count'] for card in compact['player']['deck']], [2, 1])

    def test_planner_context_budget_preserves_current_state_and_actions(self):
        context = {
            'game': {'state_type': 'card_reward', 'player': {'deck': [{'name': 'Strike'}]}},
            'legal_actions': {'0': {'action': {'action': 'skip'}}},
            'previous_plan': {'deck_direction': 'keep'},
            'past_planner_hypotheses': [{'recommendation': 'x' * 8000} for _ in range(5)],
            'battle_reports': [{'summary': 'y' * 8000} for _ in range(5)],
            'planner_decisions': [{'description': 'z' * 4000} for _ in range(12)],
        }
        trimmed = role_memory.trim_context(
            context, 48000, ('past_planner_hypotheses', 'battle_reports', 'planner_decisions'))
        self.assertLessEqual(role_memory.estimated_tokens(trimmed), 48000)
        self.assertEqual(trimmed['game'], context['game'])
        self.assertEqual(trimmed['legal_actions'], context['legal_actions'])

    def test_planner_review_excludes_combat_logs_even_at_game_over(self):
        self.fight_action()
        self.state.update(state_type='game_over')
        self.state['player']['character'] = 'Ironclad'
        self.c.observe(self.state)
        (self.root / 'result.json').write_text(json.dumps({'state': self.state}), encoding='utf-8')
        evidence = build_evidence(self.root, planner_only=True)
        self.assertNotIn('private_card', json.dumps(evidence))
        self.assertNotIn('tactics', json.dumps(evidence))
        self.assertNotIn('end_turn', json.dumps(evidence))
        self.assertEqual(len(evidence['evidence']), 2)

    def test_incompatible_memory_history_is_reset(self):
        old = copy.deepcopy(self.c.memory)
        old['memory_version'] = 3
        old['planner']['recent_actions'] = [{'role': 'planner', 'action': 'map'}]
        old['combat'] = {'location': {}, 'observations': [self.state], 'actions': []}
        old['reported_cost_usd'] = 1.25
        (self.root / 'memory.json').write_text(json.dumps(old), encoding='utf-8')
        resumed = Controller(self.config, self.root, self.transport)
        self.assertEqual(resumed.memory['planner']['decisions'], [])
        self.assertIsNone(resumed.memory['combat'])
        self.assertEqual(resumed.memory['memory_version'], 5)
        self.assertNotIn('reported_cost_usd', resumed.memory)
        resumed_again = Controller(self.config, self.root, self.transport)
        self.assertNotIn('reported_cost_usd', resumed_again.memory)


if __name__ == '__main__':
    unittest.main()
