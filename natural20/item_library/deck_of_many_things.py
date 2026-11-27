"""Deck of Many Things (SRD, DMG) — card-draw wondrous item.

Item YAML (``item_class: DeckOfManyThingsItem``)::

    deck_of_many_things:
      item_class: DeckOfManyThingsItem
      usable: true
      activation: action
      cards: 13          # 13 or 22 (the full deck)

Drawing: declare a number of cards (1-3), then each card is drawn randomly.
Cards fade from the deck when drawn (the Fool and the Jester return to it,
so they can be drawn twice); the draw history is stored on the inventory
stack under ``deck_drawn``.

Mechanical card effects are applied through existing engine primitives
(XP awards, ability shifts, gold, item grants/loss, NPC summons, status
effects). Cards that need narrative adjudication (Flames, Rogue, The Fates,
The Void, Donjon, Comet, Vizier, Throne) set a ``deck_<card>`` property on
the drawer and log the SRD text for the DM.
"""
from __future__ import annotations

import random

from natural20.die_roll import DieRoll
from natural20.item_library.object import Object

# (key, label, full-deck-only)
CARDS = [
    ('vizier', 'Vizier', False),
    ('sun', 'Sun', False),
    ('moon', 'Moon', False),
    ('star', 'Star', False),
    ('comet', 'Comet', True),
    ('fates', 'The Fates', True),
    ('throne', 'Throne', False),
    ('key', 'Key', False),
    ('knight', 'Knight', False),
    ('gem', 'Gem', True),
    ('talons', 'Talons', True),
    ('void', 'The Void', False),
    ('flames', 'Flames', False),
    ('skull', 'Skull', False),
    ('idiot', 'Idiot', True),
    ('donjon', 'Donjon', True),
    ('ruin', 'Ruin', False),
    ('euryale', 'Euryale', False),
    ('rogue', 'Rogue', False),
    ('balance', 'Balance', True),
    ('fool', 'Fool', True),
    ('jester', 'Jester', False),
]

FULL_DECK_ONLY = {key for key, _label, full in CARDS if full}
LABELS = {key: label for key, label, _full in CARDS}


def _draw_pool(cards: int):
    if int(cards or 13) >= 22:
        return [key for key, _l, _f in CARDS]
    return [key for key, _l, full in CARDS if not full]


class DeckOfManyThingsItem(Object):

    def consumable(self):
        return False

    def can_use(self, entity, battle):
        return True

    # -- targeting ----------------------------------------------------------

    def build_map(self, action):
        def choose_draws(choice):
            action.deck_draws = max(1, min(3, int(choice or 1)))
            return action

        return {
            'param': [{'type': 'select_choice', 'num': 1,
                       'choices': [['Draw 1 card', 1], ['Draw 2 cards', 2],
                                   ['Draw 3 cards', 3]]}],
            'next': choose_draws,
        }

    def resolve(self, entity, battle, action, _battle_map):
        deck_size = int(self.properties.get('cards') or 13)
        drawn = []
        pool = _draw_pool(deck_size)
        stack = getattr(entity, 'inventory', {})
        entry = stack.get(self.properties.get('name')) if isinstance(stack, dict) else None
        history = list((entry or {}).get('deck_drawn') or [])
        for _ in range(int(getattr(action, 'deck_draws', 1) or 1)):
            available = [c for c in pool if c not in history or c in ('fool', 'jester')]
            if not available:
                break
            pick = random.choice(available)
            drawn.append(pick)
            if pick not in ('fool', 'jester'):
                history.append(pick)
        return {'deck_draws_result': drawn, 'deck_history': history}

    # -- effects ------------------------------------------------------------

    def use(self, entity, result, session=None):
        drawer = (result or {}).get('source') or entity
        session = getattr(drawer, 'session', None) or session
        battle = (result or {}).get('battle')
        drawn = list((result or {}).get('deck_draws_result') or [])
        history = list((result or {}).get('deck_history') or [])
        if drawn:
            stack = getattr(drawer, 'inventory', {})
            entry = stack.get(self.properties.get('name')) if isinstance(stack, dict) else None
            if isinstance(entry, dict):
                entry['deck_drawn'] = history
        for card in drawn:
            self._apply_card(card, drawer, battle, session)

    def _log(self, session, drawer, card, text):
        if session is not None:
            session.event_manager.received_event({
                'event': 'deck_of_many_things', 'source': drawer,
                'card': card, 'label': LABELS.get(card, card), 'text': text,
            })

    def _apply_card(self, card, drawer, battle, session):
        handler = getattr(self, f'_card_{card}', None)
        if handler is None:
            return
        handler(drawer, battle, session)

    # -- card handlers --------------------------------------------------------

    def _flag(self, drawer, card, text, session):
        props = getattr(drawer, 'properties', None)
        if isinstance(props, dict):
            props[f'deck_{card}'] = True
        self._log(session, drawer, card, text)

    def _xp(self, drawer, amount, session, card):
        try:
            from natural20.progression import award_xp_to_character
            award_xp_to_character(drawer, amount, source='deck_of_many_things')
        except Exception:
            pass
        self._log(session, drawer, card, f'Gain {amount} XP.')

    def _card_sun(self, drawer, battle, session):
        self._xp(drawer, 50000, session, 'sun')
        self._flag(drawer, 'sun', 'A wondrous item appears in your hands (DM chooses).', session)

    def _card_fool(self, drawer, battle, session):
        try:
            from natural20.progression import award_xp_to_character
            award_xp_to_character(drawer, -10000, source='deck_fool')
        except Exception:
            pass
        self._log(session, drawer, 'fool', 'You lose 10,000 XP; the Fool returns to the deck.')

    def _card_jester(self, drawer, battle, session):
        self._xp(drawer, 10000, session, 'jester')
        self._log(session, drawer, 'jester',
                  'Instead of the XP you may draw two additional cards (DM choice).')

    def _card_star(self, drawer, battle, session):
        scores = getattr(drawer, 'properties', {}).get('ability') if isinstance(
            getattr(drawer, 'properties', None), dict) else None
        if isinstance(scores, dict) and scores:
            ability = max(scores, key=lambda k: scores[k])
            scores[ability] = min(24, int(scores[ability]) + 2)
            self._log(session, drawer, 'star',
                      f'{ability.capitalize()} increases by 2 (now {scores[ability]}).')
        else:
            self._flag(drawer, 'star', 'Increase one ability score by 2 (max 24).', session)

    def _card_idiot(self, drawer, battle, session):
        roll = DieRoll.roll('1d4+1', battle=battle, entity=drawer,
                            description='dice_roll.deck_idiot')
        scores = getattr(drawer, 'properties', {}).get('ability') if isinstance(
            getattr(drawer, 'properties', None), dict) else None
        if isinstance(scores, dict) and 'int' in scores:
            scores['int'] = max(1, int(scores['int']) - int(roll.result()))
        self._log(session, drawer, 'idiot',
                  f'Intelligence permanently reduced by {roll.result()} '
                  '(you draw one additional card).')

    def _card_gem(self, drawer, battle, session):
        self._add_wealth(drawer, 50000)
        self._log(session, drawer, 'gem', 'Fifty gems worth 1,000 gp each appear at your feet.')

    def _card_ruin(self, drawer, battle, session):
        removed = self._clear_wealth(drawer)
        self._log(session, drawer, 'ruin',
                  f'All non-magical wealth is lost to you ({removed} gp removed).')

    def _card_key(self, drawer, battle, session):
        try:
            drawer.add_item('longsword_plus_one', 1)
            self._log(session, drawer, 'key',
                      'A rare magic weapon appears in your hands (granted: Longsword +1).')
        except Exception:
            self._flag(drawer, 'key', 'A rare magic weapon appears in your hands.', session)

    def _card_knight(self, drawer, battle, session):
        try:
            group = getattr(drawer, 'group', 'a')
            knight = session.npc('veteran', {'name': "Knight of the Deck", 'group': group})
            knight.group = group
            knight.properties['summoner_uid'] = getattr(drawer, 'entity_uid', None)
            session.register_entity(knight)
            battle_map = session.map_for_entity(drawer)
            if battle_map is not None:
                pos = battle_map.position_of(drawer)
                if pos:
                    battle_map.place((pos[0] + 1, pos[1]), knight, None, battle)
            self._log(session, drawer, 'knight',
                      'A 4th-level fighter appears and serves you loyally until death.')
        except Exception:
            self._flag(drawer, 'knight', 'A 4th-level fighter enters your service.', session)

    def _card_skull(self, drawer, battle, session):
        try:
            hp_fn = getattr(drawer, 'max_hp', None)
            drawer_max = int(hp_fn() if callable(hp_fn) else 20) or 20
            overrides = {'max_hp': max(1, drawer_max // 2)}
            avatar = session.npc('avatar_of_death',
                                 {'name': 'Avatar of Death', 'group': 'b',
                                  'overrides': overrides})
            avatar.group = 'b'
            session.register_entity(avatar)
            battle_map = session.map_for_entity(drawer)
            if battle_map is not None:
                pos = battle_map.position_of(drawer)
                if pos:
                    battle_map.place((pos[0] + 1, pos[1]), avatar, None, battle)
            self._log(session, drawer, 'skull',
                      'An avatar of death appears and attacks; you must fight it alone.')
        except Exception:
            self._flag(drawer, 'skull', 'An avatar of death rises against you.', session)

    def _card_euryale(self, drawer, battle, session):
        statuses = getattr(drawer, 'statuses', None)
        if isinstance(statuses, list) and 'cursed' not in statuses:
            statuses.append('cursed')
        self._flag(drawer, 'euryale',
                   'Cursed: -2 penalty on saving throws (only The Fates or a god can end it).',
                   session)

    def _card_balance(self, drawer, battle, session):
        align = str(getattr(drawer, 'alignment', '') or '')
        flip = {'lawful_good': 'chaotic_evil', 'chaotic_evil': 'lawful_good',
                'lawful_evil': 'chaotic_good', 'chaotic_good': 'lawful_evil',
                'neutral_good': 'neutral_evil', 'neutral_evil': 'neutral_good',
                'lawful_neutral': 'chaotic_neutral', 'chaotic_neutral': 'lawful_neutral'}
        if align in flip:
            drawer.alignment = flip[align]
            self._log(session, drawer, 'balance', f'Your alignment flips to {flip[align]}.')
        else:
            self._log(session, drawer, 'balance', 'The card has no effect on you.')

    def _card_talons(self, drawer, battle, session):
        removed = self._destroy_magic_items(drawer)
        self._log(session, drawer, 'talons',
                  f'Every magic item you wear or carry disintegrates ({removed} removed).')

    def _card_moon(self, drawer, battle, session):
        roll = DieRoll.roll('1d3', battle=battle, entity=drawer,
                            description='dice_roll.deck_moon')
        self._flag(drawer, 'moon',
                   f'You may cast wish {roll.result()} time(s) (wish is DM-ruled).', session)

    def _card_throne(self, drawer, battle, session):
        self._flag(drawer, 'throne',
                   'You gain Persuasion proficiency (doubled) and rightful ownership of a '
                   'monster-held keep.', session)

    def _card_vizier(self, drawer, battle, session):
        self._flag(drawer, 'vizier',
                   'Once within a year, a meditated question receives a truthful answer.',
                   session)

    def _card_comet(self, drawer, battle, session):
        self._flag(drawer, 'comet',
                   'If you single-handedly defeat the next hostile monster or group, you '
                   'gain enough XP for one level.', session)

    def _card_fates(self, drawer, battle, session):
        self._flag(drawer, 'fates',
                   'Reality can be rewound once: one event avoided as if it never happened.',
                   session)

    def _card_flames(self, drawer, battle, session):
        self._flag(drawer, 'flames',
                   'A powerful devil becomes your enemy and seeks your ruin.', session)

    def _card_rogue(self, drawer, battle, session):
        self._flag(drawer, 'rogue',
                   'An NPC of the DM\u2019s choice becomes secretly hostile toward you.',
                   session)

    def _card_void(self, drawer, battle, session):
        statuses = getattr(drawer, 'statuses', None)
        if isinstance(statuses, list):
            for cond in ('incapacitated', 'unconscious'):
                if cond not in statuses:
                    statuses.append(cond)
        self._flag(drawer, 'void',
                   'Your soul is trapped in a guarded object; your body is incapacitated.',
                   session)

    def _card_donjon(self, drawer, battle, session):
        self._flag(drawer, 'donjon',
                   'You vanish into an extraplanar sphere of suspended animation; only a wish '
                   'reveals your prison.', session)

    # -- wealth / inventory helpers -------------------------------------------

    def _add_wealth(self, drawer, gp):
        try:
            drawer.add_item('gold_piece', gp)
        except Exception:
            pass

    def _clear_wealth(self, drawer):
        removed = 0
        stack = getattr(drawer, 'inventory', {})
        if not isinstance(stack, dict):
            return removed
        for key in list(stack.keys()):
            try:
                meta = drawer.session.load_thing(key) or {}
            except Exception:
                meta = {}
            if str(meta.get('type', '')).lower() in ('coin', 'currency') or \
                    key in ('gold_piece', 'silver_piece', 'copper_piece', 'electrum_piece'):
                removed += int((stack.get(key) or {}).get('qty') or 0)
                try:
                    drawer.remove_item(key, (stack.get(key) or {}).get('qty') or 1)
                except Exception:
                    pass
        return removed

    def _destroy_magic_items(self, drawer):
        removed = 0
        stack = getattr(drawer, 'inventory', {})
        if not isinstance(stack, dict):
            return removed
        for key in list(stack.keys()):
            try:
                meta = drawer.session.load_thing(key) or {}
            except Exception:
                meta = {}
            if meta.get('magical') and not meta.get('artifact'):
                try:
                    drawer.remove_item(key, (stack.get(key) or {}).get('qty') or 1)
                    removed += 1
                except Exception:
                    pass
        props = getattr(drawer, 'properties', None)
        if isinstance(props, dict):
            props['equipped'] = [k for k in (props.get('equipped') or [])
                                 if k in stack]
        return removed
