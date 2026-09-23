"""Role-separated working memory derived from durable run facts."""
import copy
import json

POST_COMBAT = {'rewards', 'card_reward', 'map', 'shop', 'rest_site', 'event', 'game_over'}
MEMORY_VERSION = 5
COMBAT_HISTORY_LIMIT = 30
COMBAT_HISTORY_TOKENS = 40000
PLANNER_DECISION_LIMIT = 40
PLANNER_BATTLE_REPORT_LIMIT = 24
PLANNER_HISTORY_TOKENS = 64000


def estimated_tokens(value):
    """Conservative provider-independent estimate: at most one Unicode character per token."""
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')))


def _bounded(items, max_items, max_tokens):
    items = items[-max_items:]
    while len(items) > 1 and estimated_tokens(items) > max_tokens:
        items.pop(0)
    return items


def _text(value, limit):
    return value[:limit] if isinstance(value, str) else value


def normalize_role(role):
    return role


def normalize_action(item):
    item = copy.deepcopy(item)
    if 'description' in item:
        item['description'] = _text(item['description'], 300)
    if 'reason' in item:
        item['reason'] = _text(item['reason'], 500)
    return item


def _compact_status(values):
    return [{k: copy.deepcopy(value[k]) for k in ('id', 'name', 'amount', 'type') if k in value}
            for value in values or []]


def _compact_cards(cards, include_description=False):
    """Group permanent duplicate cards while preserving upgrades and enchantments."""
    grouped = {}
    order = []
    keys = ('id', 'name', 'is_upgraded', 'cost', 'star_cost', 'type', 'rarity',
            'enchantments', 'affliction')
    for card in cards or []:
        compact = {k: copy.deepcopy(card[k]) for k in keys if k in card}
        if include_description and 'description' in card:
            compact['description'] = _text(card['description'], 700)
        signature = json.dumps(compact, ensure_ascii=False, sort_keys=True)
        if signature not in grouped:
            grouped[signature] = compact
            grouped[signature]['count'] = 0
            order.append(signature)
        count = card.get('count', 1)
        grouped[signature]['count'] += count if isinstance(count, int) and count > 0 else 1
    return [grouped[key] for key in order]


def _compact_items(values):
    keys = ('id', 'name', 'description', 'counter', 'slot', 'target_type', 'can_use_in_combat')
    return [{k: _text(copy.deepcopy(value[k]), 700) for k in keys if k in value}
            for value in values or []]


def strategic_state(state):
    """Expose strategic resources and screen data without private combat history."""
    player = state.get('player', {})
    snapshot = copy.deepcopy(state)
    snapshot.pop('battle', None)
    compact_player = {k: copy.deepcopy(player[k]) for k in
                      ('character', 'hp', 'max_hp', 'gold', 'max_potion_slots') if k in player}
    if 'deck' in player:
        compact_player['deck'] = _compact_cards(player['deck'], include_description=True)
    if 'relics' in player:
        compact_player['relics'] = _compact_items(player['relics'])
    if 'potions' in player:
        compact_player['potions'] = _compact_items(player['potions'])
    snapshot['player'] = compact_player
    return snapshot


def combat_finished(state):
    battle = state.get('battle') or {}
    if battle.get('is_over') or battle.get('combat_over'):
        return True
    message = str(state.get('message') or '').casefold()
    return 'combat ended' in message or 'waiting for rewards' in message


def combat_snapshot(state, observation_id=None):
    """Record changing tactical facts. The current full game is always sent separately."""
    player = state.get('player') or {}
    battle = state.get('battle') or {}
    result = {
        'observation_id': observation_id,
        'state_type': state.get('state_type'),
        'round': battle.get('round'),
        'turn': battle.get('turn'),
        'player': {k: copy.deepcopy(player[k]) for k in
                   ('hp', 'max_hp', 'block', 'energy', 'max_energy', 'stars',
                    'draw_pile_count', 'discard_pile_count', 'exhaust_pile_count',
                    'orb_slots', 'orb_empty_slots') if k in player},
        'enemies': [],
    }
    if player.get('status'):
        result['player']['status'] = _compact_status(player['status'])
    if 'hand' in player:
        result['player']['hand'] = [
            {k: copy.deepcopy(card[k]) for k in
             ('id', 'name', 'index', 'cost', 'star_cost', 'can_play', 'target_type') if k in card}
            for card in player['hand']
        ]
    if 'potions' in player:
        result['player']['potions'] = _compact_items(player['potions'])
    if 'orbs' in player:
        result['player']['orbs'] = [
            {k: copy.deepcopy(orb[k]) for k in ('id', 'name', 'passive_val', 'evoke_val') if k in orb}
            for orb in player['orbs']
        ]
    for enemy in battle.get('enemies', []):
        item = {k: copy.deepcopy(enemy[k]) for k in
                ('entity_id', 'combat_id', 'name', 'hp', 'max_hp', 'block') if k in enemy}
        if enemy.get('status'):
            item['status'] = _compact_status(enemy['status'])
        if enemy.get('intents'):
            item['intents'] = [{k: copy.deepcopy(intent[k]) for k in
                                ('type', 'label', 'title', 'description') if k in intent}
                               for intent in enemy['intents']]
        result['enemies'].append(item)
    return result


def _location(state):
    run = state.get('run') or {}
    return {k: run[k] for k in ('act', 'floor') if k in run}


def initialize(memory):
    if memory.get('memory_version') != MEMORY_VERSION:
        run_id = memory.get('run_id')
        memory.clear()
        memory.update({
            'run_id': run_id,
            'plan': {k: '' for k in ('deck_direction', 'card_priorities', 'route_policy',
                                      'resource_policy', 'combat_guidance')},
            'planner': {'decisions': [], 'battle_reports': []},
            'combat': None,
            'calls': {'planner': 0, 'combat': 0, 'review': 0},
            'battle_counter': 0,
            'pending_action': None,
            'memory_version': MEMORY_VERSION,
        })
        return
    memory.setdefault('planner', {}).setdefault('decisions', [])
    memory['planner'].setdefault('battle_reports', [])
    memory['planner']['decisions'] = _bounded(memory['planner']['decisions'],
                                               PLANNER_DECISION_LIMIT, PLANNER_HISTORY_TOKENS)
    memory['planner']['battle_reports'] = _bounded(memory['planner']['battle_reports'],
                                                    PLANNER_BATTLE_REPORT_LIMIT, PLANNER_HISTORY_TOKENS)
    memory.setdefault('combat', None)
    memory.setdefault('battle_counter', 0)
    memory.setdefault('pending_action', None)
    calls = memory.setdefault('calls', {})
    for role in ('planner', 'combat', 'review'):
        calls.setdefault(role, 0)
    memory['memory_version'] = MEMORY_VERSION


def _new_battle(memory, state, observation_id):
    memory['battle_counter'] += 1
    battle_id = f"{memory['run_id']}:battle:{memory['battle_counter']}"
    snapshot = combat_snapshot(state, observation_id)
    player = state.get('player') or {}
    battle = state.get('battle') or {}
    return {
        'battle_id': battle_id,
        'location': _location(state),
        'started_observation_id': observation_id,
        'start_state': strategic_state(state),
        'enemies': [{k: copy.deepcopy(e[k]) for k in
                     ('entity_id', 'combat_id', 'name', 'max_hp') if k in e}
                    for e in battle.get('enemies', [])],
        'observations': [snapshot],
        'recent_actions': [],
        'action_count': 0,
        'action_counts': {},
        'cards_played': {},
        'potions_used': [],
        'rounds_seen': [battle.get('round')] if battle.get('round') is not None else [],
        'hp_samples': [player.get('hp')] if isinstance(player.get('hp'), (int, float)) else [],
    }


def _battle_report(active, state, observation_id):
    end_state = strategic_state(state)
    end_player = state.get('player') or {}
    start_player = (active.get('start_state') or {}).get('player') or {}
    start_hp = start_player.get('hp')
    end_hp = end_player.get('hp')
    terminal = state.get('state_type') == 'game_over'
    outcome = 'defeat' if terminal and isinstance(end_hp, (int, float)) and end_hp <= 0 else (
        'victory' if state.get('state_type') in POST_COMBAT and not terminal else 'unknown')
    net_hp = end_hp - start_hp if isinstance(start_hp, (int, float)) and isinstance(end_hp, (int, float)) else None
    return {
        'battle_id': active['battle_id'],
        'location': active['location'],
        'character': start_player.get('character') or end_player.get('character'),
        'enemies': active.get('enemies', []),
        'outcome': outcome,
        'started_observation_id': active.get('started_observation_id'),
        'ended_observation_id': observation_id,
        'start_resources': {k: start_player.get(k) for k in ('hp', 'max_hp', 'gold', 'potions')},
        'end_resources': {k: end_player.get(k) for k in ('hp', 'max_hp', 'gold', 'potions')},
        'net_hp_change': net_hp,
        'rounds_observed': sorted({x for x in active.get('rounds_seen', []) if isinstance(x, int)}),
        'action_count': active.get('action_count', 0),
        'action_counts': active.get('action_counts', {}),
        'cards_played': active.get('cards_played', {}),
        'potions_used': active.get('potions_used', []),
        'min_observed_hp': min(active['hp_samples']) if active.get('hp_samples') else None,
        'end_state': end_state,
        'data_quality': {
            'result_kind': 'observed_endpoint_delta',
            'exact_damage_breakdown': False,
            'draw_pile_order_known': False,
            'notes': 'Net changes may include damage, self-loss, healing and passive effects.'
        },
    }


def planner_battle_report(report):
    """Battle-to-planner handoff: outcome and resource endpoints, never tactical history."""
    keys = ('battle_id', 'location', 'character', 'enemies', 'outcome',
            'started_observation_id', 'ended_observation_id', 'start_resources',
            'end_resources', 'net_hp_change', 'rounds_observed', 'end_state', 'data_quality')
    return {key: copy.deepcopy(report[key]) for key in keys if key in report}


def observe(memory, state, combat, log, observation_id=None):
    """Update role memories and return the battle association/report for the durable journal."""
    active = memory.get('combat')
    if active is not None and (combat_finished(state) or (not combat and state.get('state_type') in POST_COMBAT)):
        report = _battle_report(active, state, observation_id)
        handoff = planner_battle_report(report)
        memory['planner']['battle_reports'] = _bounded(
            memory['planner']['battle_reports'] + [handoff],
            PLANNER_BATTLE_REPORT_LIMIT, PLANNER_HISTORY_TOKENS)
        log('battle_finished', battle_id=active['battle_id'], report=handoff,
            state=strategic_state(state))
        memory['combat'] = None
        return {'battle_id': active['battle_id'], 'report': report}
    if combat:
        snapshot = combat_snapshot(state, observation_id)
        restarted = (active is not None and snapshot.get('round') == 1
                     and any(isinstance(x, int) and x > 1 for x in active.get('rounds_seen', [])))
        is_new = active is None or active.get('location') != _location(state) or restarted
        if is_new:
            active = _new_battle(memory, state, observation_id)
            memory['combat'] = active
        elif not active['observations'] or active['observations'][-1] != snapshot:
            active['observations'] = _bounded(active['observations'] + [snapshot],
                                               COMBAT_HISTORY_LIMIT, COMBAT_HISTORY_TOKENS)
        if not is_new:
            battle = state.get('battle') or {}
            player = state.get('player') or {}
            if battle.get('round') is not None:
                active['rounds_seen'].append(battle['round'])
            if isinstance(player.get('hp'), (int, float)):
                active['hp_samples'].append(player['hp'])
        return {'battle_id': active['battle_id'], 'report': None}
    return {'battle_id': None, 'report': None}


def record_action(memory, state, combat, action, description, role, decision,
                  observation_id=None, decision_id=None, action_id=None):
    item = normalize_action({'observation_id': observation_id, 'decision_id': decision_id,
                             'action_id': action_id, 'run': state.get('run'),
                             'screen': state.get('state_type'), 'role': role, 'action': action,
                             'description': description, 'reason': (decision or {}).get('reason', '')})
    if combat and memory.get('combat') is not None:
        active = memory['combat']
        active['action_count'] += 1
        kind = action.get('action', 'unknown')
        active['action_counts'][kind] = active['action_counts'].get(kind, 0) + 1
        if kind == 'play_card':
            name = description.split(' -> ', 1)[0] if description else str(action.get('card_index'))
            active['cards_played'][name] = active['cards_played'].get(name, 0) + 1
        elif kind == 'use_potion':
            active['potions_used'].append({'description': description, 'slot': action.get('slot'),
                                           'target': action.get('target')})
        active['recent_actions'] = _bounded(active['recent_actions'] + [item],
                                             COMBAT_HISTORY_LIMIT, COMBAT_HISTORY_TOKENS)
    elif role == 'planner':
        memory['planner']['decisions'] = _bounded(memory['planner']['decisions'] + [item],
                                                  PLANNER_DECISION_LIMIT, PLANNER_HISTORY_TOKENS)


def trim_context(context, max_tokens, history_keys):
    context = copy.deepcopy(context)
    while estimated_tokens(context) > max_tokens:
        candidates = [(estimated_tokens(context.get(key)), key) for key in history_keys if context.get(key)]
        if not candidates:
            break
        _, key = max(candidates)
        context[key].pop(0)
    return context


def trim_combat_context(context, max_tokens=45056):
    context = copy.deepcopy(context)
    while estimated_tokens(context) > max_tokens:
        memory = context.get('battle_memory') or {}
        candidates = []
        for key in ('observations', 'recent_actions'):
            if memory.get(key):
                candidates.append((estimated_tokens(memory[key]), 'battle_memory', key))
        if context.get('past_combat_cases'):
            candidates.append((estimated_tokens(context['past_combat_cases']), 'past_combat_cases', None))
        if not candidates:
            break
        _, section, key = max(candidates)
        if section == 'battle_memory':
            memory[key].pop(0)
        else:
            context[section].pop(0)
    return context
