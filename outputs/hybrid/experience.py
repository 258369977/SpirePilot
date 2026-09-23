"""Evidence-linked cross-run memory. No model claims are promoted to verified rules."""
import hashlib
import json
import pathlib
import sqlite3
import time
import re
from contextlib import contextmanager
from role_memory import strategic_state

SCREENS = ['map', 'card_reward', 'shop', 'rest_site', 'event', 'card_select', 'relic_select', 'bundle_select', 'monster', 'elite', 'boss', 'hand_select', 'any']

def readable_review(doc):
    lines = ['# 局后复盘', '', doc['review']['summary'], '',
             '以下为模型对日志的归纳与待验证假设；引用存在性已校验，结论正确性不因此得到保证。', '',
             f"来源局：{doc['run_id']}；适用版本范围：{doc['scope']}", '']
    for i, item in enumerate(doc['review']['lessons'], 1):
        lines += [f'## 经验 {i}', '', f"日志观察：{item['observation']}", '',
                  f"解释假设：{item['hypothesis']}", '', f"条件建议：{item['recommendation']}", '',
                  f"局限：{item['limitations']}", '',
                  f"适用：{item['role']} / {', '.join(item['screens'])}", '',
                  f"证据：{', '.join(item['evidence_ids'])}（对应 events.jsonl 行号或 result.json 最终状态）", '']
    return '\n'.join(lines)

def schema():
    string = {'type': 'string'}
    lesson = {'type': 'object', 'properties': {
        'observation': string, 'hypothesis': string, 'recommendation': string,
        'limitations': string, 'role': {'type': 'string', 'enum': ['planner', 'combat', 'both']},
        'screens': {'type': 'array', 'items': {'type': 'string', 'enum': SCREENS}},
        'enemy_ids': {'type': 'array', 'items': string},
        'evidence_ids': {'type': 'array', 'items': string}},
        'required': ['observation', 'hypothesis', 'recommendation', 'limitations', 'role', 'screens', 'enemy_ids', 'evidence_ids'],
        'additionalProperties': False}
    return {'type': 'object', 'properties': {'summary': string, 'lessons': {'type': 'array', 'items': lesson}},
            'required': ['summary', 'lessons'], 'additionalProperties': False}

def build_evidence(directory, planner_only=False):
    directory = pathlib.Path(directory)
    result = json.loads((directory / 'result.json').read_text(encoding='utf-8'))
    final = strategic_state(result['state']) if planner_only else result['state']
    evidence = []
    strategic = []
    combat = {}
    path = directory / 'events.jsonl'
    if path.exists():
        with path.open(encoding='utf-8') as f:
            for line_number, line in enumerate(f, 1):
                row = json.loads(line)
                if planner_only and row.get('kind') == 'battle_finished':
                    report = row.get('report')
                    strategic.append({'id': 'battle:' + str(row.get('battle_id') or line_number),
                                      'post_battle_report': report} if report else
                                     {'id': f'line:{line_number}',
                                      'post_battle_state': strategic_state(row['state'])})
                    continue
                if row.get('kind') != 'action':
                    continue
                s = row['state']; p = s.get('player', {}); battle = s.get('battle', {})
                if planner_only:
                    if s['state_type'] in {'monster', 'elite', 'boss', 'hand_select'} or battle:
                        continue
                    s = strategic_state(s); p = s.get('player', {}); battle = {}
                record = {'id': ('action:' + str(row['action_id']) if row.get('action_id')
                                 else f'line:{line_number}'),
                          'run': s.get('run'), 'screen': s['state_type'],
                          'hp': p.get('hp'), 'max_hp': p.get('max_hp'), 'gold': p.get('gold'),
                          'deck': p.get('deck'), 'relics': p.get('relics'), 'potions': p.get('potions'),
                          'hand': p.get('hand'), 'energy': p.get('energy'), 'block': p.get('block'),
                          'battle': battle, 'screen_data': s.get(s['state_type']),
                          'action': row['action'], 'result': row['result'],
                          'reason': (row.get('decision') or {}).get('reason')}
                if s['state_type'] in {'monster', 'elite', 'boss', 'hand_select'} or battle:
                    key = json.dumps(s.get('run'), sort_keys=True)
                    combat.setdefault(key, []).append(record)
                else:
                    strategic.append(record)
    # Include early and late strategic decisions, and first/last actions per fight.
    if len(strategic) > 32:
        strategic = strategic[:8] + strategic[-24:]
    evidence.extend(strategic)
    for records in list(combat.values())[-24:]:
        evidence.extend(records[:1] + records[-2:] if len(records) > 3 else records)
    final_record = {'id': 'final', 'state': final}
    evidence.append(final_record)
    # Bound payload while retaining the terminal observation.
    while len(json.dumps(evidence, ensure_ascii=False)) > 65000 and len(evidence) > 2:
        evidence.pop(0)
    character = final.get('player', {}).get('character')
    if not character:
        raise ValueError('Missing character in final state')
    return {'character': character, 'terminal_observation': final,
            'sampling_note': 'Partial log excerpts; actions show pre-action HP. Do not infer exact damage or causality from missing steps. Game-over alone does not prove victory.',
            'evidence': evidence}

def validate(review, evidence):
    if not isinstance(review.get('summary'), str) or len(review['summary']) > 4000:
        raise ValueError('Invalid review summary')
    lessons = review.get('lessons')
    if not isinstance(lessons, list) or len(lessons) > 8:
        raise ValueError('Expected at most eight lessons')
    valid_ids = {x['id'] for x in evidence['evidence']}
    valid_enemies = {
        e.get('entity_id')
        for x in evidence['evidence']
        for source in (x.get('battle', {}), x.get('post_battle_report', {}))
        for e in source.get('enemies', [])
        if e.get('entity_id')
    }
    for item in lessons:
        for k in ('observation', 'hypothesis', 'recommendation', 'limitations'):
            if not isinstance(item.get(k), str) or not item[k].strip() or len(item[k]) > 1500:
                raise ValueError('Invalid lesson text')
        if item.get('role') not in {'planner', 'combat', 'both'}:
            raise ValueError('Invalid role')
        for key, allowed, nonempty in [('evidence_ids', valid_ids, True), ('screens', set(SCREENS), True), ('enemy_ids', valid_enemies, False)]:
            value = item.get(key)
            if not isinstance(value, list) or (nonempty and not value) or any(not isinstance(v, str) or v not in allowed for v in value):
                raise ValueError('Invalid ' + key)

class ExperienceStore:
    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS reviews (run_id TEXT PRIMARY KEY, created REAL, character TEXT, scope TEXT, document TEXT)')
            db.execute('''CREATE TABLE IF NOT EXISTS combat_cases (
                battle_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, created REAL NOT NULL,
                character TEXT, scope TEXT NOT NULL, enemy_keys TEXT NOT NULL, document TEXT NOT NULL
            )''')
            db.execute('CREATE INDEX IF NOT EXISTS idx_combat_cases_lookup ON combat_cases(character, scope, created)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, run_id):
        with self.connect() as db:
            row = db.execute('SELECT document FROM reviews WHERE run_id=?', (run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, run_id, scope, review, evidence, model):
        validate(review, evidence)
        doc = {'run_id': run_id, 'scope': scope, 'character': evidence['character'], 'model': model,
               'review': review, 'evidence': evidence, 'status': 'model_generated_hypotheses',
               'evidence_hash': hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()}
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO reviews VALUES (?,?,?,?,?)',
                       (run_id, time.time(), evidence['character'], scope, json.dumps(doc, ensure_ascii=False)))
        return self.get(run_id)

    @staticmethod
    def enemy_key(value):
        return re.sub(r'_\d+$', '', str(value or '')).upper()

    def put_combat_case(self, run_id, scope, report):
        if not report.get('battle_id') or report.get('action_count', 0) <= 0:
            return None
        keys = sorted({self.enemy_key(e.get('entity_id') or e.get('name'))
                       for e in report.get('enemies', []) if e.get('entity_id') or e.get('name')})
        doc = {
            'source_run': run_id,
            'battle_id': report['battle_id'],
            'role': 'combat',
            'status': 'observed_case',
            'character': report.get('character'),
            'scope': scope,
            'enemy_keys': keys,
            'facts': report,
            'limitations': report.get('data_quality', {}),
        }
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO combat_cases VALUES (?,?,?,?,?,?,?)',
                       (report['battle_id'], run_id, time.time(), report.get('character'), scope,
                        json.dumps(keys), json.dumps(doc, ensure_ascii=False)))
        return doc

    def retrieve_combat_cases(self, state, scope, exclude_run, limit=5):
        character = state.get('player', {}).get('character')
        current = {self.enemy_key(e.get('entity_id') or e.get('name'))
                   for e in state.get('battle', {}).get('enemies', [])}
        with self.connect() as db:
            rows = db.execute('''SELECT document FROM combat_cases
                                 WHERE character=? AND scope=? AND run_id<>?
                                 ORDER BY created DESC LIMIT 200''',
                              (character, scope, exclude_run)).fetchall()
        candidates = []
        for recency, (raw,) in enumerate(rows):
            doc = json.loads(raw)
            overlap = current.intersection(doc.get('enemy_keys', []))
            score = len(overlap) * 20 - recency / 1000
            if current and not overlap:
                continue
            candidates.append((score, doc))
        candidates.sort(key=lambda item: item[0], reverse=True)
        return [doc for _, doc in candidates[:limit]]

    def list_memories(self, limit=100):
        entries = []
        with self.connect() as db:
            for created, raw in db.execute(
                    'SELECT created, document FROM reviews ORDER BY created DESC LIMIT ?', (limit,)):
                doc = json.loads(raw)
                entries.append((created, {
                    'role': 'planner', 'character': doc.get('character'),
                    'scope': doc.get('scope'), 'source_run': doc.get('run_id'),
                    'summary': doc.get('review', {}).get('summary', ''), 'document': doc}))
            for created, raw in db.execute(
                    'SELECT created, document FROM combat_cases ORDER BY created DESC LIMIT ?', (limit,)):
                doc = json.loads(raw)
                facts = doc.get('facts', {})
                enemies = '、'.join(e.get('name') or e.get('entity_id', '?')
                                     for e in facts.get('enemies', [])) or '未知敌人'
                location = facts.get('location', {})
                summary = (f"{enemies} · {facts.get('outcome', 'unknown')} · "
                           f"第 {location.get('act', '?')} 幕 / {location.get('floor', '?')} 层")
                entries.append((created, {
                    'role': 'combat', 'character': doc.get('character'),
                    'scope': doc.get('scope'), 'source_run': doc.get('source_run'),
                    'summary': summary, 'document': doc}))
        entries.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in entries[:limit]]

    def retrieve(self, s, role, scope, exclude_run, limit=5):
        if role == 'combat':
            return self.retrieve_combat_cases(s, scope, exclude_run, limit)
        character = s.get('player', {}).get('character')
        enemies = {e.get('entity_id') for e in s.get('battle', {}).get('enemies', [])}
        candidates = []
        with self.connect() as db:
            rows = db.execute('SELECT document FROM reviews WHERE character=? AND scope=? AND run_id<>? ORDER BY created DESC LIMIT 200',
                              (character, scope, exclude_run)).fetchall()
        for recency, (raw,) in enumerate(rows):
            doc = json.loads(raw)
            for lesson in doc['review']['lessons']:
                if lesson['role'] not in {role, 'both'}:
                    continue
                if s['state_type'] not in lesson['screens'] and 'any' not in lesson['screens']:
                    continue
                if lesson['enemy_ids'] and not enemies.intersection(lesson['enemy_ids']):
                    continue
                score = (10 if lesson['enemy_ids'] else 0) + (2 if s['state_type'] in lesson['screens'] else 0) - recency / 1000
                candidates.append((score, {'source_run': doc['run_id'], 'status': doc['status'], **lesson}))
        candidates.sort(key=lambda x: x[0], reverse=True)
        selected = []; seen = set()
        for _, lesson in candidates:
            signature = lesson['recommendation'].strip().lower()
            if signature in seen:
                continue
            seen.add(signature); selected.append(lesson)
            if len(selected) >= limit:
                break
        return selected
