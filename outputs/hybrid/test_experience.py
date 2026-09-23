import copy
import json
import pathlib
import tempfile
import unittest
from experience import ExperienceStore, build_evidence
from hybrid_player import Controller

class ExperienceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.store = ExperienceStore(self.root / 'memory.sqlite3')
        self.evidence = {'character': 'Ironclad', 'evidence': [{'id': 'line:1', 'battle': {'enemies': [{'entity_id': 'WORM_0'}]}}]}
        self.lesson = {'observation': 'Low HP before elite.', 'hypothesis': 'Safer route might help.',
                       'recommendation': 'Consider rest when low HP.', 'limitations': 'One run, no counterfactual.',
                       'role': 'planner', 'screens': ['map'], 'enemy_ids': [], 'evidence_ids': ['line:1']}
        self.review = {'summary': 'One run.', 'lessons': [self.lesson]}

    def test_idempotent_insert(self):
        self.store.put('r1', 'v1', self.review, self.evidence, 'test')
        self.store.put('r1', 'v1', self.review, self.evidence, 'test')
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM reviews').fetchone()[0], 1)

    def test_hallucinated_evidence_rejected(self):
        self.lesson['evidence_ids'] = ['line:999']
        with self.assertRaises(ValueError):
            self.store.put('r1', 'v1', self.review, self.evidence, 'test')
        self.assertIsNone(self.store.get('r1'))

    def test_planner_lesson_can_cite_enemy_from_battle_handoff(self):
        evidence = {'character': 'Ironclad', 'evidence': [{
            'id': 'battle:r1:1',
            'post_battle_report': {'enemies': [{'entity_id': 'WORM_0'}]}
        }]}
        review = copy.deepcopy(self.review)
        review['lessons'][0]['evidence_ids'] = ['battle:r1:1']
        review['lessons'][0]['enemy_ids'] = ['WORM_0']
        self.store.put('r1', 'v1', review, evidence, 'test')
        self.assertIsNotNone(self.store.get('r1'))

    def test_scope_character_role_and_current_run_filters(self):
        self.store.put('r1', 'v1', self.review, self.evidence, 'test')
        s = {'state_type': 'map', 'player': {'character': 'Ironclad'}}
        self.assertEqual(len(self.store.retrieve(s, 'planner', 'v1', 'new')), 1)
        for role, scope, run in [('combat', 'v1', 'new'), ('planner', 'v2', 'new'), ('planner', 'v1', 'r1')]:
            self.assertEqual(self.store.retrieve(s, role, scope, run), [])
        s['player']['character'] = 'Defect'
        self.assertEqual(self.store.retrieve(s, 'planner', 'v1', 'new'), [])

    def test_enemy_specific_memory(self):
        report = {'battle_id':'r1:battle:1','character':'Ironclad','outcome':'victory',
                  'action_count':3,'enemies':[{'entity_id':'WORM_2','combat_id':7}],
                  'data_quality':{'exact_damage_breakdown':False}}
        self.store.put_combat_case('r1', 'v1', report)
        s = {'state_type': 'monster', 'player': {'character': 'Ironclad'}, 'battle': {'enemies': [{'entity_id': 'OTHER_0'}]}}
        self.assertEqual(self.store.retrieve(s, 'combat', 'v1', 'new'), [])
        s['battle']['enemies'][0]['entity_id'] = 'WORM_0'
        self.assertEqual(len(self.store.retrieve(s, 'combat', 'v1', 'new')), 1)
        self.assertEqual(self.store.retrieve(s, 'planner', 'v1', 'new'), [])

    def test_library_lists_planner_and_combat_separately(self):
        self.store.put('r1', 'v1', self.review, self.evidence, 'test')
        self.store.put_combat_case('r1', 'v1', {
            'battle_id':'r1:battle:1','character':'Ironclad','outcome':'victory',
            'action_count':2,'location':{'act':1,'floor':4},
            'enemies':[{'entity_id':'WORM_0','name':'Worm'}], 'data_quality':{}})
        entries = self.store.list_memories()
        self.assertEqual({entry['role'] for entry in entries}, {'planner', 'combat'})
        self.assertTrue(all(entry['summary'] for entry in entries))

    def test_role_names_are_not_rewritten(self):
        self.store.put('r1', 'v1', self.review, self.evidence, 'test')
        with self.store.connect() as db:
            raw = db.execute('SELECT document FROM reviews WHERE run_id=?', ('r1',)).fetchone()[0]
            doc = json.loads(raw)
            doc['review']['lessons'][0]['role'] = 'planner'
            db.execute('UPDATE reviews SET document=? WHERE run_id=?', (json.dumps(doc), 'r1'))
        loaded = ExperienceStore(self.root / 'memory.sqlite3').get('r1')
        self.assertEqual(loaded['review']['lessons'][0]['role'], 'planner')

    def fixture(self):
        final = {'state_type': 'game_over', 'player': {'character': 'Ironclad', 'hp': 0}, 'run': {'floor': 10}}
        (self.root / 'result.json').write_text(json.dumps({'state': final}), encoding='utf-8')
        row = {'kind': 'action', 'state': {'state_type': 'map', 'player': {'character': 'Ironclad', 'hp': 10}, 'run': {'floor': 9}},
               'action': {'action': 'choose_map_node', 'index': 0}, 'result': {'status': 'ok'}}
        (self.root / 'events.jsonl').write_text(json.dumps(row)+'\n', encoding='utf-8')
        cfg = json.loads((pathlib.Path(__file__).parent / 'config.example.json').read_text(encoding='utf-8'))
        cfg['experience_db'] = str(self.root / 'memory.sqlite3')
        return cfg

    def test_review_then_new_run_retrieval_without_second_call(self):
        cfg = self.fixture(); calls = []
        def transport(*args):
            calls.append(args)
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(self.review)}}], 'usage': {'cost': .001}}
        c = Controller(cfg, self.root, transport); c.stop_path = self.root / 'STOP'
        c.review_run(); c.review_run()
        self.assertEqual(len(calls), 1)
        self.assertEqual(json.loads((self.root / 'review_status.json').read_text())['status'], 'complete')
        c2 = Controller(cfg, self.root / 'newrun', transport)
        lessons = c2.experience.retrieve({'state_type': 'map', 'player': {'character': 'Ironclad'}}, 'planner', c2.scope, c2.memory['run_id'])
        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0]['status'], 'model_generated_hypotheses')

    def test_failure_preserves_result_and_allows_retry(self):
        cfg = self.fixture()
        def fail(*args): raise RuntimeError('Offline')
        c = Controller(cfg, self.root, fail); c.stop_path = self.root / 'STOP'
        c.review_run()
        self.assertTrue((self.root / 'result.json').exists())
        self.assertEqual(json.loads((self.root / 'review_status.json').read_text())['status'], 'pending')
        self.assertIsNone(c.experience.get(c.memory['run_id']))

    def test_summary_preserves_terminal_and_sources(self):
        self.fixture()
        e = build_evidence(self.root)
        self.assertEqual([x['id'] for x in e['evidence']], ['line:1', 'final'])
        self.assertEqual(e['terminal_observation']['player']['hp'], 0)

if __name__ == '__main__': unittest.main()
