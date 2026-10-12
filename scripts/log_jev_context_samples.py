"""Log sample JEV contexts (state + options) for review.

Drives real Battle scenarios on the battle_sim fixture map and records the
exact (state, options) pairs that JevActionPlanner hands to the provider's
decide_action, plus a few state-only renders. Writes a plain-text review
file. Run from the repo root:

    python scripts/log_jev_context_samples.py [output_path]
"""
import random
import sys

from natural20.event_manager import EventManager
from natural20.session import Session
from natural20.map import Map
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.utils.jev_decision import JevActionPlanner, jev_select_action

OUT = sys.argv[1] if len(sys.argv) > 1 else 'jev_state_samples.txt'


class RecordingJev:
    """FakeJev that records every (state, options) pair it is asked."""

    is_available = True

    def __init__(self, script):
        self.script = list(script)
        self.states = []
        self.options = []

    def decide_action(self, state, options):
        self.states.append(state)
        self.options.append(list(options))
        if not self.script:
            return None
        item = self.script.pop(0)
        if isinstance(item, int):
            idx = item % len(options)
            return {'index': idx, 'choice': options[idx]}
        for i, o in enumerate(options):
            if item in o:
                return {'index': i, 'choice': o}
        return {'index': len(options) - 1, 'choice': options[-1]}

    def decide_bool(self, *a, **k):
        return {'noul': 0.9, 'confidence': 0.9}


def new_session():
    return Session(root_path='tests/fixtures', event_manager=EventManager())


def two_entity_battle(session):
    m = Map(session, 'battle_sim')
    battle = Battle(session, m)
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    goblin = session.npc('goblin')
    battle.add(fighter, 'a', position=[2, 5], token='G')
    battle.add(goblin, 'b', position=[1, 5], token='g')
    battle.start()
    battle.set_current_turn(goblin)
    goblin.reset_turn(battle)
    fighter.reset_turn(battle)
    return battle, m, fighter, goblin


def wizard_battle(session):
    m = Map(session, 'battle_sim')
    session.register_map('test_map', m)
    battle = Battle(session, m)
    wizard = session.npc('test_wizard', {'name': 'Noke'})
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    m.add(wizard, 1, 1)
    m.add(fighter, 1, 2)
    battle.add(wizard, 'b', add_to_initiative=True)
    battle.add(fighter, 'a', add_to_initiative=True)
    battle.start(combat_order=[wizard, fighter])
    wizard.reset_turn(battle)
    fighter.reset_turn(battle)
    battle.set_current_turn(wizard)
    return battle, m, fighter, wizard


def mage_battle(session):
    m = Map(session, 'battle_sim')
    battle = Battle(session, m)
    mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
    goblin = session.npc('goblin')
    battle.add(mage, 'a', position=[2, 5], token='W')
    battle.add(goblin, 'b', position=[1, 5], token='g')
    battle.start()
    battle.set_current_turn(goblin)
    goblin.reset_turn(battle)
    mage.reset_turn(battle)
    return battle, m, mage, goblin


L = []


def section(title, note=None):
    L.append('')
    L.append('=' * 78)
    L.append(title)
    if note:
        L.append(note)
    L.append('=' * 78)


def log_context(label, battle, entity, script, chosen=None):
    rec = RecordingJev(script)
    action = jev_select_action(rec, battle, entity)
    L.append('')
    L.append(f'--- {label}')
    if rec.states:
        L.append('STATE (sent to decide_action):')
        L.append(rec.states[-1])
        L.append('')
        L.append(f'OPTIONS ({len(rec.options[-1])} sent):')
        for i, o in enumerate(rec.options[-1]):
            mark = ' >' if (chosen is not None and o == chosen) else '  '
            L.append(f'{mark} [{i}] {o}')
    else:
        # single legal leaf: auto-selected, provider never consulted
        L.append('(provider not consulted - single legal leaf auto-selected)')
        L.append(f'auto-selected action: {type(action).__name__ if action else None}')
    if chosen is None and rec.options:
        # derive the chosen option from the script result
        pass


def state_only(label, battle, entity, note=None):
    planner = JevActionPlanner(None)
    planner._names = planner._display_names(battle, entity)
    st = planner._render_state(battle, entity)
    L.append('')
    L.append(f'--- {label}')
    if note:
        L.append(note)
    L.append(st)


def main():
    random.seed(42)

    # ------------------------------------------------------------------ #
    section('SAMPLE 1: battle start - goblin, first turn, empty log',
            'No entries have happened yet, so there is NO "since last turn:" block.')
    s = new_session()
    battle, m, fighter, goblin = two_entity_battle(s)
    log_context("goblin's first turn", battle, goblin, ['attack '])

    # ------------------------------------------------------------------ #
    section('SAMPLE 2: one round later - fighter, second turn',
            'Round 1: goblin attacked, fighter dodged. Round 2: goblin attacked again. '
            'The fighter now sees its own dodge and the newest attack; the round-1 '
            'attack is outside the window.')
    s = new_session()
    battle, m, fighter, goblin = two_entity_battle(s)
    battle.start_turn()
    a1 = jev_select_action(RecordingJev(['attack ']), battle, goblin)
    battle.action(a1); battle.commit(a1); battle.end_turn()
    battle.set_current_turn(fighter)
    battle.start_turn()
    d1 = jev_select_action(RecordingJev(['dodge']), battle, fighter)
    battle.action(d1); battle.commit(d1); battle.end_turn()
    battle.set_current_turn(goblin)
    goblin.reset_turn(battle)
    battle.start_turn()
    a2 = jev_select_action(RecordingJev(['attack ']), battle, goblin)
    battle.action(a2); battle.commit(a2); battle.end_turn()
    battle.set_current_turn(fighter)
    fighter.reset_turn(battle)
    battle.start_turn()
    log_context("fighter's second turn (witnessed: own dodge + new attack)",
                battle, fighter, ['attack '])

    # ------------------------------------------------------------------ #
    section('SAMPLE 3: spellcaster state - Test Wizard (Noke) with slots',
            'Wizard on his turn: full state with mods/slots, then the POV line '
            'appears for the fighter after Noke casts Haste on himself.')
    s = new_session()
    battle, m, fighter, wizard = wizard_battle(s)
    state_only("wizard's first turn (no POV yet - empty log)", battle, wizard)
    battle.start_turn()
    h = jev_select_action(RecordingJev(['Haste']), battle, wizard)
    battle.action(h); battle.commit(h); battle.end_turn()
    battle.set_current_turn(fighter)
    fighter.reset_turn(battle)
    battle.start_turn()
    log_context("fighter after witnessing the Haste cast", battle, fighter, ['attack '])
    state_only("wizard's second turn (POV includes his own Haste cast)", battle, wizard)

    # ------------------------------------------------------------------ #
    section('SAMPLE 4: downed & poisoned wizard (rich state + conditions)',
            'The goblin\'s opening attack drops Crysania (6 HP) to 0. The state now '
            'shows the standing conditions (unconscious, poisoned) that '
            '``entity.statuses`` tracks, plus the witnessed blow and her slots/scroll. '
            'Rendered state-only because a downed entity has no actions to choose.')
    s = new_session()
    battle, m, mage, goblin = mage_battle(s)
    battle.start_turn()
    a1 = jev_select_action(RecordingJev(['attack ']), battle, goblin)
    battle.action(a1); battle.commit(a1); battle.end_turn()
    battle.set_current_turn(mage)
    mage.reset_turn(battle)
    battle.start_turn()
    if 'poisoned' not in mage.statuses:
        mage.statuses.append('poisoned')
    state_only("Crysania's state (0 HP, poisoned, witnessed the blow)", battle, mage)

    # ------------------------------------------------------------------ #
    section('SAMPLE 5: window semantics - what "since last turn" includes',
            'The window opens at the START of the entity\'s previous turn, so on the '
            'fighter\'s 3rd turn it holds: the fighter\'s own 2nd-turn move, then the '
            'goblin\'s 3rd-turn attack. The 1st-turn dodge and 2nd-turn attack are '
            'already outside the window. Lines are oldest-first, newest-last.')
    s = new_session()
    battle, m, fighter, goblin = two_entity_battle(s)
    wizard_b = None
    # goblin attacks, then (simulating an ally wizard on the fighter's side) cast
    battle.start_turn()
    a1 = jev_select_action(RecordingJev(['attack ']), battle, goblin)
    battle.action(a1); battle.commit(a1); battle.end_turn()
    battle.set_current_turn(fighter)
    battle.start_turn()
    d1 = jev_select_action(RecordingJev(['dodge']), battle, fighter)
    battle.action(d1); battle.commit(d1); battle.end_turn()
    battle.set_current_turn(goblin)
    goblin.reset_turn(battle)
    battle.start_turn()
    a2 = jev_select_action(RecordingJev(['attack ']), battle, goblin)
    battle.action(a2); battle.commit(a2); battle.end_turn()
    battle.set_current_turn(fighter)
    fighter.reset_turn(battle)
    battle.start_turn()
    # give the fighter a move this time so a "moved" entry lands in the NEXT window
    mv = jev_select_action(RecordingJev(['move: engage']), battle, fighter)
    battle.action(mv); battle.commit(mv); battle.end_turn()
    battle.set_current_turn(goblin)
    goblin.reset_turn(battle)
    battle.start_turn()
    a3 = jev_select_action(RecordingJev(['attack ']), battle, goblin)
    battle.action(a3); battle.commit(a3); battle.end_turn()
    battle.set_current_turn(fighter)
    fighter.reset_turn(battle)
    battle.start_turn()
    log_context("fighter's third turn (window: own 2nd-turn move + new attack)",
                battle, fighter, ['attack '])

    # ------------------------------------------------------------------ #
    section('SAMPLE 6: POV cap - more witnessed entries than MAX_JEV_POV_LOG',
            'The log is padded past the cap; only the 10 most recent witnessed '
            'lines are rendered (oldest of the kept ten first).')
    from natural20.utils.jev_decision import MAX_JEV_POV_LOG
    s = new_session()
    battle, m, fighter, goblin = two_entity_battle(s)
    battle.start_turn()
    a1 = jev_select_action(RecordingJev(['attack ']), battle, goblin)
    battle.action(a1); battle.commit(a1)
    for _ in range(20):
        battle.battle_log.append(a1)
    planner = JevActionPlanner(None)
    planner._names = planner._display_names(battle, fighter)
    out_lines = planner._pov_log(battle, fighter)
    L.append('')
    L.append(f'--- _pov_log() output (cap = {MAX_JEV_POV_LOG}):')
    L.append(f'({len(out_lines)} lines rendered)')
    L.extend(out_lines)

    # ------------------------------------------------------------------ #
    section('SAMPLE 7: unconscious enemy + name-collision disambiguation',
            'Existing state lines shown for completeness of the context review: a '
            'downed-but-stable enemy is flagged (unconscious); a renamed fighter '
            'colliding with the goblin name gets an @[x, y] suffix.')
    s = new_session()
    battle, m, fighter, goblin = two_entity_battle(s)
    fighter.set_hp(0)
    fighter.update_state('unconscious')
    state_only('goblin vs a downed (0 HP, unconscious) fighter', battle, goblin)
    fighter2 = PlayerCharacter.load(s, 'high_elf_fighter.yml')
    m2 = Map(s, 'battle_sim')
    b2 = Battle(s, m2)
    f2 = PlayerCharacter.load(s, 'high_elf_fighter.yml')
    g2 = s.npc('goblin')
    b2.add(f2, 'a', position=[2, 5], token='G')
    b2.add(g2, 'b', position=[1, 5], token='g')
    b2.start()
    b2.set_current_turn(g2)
    g2.reset_turn(b2)
    f2.reset_turn(b2)
    f2.name = g2.name  # force a collision
    state_only('name collision (fighter renamed to the goblin\'s name)', b2, g2)

    with open(OUT, 'w') as f:
        f.write('\n'.join(L) + '\n')
    print(f'wrote {OUT} ({len(L)} lines)')


if __name__ == '__main__':
    main()
