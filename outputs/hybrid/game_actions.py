import json
character_selected = False

def candidates(s):
    global character_selected
    t = s['state_type']; p = s.get('player', {}); d = s.get(t, {}); a = []
    def add(action, desc='', **kw): a.append((dict(action=action, **kw), desc))
    if t == 'menu':
        opts = [x if isinstance(x,str) else x['name'] for x in s.get('options',[]) if isinstance(x,str) or x.get('enabled',True)]
        if s.get('menu_screen')=='character_select':
            if not character_selected and 'IRONCLAD' in opts:
                character_selected=True;add('menu_select',option='IRONCLAD');return a
            if 'confirm' in opts: add('menu_select',option='confirm');return a
        for pref in ('continue','singleplayer','standard','IRONCLAD','ironclad','confirm','embark','no'):
            if pref in opts: add('menu_select', option=pref); return a
        raise RuntimeError('Unsupported menu: '+json.dumps(s))
    if t in ('monster','elite','boss'):
        b=s.get('battle',{})
        if b.get('turn') != 'player' or not b.get('is_play_phase'): return []
        enemies=[e for e in b.get('enemies',[]) if e.get('hp',0)>0]
        for c in p.get('hand',[]):
            if not c.get('can_play'): continue
            if c.get('target_type') == 'AnyEnemy':
                for e in enemies: add('play_card', c['name']+' -> '+e['name'], card_index=c['index'], target=e['entity_id'])
            else: add('play_card',c['name'],card_index=c['index'])
        for c in p.get('potions',[]):
            if not c.get('can_use_in_combat'): continue
            if c.get('target_type') == 'AnyEnemy':
                for e in enemies: add('use_potion',c['name']+' -> '+e['name'],slot=c['slot'],target=e['entity_id'])
            else: add('use_potion',c['name'],slot=c['slot'])
        add('end_turn','End turn and let enemies act')
    elif t=='map':
        for x in d.get('next_options',[]): add('choose_map_node',json.dumps(x),index=x['index'])
    elif t=='event':
        if d.get('in_dialogue'): add('advance_dialogue')
        else:
            for x in d.get('options',[]):
                if not x.get('is_locked'): add('choose_event_option',json.dumps(x),index=x['index'])
    elif t=='rewards':
        for x in d.get('items',[]):
            if x.get('type')=='potion' and len(p.get('potions',[]))>=p.get('max_potion_slots',3): continue
            add('claim_reward',json.dumps(x),index=x['index'])
        if not a and d.get('can_proceed'): add('proceed')
    elif t=='card_reward':
        for x in d.get('cards',[]): add('select_card_reward',json.dumps(x),card_index=x['index'])
        if d.get('can_skip'): add('skip_card_reward','Skip adding a card; keep deck consistent')
    elif t in ('card_select','hand_select'):
        hand=t=='hand_select'
        if d.get('can_confirm') or d.get('preview_showing'): add('combat_confirm_selection' if hand else 'confirm_selection')
        else:
            selected={x['index'] for x in d.get('selected_cards',[])}
            for x in d.get('cards',[]):
                if x['index'] not in selected: add('combat_select_card' if hand else 'select_card',json.dumps(x),**{('card_index' if hand else 'index'):x['index']})
    elif t=='rest_site':
        for x in d.get('options',[]):
            if x.get('is_enabled'): add('choose_rest_option',json.dumps(x),index=x['index'])
        if not a and d.get('can_proceed'): add('proceed')
    elif t in ('shop','fake_merchant'):
        shop=d if t=='shop' else d.get('shop',{})
        for x in shop.get('items',[]):
            if x.get('is_stocked') and x.get('can_afford'): add('shop_purchase',json.dumps(x),index=x['index'])
        # STS2MCP's proceed action closes the inventory before clicking the room button.
        # can_proceed describes the obscured room button and is normally false while shopping.
        add('proceed','Leave shop and save remaining gold')
    elif t=='treasure':
        for x in d.get('relics',[]): add('claim_treasure_relic',json.dumps(x),index=x['index'])
        if not a and d.get('can_proceed'): add('proceed')
    elif t=='relic_select':
        for x in d.get('relics',[]): add('select_relic',json.dumps(x),index=x['index'])
    elif t=='bundle_select':
        if d.get('can_confirm'): add('confirm_bundle_selection')
        else:
            for x in d.get('bundles',[]): add('select_bundle',json.dumps(x),index=x['index'])
    elif t=='crystal_sphere':
        if d.get('can_proceed'): add('crystal_sphere_proceed')
        for x in d.get('clickable_cells',[]): add('crystal_sphere_click_cell',json.dumps(x),x=x['x'],y=x['y'])
    return a
