"""Rules-bound combat communication and intelligence-scaled tactics."""
import pytest
from unittest.mock import MagicMock, patch

from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils import combat_comms, combat_intelligence, combat_strategy


@pytest.fixture
def setup():
    event_manager = EventManager()
    event_manager.standard_cli()
    session = Session(root_path='tests/fixtures', event_manager=event_manager)
    battle_map = Map(session, 'tests/fixtures/battle_sim.yml')
    session.maps['test'] = battle_map
    battle = Battle(session, battle_map)
    gruk = session.npc('goblin', {"name": "Gruk"})
    snix = session.npc('goblin', {"name": "Snix"})
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    battle.add(gruk, 'b', position=(2, 2), token='g')
    battle.add(snix, 'b', position=(3, 2), token='G')
    battle.add(fighter, 'a', position=(4, 3), token='F')
    # A second foe: with a lone enemy, focus-fire callouts are not offered.
    mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
    battle.add(mage, 'a', position=(5, 3), token='M')
    for e in (gruk, snix, fighter, mage):
        e.reset_turn(battle)
    battle.start()
    battle.set_current_turn(gruk)
    return battle, gruk, snix, fighter


def _set_int(entity, score):
    entity.ability_scores['int'] = score


def _secret_tongue(*entities):
    for e in entities:
        e.properties['languages'] = ['common', 'sylvan']


class TestSpeakingRules:
    def test_ally_hears_and_enemy_overhears(self, setup):
        battle, gruk, snix, fighter = setup
        res = combat_comms.issue_callout(battle, gruk, 'focus', target=fighter, language='common')
        assert res['ok']
        assert snix.name in res['heard_by']
        assert fighter.name in res['overheard_by_enemies']
        assert combat_comms.heard_callouts(battle, snix)[-1]['target_uid'] == fighter.entity_uid

    def test_once_per_turn(self, setup):
        battle, gruk, snix, fighter = setup
        assert combat_comms.issue_callout(battle, gruk, 'focus', target=fighter)['ok']
        again = combat_comms.issue_callout(battle, gruk, 'retreat')
        assert not again['ok'] and again['reason'] == 'already_spoke'

    def test_only_on_own_turn(self, setup):
        battle, gruk, snix, fighter = setup
        res = combat_comms.issue_callout(battle, snix, 'retreat')
        assert res['reason'] == 'not_your_turn'

    def test_unconscious_cannot_speak(self, setup):
        battle, gruk, snix, fighter = setup
        gruk.statuses.append('unconscious')
        res = combat_comms.issue_callout(battle, gruk, 'retreat')
        assert not res['ok'] and res['reason'] == 'unconscious'

    def test_silenced_cannot_speak(self, setup):
        battle, gruk, snix, fighter = setup
        gruk.statuses.append('silenced')
        assert combat_comms.issue_callout(battle, gruk, 'retreat')['reason'] == 'silenced'

    def test_deafened_or_unconscious_listener_hears_nothing(self, setup):
        battle, gruk, snix, fighter = setup
        snix.statuses.append('deafened')
        fighter.statuses.append('unconscious')
        combat_comms.issue_callout(battle, gruk, 'retreat')
        assert combat_comms.heard_callouts(battle, snix) == []
        assert combat_comms.heard_callouts(battle, fighter) == []

    def test_brief_utterance_word_cap(self, setup):
        battle, gruk, snix, fighter = setup
        res = combat_comms.issue_callout(battle, gruk, 'say', message=' '.join(['go'] * 50))
        assert len(res['text'].split()) == combat_comms.max_words_for(gruk)

    def test_cannot_call_out_unseen_target(self, setup):
        battle, gruk, snix, fighter = setup
        with patch.object(battle, 'can_see', return_value=False):
            res = combat_comms.issue_callout(battle, gruk, 'focus', target=fighter)
        assert res['reason'] == 'target_not_visible'

    def test_language_enemy_does_not_know_stays_secret(self, setup):
        battle, gruk, snix, fighter = setup
        _secret_tongue(gruk, snix)
        res = combat_comms.issue_callout(battle, gruk, 'focus', target=fighter, language='sylvan')
        assert res['ok'] and res['overheard_by_enemies'] == []
        entry = combat_comms.heard_callouts(battle, fighter)[-1]
        assert entry['understood'] is False and entry['text'] is None
        lines = combat_comms.callout_lines(battle, fighter)
        assert any('could not understand' in l for l in lines)

    def test_telepathy_is_silent_and_works_in_silence(self, setup):
        battle, gruk, snix, fighter = setup
        gruk.properties['telepathy'] = 60
        gruk.statuses.append('silenced')
        res = combat_comms.issue_callout(battle, gruk, 'focus', target=fighter)
        assert res['ok'] and res['language'] == 'telepathy'
        assert combat_comms.heard_callouts(battle, snix)[-1]['mode'] == 'telepathy'
        assert combat_comms.heard_callouts(battle, fighter) == []

    def test_human_speech_in_battle_is_recorded(self, setup):
        battle, gruk, snix, fighter = setup
        fighter.send_conversation("Get the goblin!", distance_ft=30, language='common')
        assert combat_comms.heard_callouts(battle, gruk)[-1]['text'] == "Get the goblin!"

    def test_disabled_via_game_properties(self, setup):
        battle, gruk, snix, fighter = setup
        battle.session.game_properties = {'combat_communication': {'enabled': False}}
        assert combat_comms.issue_callout(battle, gruk, 'retreat')['reason'] == 'disabled'

    def test_inbox_expires(self, setup):
        battle, gruk, snix, fighter = setup
        combat_comms.issue_callout(battle, gruk, 'retreat')
        battle.round += 2
        assert combat_comms.heard_callouts(battle, snix) == []


class TestAutoCallout:
    def test_announces_attack_target(self, setup):
        battle, gruk, snix, fighter = setup
        action = MagicMock(target=fighter)
        res = combat_comms.auto_callout(battle, gruk, action)
        assert res['ok'] and combat_comms.heard_callouts(battle, snix)[-1]['kind'] == 'focus'

    def test_calls_for_healing_when_low(self, setup):
        battle, gruk, snix, fighter = setup
        gruk.attributes['hp'] = 1
        snix.add_item('healing_potion')
        res = combat_comms.auto_callout(battle, gruk, MagicMock(target=fighter))
        assert res['ok'] and combat_comms.heard_callouts(battle, snix)[-1]['kind'] == 'heal'

    def test_no_healing_call_when_no_ally_can_heal(self, setup):
        battle, gruk, snix, fighter = setup
        gruk.attributes['hp'] = 1
        options = combat_strategy.strategy_options(battle, gruk, MagicMock(target=fighter))
        assert not any(o['kind'] == 'heal' for o in options)

    def test_ally_directed_callout_needs_a_listening_ally(self, setup):
        battle, gruk, snix, fighter = setup
        snix.attributes['hp'] = 0
        snix.make_dead()
        res = combat_comms.issue_callout(battle, gruk, 'heal')
        assert not res['ok'] and res['reason'] == 'no_listening_ally'
        assert combat_comms.issue_callout(battle, gruk, 'taunt', target=fighter)['ok']

    def test_skips_when_ally_already_called_same_focus(self, setup):
        battle, gruk, snix, fighter = setup
        combat_comms.issue_callout(battle, gruk, 'focus', target=fighter)
        battle.set_current_turn(snix)
        assert combat_comms.auto_callout(battle, snix, MagicMock(target=fighter)) is None


@pytest.fixture(autouse=True)
def _no_phraser():
    combat_comms.set_callout_phraser(None)
    yield
    combat_comms.set_callout_phraser(None)


class TestStrategicCallouts:
    def test_menu_starts_silent_and_offers_combat_options(self, setup):
        from natural20.utils.combat_strategy import strategy_options
        battle, gruk, snix, fighter = setup
        snix.attributes['hp'] = 1
        gruk.attributes['hp'] = 2
        snix.add_item('healing_potion')
        opts = strategy_options(battle, gruk, MagicMock(target=fighter))
        assert opts[0]['kind'] is None
        kinds = {(o['kind'], getattr(o['target'], 'name', None)) for o in opts[1:]}
        assert ('focus', fighter.name) in kinds
        assert ('heal', None) in kinds
        assert ('protect', snix.name) in kinds
        assert all(o['desc'] and o['intent'] for o in opts)

    def test_menu_respects_wits(self, setup):
        from natural20.utils.combat_strategy import strategy_options
        battle, gruk, snix, fighter = setup
        snix.attributes['hp'] = 1
        _set_int(gruk, 5)
        kinds = {o['kind'] for o in strategy_options(battle, gruk, MagicMock(target=fighter))}
        assert 'protect' not in kinds and 'warn' not in kinds

    def test_chooser_picks_the_direction(self, setup):
        battle, gruk, snix, fighter = setup
        snix.attributes['hp'] = 1
        picked = {}

        def chooser(options):
            picked['options'] = options
            return next(o for o in options if o['kind'] == 'protect')

        res = combat_comms.auto_callout(battle, gruk, MagicMock(target=fighter), chooser=chooser)
        assert res['ok']
        entry = combat_comms.heard_callouts(battle, snix)[-1]
        assert entry['kind'] == 'protect' and entry['target_uid'] == snix.entity_uid

    def test_chooser_can_stay_silent(self, setup):
        battle, gruk, snix, fighter = setup
        res = combat_comms.auto_callout(battle, gruk, MagicMock(target=fighter),
                                        chooser=lambda options: options[0])
        assert res is None
        assert combat_comms.heard_callouts(battle, snix) == []

    def test_failed_chooser_falls_back_to_default(self, setup):
        battle, gruk, snix, fighter = setup
        res = combat_comms.auto_callout(battle, gruk, MagicMock(target=fighter),
                                        chooser=lambda options: None)
        assert res['ok'] and combat_comms.heard_callouts(battle, snix)[-1]['kind'] == 'focus'

    def test_strategic_switch_off_ignores_chooser(self, setup):
        battle, gruk, snix, fighter = setup
        battle.session.game_properties['combat_communication'] = {'strategic_callouts': False}
        chooser = MagicMock()
        combat_comms.auto_callout(battle, gruk, MagicMock(target=fighter), chooser=chooser)
        chooser.assert_not_called()

    def test_jev_select_callout_uses_decision_model(self, setup):
        from natural20.utils.combat_strategy import strategy_options
        from natural20.utils.jev_decision import jev_select_callout
        battle, gruk, snix, fighter = setup
        provider = MagicMock(is_available=True)
        provider.decide_action.return_value = {'index': 1}
        opts = strategy_options(battle, gruk, MagicMock(target=fighter))
        choice = jev_select_callout(provider, battle, gruk, opts)
        assert choice is opts[1]
        state, descs = provider.decide_action.call_args.args
        assert 'call out to your allies' in state
        assert descs[0].startswith('stay silent')

    def test_jev_select_callout_out_of_range_is_none(self, setup):
        from natural20.utils.jev_decision import jev_select_callout
        battle, gruk, snix, fighter = setup
        provider = MagicMock(is_available=True)
        provider.decide_action.return_value = {'index': 9}
        assert jev_select_callout(provider, battle, gruk, [{'kind': None, 'desc': 'stay silent'}]) is None


class TestCalloutPhrasing:
    def test_phraser_voices_the_callout(self, setup):
        battle, gruk, snix, fighter = setup
        seen = {}

        def phraser(request):
            seen.update(request)
            return 'Gruk: "Stab the shiny elf, Snix!"'

        combat_comms.set_callout_phraser(phraser)
        res = combat_comms.issue_callout(battle, gruk, 'focus', target=fighter, intent='kill the elf')
        assert res['text'] == 'Stab the shiny elf, Snix!'
        assert seen['intent'] == 'kill the elf' and seen['target'] is fighter
        entry = combat_comms.heard_callouts(battle, snix)[-1]
        assert entry['kind'] == 'focus' and entry['target_uid'] == fighter.entity_uid

    def test_phrase_is_capped_to_brief_utterance(self, setup):
        battle, gruk, snix, fighter = setup
        combat_comms.set_callout_phraser(lambda r: ' '.join(['charge'] * 60))
        res = combat_comms.issue_callout(battle, gruk, 'focus', target=fighter)
        assert len(res['text'].split()) == combat_comms.max_words_for(gruk)

    @pytest.mark.parametrize('reply', [None, '', '[NO_RESPONSE]'])
    def test_bad_phrase_falls_back_to_template(self, setup, reply):
        battle, gruk, snix, fighter = setup
        combat_comms.set_callout_phraser(lambda r: reply)
        res = combat_comms.issue_callout(battle, gruk, 'focus', target=fighter)
        assert res['text'].startswith('Focus on')

    def test_phraser_error_falls_back(self, setup):
        battle, gruk, snix, fighter = setup

        def boom(request):
            raise RuntimeError('provider down')

        combat_comms.set_callout_phraser(boom)
        assert combat_comms.issue_callout(battle, gruk, 'retreat')['text'] == 'Fall back!'

    def test_explicit_message_is_not_rephrased(self, setup):
        battle, gruk, snix, fighter = setup
        phraser = MagicMock(return_value='something else')
        combat_comms.set_callout_phraser(phraser)
        res = combat_comms.issue_callout(battle, gruk, 'say', message='Hold the door')
        assert res['text'] == 'Hold the door'
        phraser.assert_not_called()

    def test_opt_outs(self, setup):
        battle, gruk, snix, fighter = setup
        phraser = MagicMock(return_value='Rargh!')
        combat_comms.set_callout_phraser(phraser)
        gruk.properties['callout_phrasing'] = False
        assert combat_comms.issue_callout(battle, gruk, 'retreat')['text'] == 'Fall back!'
        battle.set_current_turn(snix)
        battle.session.game_properties['combat_communication'] = {'llm_phrasing': False}
        assert combat_comms.issue_callout(battle, snix, 'retreat')['text'] == 'Fall back!'
        phraser.assert_not_called()


class TestIntelligenceTiers:
    @pytest.mark.parametrize('score,tier', [(2, 'instinct'), (5, 'simple'), (10, 'tactical'), (18, 'mastermind')])
    def test_tier_from_int(self, setup, score, tier):
        _, gruk, _, _ = setup
        _set_int(gruk, score)
        assert combat_intelligence.tactics_tier(gruk) == tier

    def test_yaml_override(self, setup):
        _, gruk, _, _ = setup
        gruk.properties['tactics'] = 'mastermind'
        assert combat_intelligence.tactics_tier(gruk) == 'mastermind'

    def test_instinct_cannot_coordinate(self, setup):
        battle, gruk, snix, fighter = setup
        _set_int(gruk, 3)
        assert not combat_comms.can_call_out(battle, gruk)
        assert combat_comms.issue_callout(battle, gruk, 'focus', target=fighter)['reason'] == 'too_simple'

    def test_simple_limits_kinds_and_words(self, setup):
        battle, gruk, snix, fighter = setup
        _set_int(gruk, 5)
        assert combat_comms.issue_callout(battle, gruk, 'protect', target=snix)['reason'] == 'too_simple'
        res = combat_comms.issue_callout(battle, gruk, 'say', message=' '.join(['go'] * 20))
        assert len(res['text'].split()) == combat_intelligence.SIMPLE_MAX_WORDS

    def test_instinct_listener_ignores_callouts(self, setup):
        battle, gruk, snix, fighter = setup
        combat_comms.issue_callout(battle, gruk, 'focus', target=fighter)
        _set_int(snix, 2)
        assert combat_comms.callout_lines(battle, snix) == []
        assert combat_comms.ally_focus_target(battle, snix) is None

    def test_simple_listener_ignores_overheard_enemy(self, setup):
        battle, gruk, snix, fighter = setup
        combat_comms.issue_callout(battle, gruk, 'focus', target=fighter, language='common')
        _set_int(fighter, 6)
        assert combat_comms.callout_lines(battle, fighter) == []
        _set_int(fighter, 12)
        assert combat_comms.callout_lines(battle, fighter)

    def test_mastermind_prefers_language_enemies_lack(self, setup):
        battle, gruk, snix, fighter = setup
        _secret_tongue(gruk, snix)
        _set_int(gruk, 18)
        assert combat_comms._choose_language(battle, gruk, None) == 'sylvan'
        _set_int(gruk, 10)
        assert combat_comms._choose_language(battle, gruk, None) == 'common'

    def test_instinct_filters_far_targets(self, setup):
        battle, gruk, snix, fighter = setup
        _set_int(gruk, 2)
        near = MagicMock(target=fighter)
        far_enemy = MagicMock(entity_uid='far')
        far = MagicMock(target=far_enemy)
        keep = MagicMock(target=None)
        with patch.object(battle, 'opposing', side_effect=lambda a, b: b in (fighter, far_enemy)), \
                patch.object(combat_intelligence, 'instinct_targets', return_value=[fighter]):
            out = combat_intelligence.filter_actions(battle, gruk, [far, near, keep])
        assert out == [near, keep]

    def test_tactical_does_not_filter(self, setup):
        battle, gruk, snix, fighter = setup
        actions = [MagicMock(target=fighter)]
        assert combat_intelligence.filter_actions(battle, gruk, actions) == actions

    def test_guidance_in_llm_instructions(self, setup):
        from natural20.llm_controller import LlmMcpController
        battle, gruk, snix, fighter = setup
        _set_int(gruk, 2)
        ctrl = LlmMcpController(battle.session, llm_client=None, use_tools=False, llm_provider=None)
        with patch.object(ctrl, '_faction_is_neutral', return_value=False):
            assert 'instinct' in ctrl._combat_instructions_for(gruk, 'b')


class TestLlmCalloutParsing:
    def test_extract_callout_line(self, setup):
        from natural20.llm_controller import LlmMcpController
        battle, *_ = setup
        ctrl = LlmMcpController(battle.session, llm_client=None, use_tools=False, llm_provider=None)
        text, callout = ctrl._extract_callout("2\nCALLOUT focus Gomerin: Get him!")
        assert ctrl._local_parse_choice_from_text(text, 5) == 2
        assert callout == {'kind': 'focus', 'target': 'Gomerin', 'message': 'Get him!'}

    def test_provider_reply_issues_callout(self, setup):
        from natural20.llm_controller import LlmMcpController
        battle, gruk, snix, fighter = setup
        provider = MagicMock()
        provider.send_message.return_value = f"0\nCALLOUT focus {fighter.name}: Stab the elf!"
        ctrl = LlmMcpController(battle.session, llm_client=None, use_tools=False, llm_provider=provider)
        a0, a1 = MagicMock(target=fighter, disabled=False), MagicMock(target=None, disabled=False)
        with patch.object(ctrl, '_build_prompt', return_value='prompt CALLOUT <focus>'), \
                patch.object(ctrl, '_maybe_enrich_action_targets', side_effect=lambda b, e, a: a), \
                patch('natural20.llm_controller.is_unbuilt_spell', return_value=False):
            chosen = ctrl.select_action(battle, gruk, [a0, a1])
        assert chosen is a0
        assert combat_comms.heard_callouts(battle, snix)[-1]['text'] == 'Stab the elf!'
