from natural20.spell.spell import Spell
from natural20.spell.extensions.save_check import SaveCheck
from natural20.utils import polymorph


class PolymorphSpell(Spell):
    """Polymorph (SRD 2014, 4th-level transmutation, concentration, 1 hour).

    An unwilling target makes a Wisdom save; on a failure (or if willing) it
    becomes a beast whose CR is at most its own CR or level. Shapechangers
    and creatures at 0 HP are unaffected. The form ends when concentration
    ends or the beast drops to 0 HP (excess damage carries over).

    YAML: ``beast_form`` (willing / ally target) and ``hostile_beast_form``
    (unwilling target, usually something harmless).
    """

    DEFAULT_ALLY_FORM = 'wolf'
    DEFAULT_HOSTILE_FORM = 'cat'

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_target',
                'num': 1,
                'range': self.properties.get('range', 60),
                'target_types': ['enemies', 'allies'],
                'exclude_statuses': [polymorph.STATUS, 'unconscious', 'dead'],
                'exclude_races': ['shapechanger'],
            }],
            'next': set_target,
        }

    @staticmethod
    def _single_target(target):
        if isinstance(target, (list, tuple)):
            return target[0] if target else None
        return target

    def _spell_dc(self, entity, spell_action=None):
        from natural20.spell.hold_person_spell import HoldPersonSpell
        return entity.spell_save_dc(HoldPersonSpell._caster_spell_ability(entity, spell_action))

    def beast_for(self, target, unwilling):
        """Beast id for ``target``, capped at the target's CR / level."""
        hostile = self.properties.get('hostile_beast_form', self.DEFAULT_HOSTILE_FORM)
        wanted = hostile if unwilling else self.properties.get('beast_form', self.DEFAULT_ALLY_FORM)
        try:
            props = polymorph.load_beast(self.session, wanted)
        except FileNotFoundError:
            return hostile
        if polymorph.beast_cr(props) > polymorph.creature_level(target):
            return hostile
        return wanted

    def compute_hit_probability(self, battle, opts=None):
        target = self._single_target(self.action.target if self.action else None)
        if target is None or polymorph.unaffected_reason(target):
            return 0.0
        if battle is None or not battle.opposing(self.source, target):
            return 1.0
        save = target.save_throw('wisdom', battle, {'is_magical': True})
        return 1.0 - save.prob(self._spell_dc(self.source, self.action))

    def resolve(self, entity, battle, spell_action, _battle_map):
        target = self._single_target(spell_action.target)

        reason = polymorph.unaffected_reason(target)
        if reason:
            return [{
                'type': 'polymorph_unaffected',
                'source': entity,
                'target': target,
                'reason': reason,
                'spell': self.properties,
            }]

        unwilling = battle is not None and battle.opposing(entity, target)
        save = None
        dc = None
        if unwilling:
            dc = self._spell_dc(entity, spell_action)
            save = SaveCheck.make(target, 'wisdom', dc, battle=battle, opts={'is_magical': True})
            if save.passed:
                return [{
                    'type': 'spell_miss',
                    'source': entity,
                    'target': target,
                    'attack_name': 'polymorph',
                    'spell_save': save.roll,
                    'dc': dc,
                }]

        return [{
            'source': entity,
            'target': target,
            'type': 'polymorph',
            'spell': self.properties,
            'effect': self,
            'beast': self.beast_for(target, unwilling),
            'spell_save': save.roll if save is not None else None,
            'dc': dc,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') == 'polymorph_unaffected':
            if session is None:
                session = battle.session if battle else item['source'].session
            session.event_manager.received_event({
                'event': 'polymorph_unaffected',
                'source': item['source'],
                'target': item['target'],
                'reason': item.get('reason'),
            })
            return None
        if item.get('type') != 'polymorph':
            return None
        if session is None:
            session = battle.session if battle else item['source'].session
        target = item['target']
        source = item['source']
        effect = item['effect']
        duration_seconds = int(effect.properties.get('duration_seconds', 3600))

        if item.get('spell_save') is not None:
            session.event_manager.received_event({
                'event': 'save_fail',
                'source': target,
                'save_type': 'wisdom',
                'dc': item['dc'],
                'roll': item['spell_save'],
            })

        source.add_casted_effect({
            'target': target,
            'effect': effect,
            'expiration': session.game_time + duration_seconds,
        })
        if source.current_concentration() != effect:
            if battle is not None and hasattr(battle, 'start_concentration'):
                battle.start_concentration(source, effect)
            else:
                source.concentration_on(effect)

        session.event_manager.received_event({
            'event': 'spell_buf',
            'spell': effect.properties.get('label', 'Polymorph'),
            'source': source,
            'target': target,
        })
        polymorph.transform(target, item.get('beast') or PolymorphSpell.DEFAULT_HOSTILE_FORM,
                            caster=source, effect=effect, battle=battle)
        return None

    def dismiss(self, entity, descriptor=None, _opts=None):
        target = (descriptor or {}).get('target') or entity
        polymorph.revert(target, reason='spell_ended', end_spell=False)
