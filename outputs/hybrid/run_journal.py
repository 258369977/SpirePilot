"""Durable, linked run facts. Model-facing memory is derived from this journal."""
import hashlib
import json
import pathlib
import sqlite3
import time
import uuid
from contextlib import contextmanager


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class RunJournal:
    SCHEMA_VERSION = 1

    def __init__(self, path, run_id):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS observations (
                    observation_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, created REAL NOT NULL,
                    state_type TEXT, act INTEGER, floor INTEGER, battle_id TEXT,
                    digest TEXT NOT NULL, state_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    decision_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, created REAL NOT NULL,
                    observation_id TEXT NOT NULL, role TEXT NOT NULL, model TEXT,
                    status TEXT NOT NULL, legal_actions_json TEXT NOT NULL,
                    decision_json TEXT, retrieved_memory_json TEXT NOT NULL,
                    seconds REAL, usage_json TEXT,
                    FOREIGN KEY(observation_id) REFERENCES observations(observation_id)
                );
                CREATE TABLE IF NOT EXISTS actions (
                    action_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, created REAL NOT NULL,
                    observation_id TEXT NOT NULL, decision_id TEXT NOT NULL, role TEXT NOT NULL,
                    action_json TEXT NOT NULL, result_json TEXT NOT NULL,
                    settled_observation_id TEXT, settlement_status TEXT NOT NULL,
                    FOREIGN KEY(observation_id) REFERENCES observations(observation_id),
                    FOREIGN KEY(decision_id) REFERENCES decisions(decision_id),
                    FOREIGN KEY(settled_observation_id) REFERENCES observations(observation_id)
                );
                CREATE TABLE IF NOT EXISTS battles (
                    battle_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, created REAL NOT NULL,
                    started_observation_id TEXT, ended_observation_id TEXT,
                    outcome TEXT NOT NULL, report_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_observations_battle ON observations(battle_id, created);
                CREATE INDEX IF NOT EXISTS idx_decisions_observation ON decisions(observation_id);
                CREATE INDEX IF NOT EXISTS idx_actions_observation ON actions(observation_id);
            ''')
            current = db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
            if current and int(current[0]) != self.SCHEMA_VERSION:
                raise RuntimeError('Unsupported run journal schema')
            db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',
                       ('schema_version', str(self.SCHEMA_VERSION)))
            db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)', ('run_id', run_id))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def new_id(prefix):
        return f'{prefix}_{uuid.uuid4().hex}'

    def set_metadata(self, key, value):
        """Store local provenance without adding it to any model prompt."""
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',
                       (str(key), canonical(value)))

    def record_observation(self, observation_id, state, battle_id=None):
        run = state.get('run') or {}
        raw = canonical(state)
        digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        with self.connect() as db:
            db.execute('INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?)',
                       (observation_id, self.run_id, time.time(), state.get('state_type'),
                        run.get('act'), run.get('floor'), battle_id, digest, raw))
        return digest

    def record_decision(self, observation_id, role, model, legal_actions, decision,
                        retrieved_memory, seconds=None, usage=None, status='selected'):
        decision_id = self.new_id('decision')
        with self.connect() as db:
            db.execute('INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                       (decision_id, self.run_id, time.time(), observation_id, role, model,
                        status, canonical(legal_actions),
                        canonical(decision) if decision is not None else None,
                        canonical(retrieved_memory or []), seconds,
                        canonical(usage) if usage is not None else None))
        return decision_id

    def update_decision_status(self, decision_id, status):
        with self.connect() as db:
            db.execute('UPDATE decisions SET status=? WHERE decision_id=?',
                       (status, decision_id))

    def record_action(self, observation_id, decision_id, role, action, result):
        action_id = self.new_id('action')
        with self.connect() as db:
            db.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (action_id, self.run_id, time.time(), observation_id, decision_id,
                        role, canonical(action), canonical(result), None, 'awaiting_observation'))
        return action_id

    def settle_action(self, action_id, observation_id, status='observed_after'):
        with self.connect() as db:
            db.execute('UPDATE actions SET settled_observation_id=?, settlement_status=? WHERE action_id=?',
                       (observation_id, status, action_id))

    def record_battle(self, report):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO battles VALUES (?,?,?,?,?,?,?)',
                       (report['battle_id'], self.run_id, time.time(),
                        report.get('started_observation_id'), report.get('ended_observation_id'),
                        report['outcome'], canonical(report)))

    def counts(self):
        with self.connect() as db:
            return {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                    for table in ('observations', 'decisions', 'actions', 'battles')}
