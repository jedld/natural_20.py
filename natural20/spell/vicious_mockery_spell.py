from natural20.spell.spell import Spell
from natural20.die_roll import DieRoll


class ViciousMockerySpell(Spell):
    """Vicious Mockery (enchantment cantrip).

    The target makes a Wisdom save; on failure it takes 1d4 psychic damage
    and has disadvantage on the next attack roll it makes before the end
    of its next turn. Damage scales at character levels 5/11/17.
    """

    def __init__(self, session, source, spell_name, details):
        super().__init__(session, source, spell_name, details)
        # Stable per-instance id so dismiss_effect can find the right effect.
        self._instance_id = f"vicious_mockery:{id(self)}"

    @property
    def id(self):
        return self._instance_id

    def to_dict(self):
        return {
            'name': self.name,
            'action': self.action,
            'session': self.session,
            'properties': self.properties,
            'source': self.source.entity_uid,
        }

    @staticmethod
    def from_dict(data):
        spell = ViciousMockerySpell(data['session'], data['source'], data['name'], data['properties'])
        spell.action = data['action']
        return spell

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [
                {
                    'type': 'select_target',
                    'num': 1,
                    'range': self.properties['range'],
                    'target_types': ['enemies'],
                }
            ],
            'next': set_target,
        }

    def _dice_count(self):
        level = self.source.level()
        n = 1
        if level >= 5:
            n += 1
        if level >= 11:
            n += 1
        if level >= 17:
            n += 1
        return n

    def _damage(self, battle, crit=False):
        n = self._dice_count()
        return DieRoll.roll(
            f"{n}d4",
            crit=crit,
            battle=battle,
            entity=self.source,
            description='dice_roll.spells.vicious_mockery',
        )

    def avg_damage(self, battle, opts=None):
        return self._damage(battle).expected()

    def compute_hit_probability(self, battle, opts=None):
        target = self.action.target if self.action else None
        if isinstance(target, list):
            target = target[0] if target else None
        if target is None:
            return 0.0
        result = target.save_throw('wisdom', battle, {'is_magical': True})
        return 1.0 - result.prob(self.source.spell_save_dc('charisma'))

    def resolve(self, entity, battle, spell_action, _battle_map):
        target = spell_action.target
        if isinstance(target, list):
            target = target[0]
        spell_dc = entity.spell_save_dc('charisma')
        save = target.save_throw('wisdom', battle, {'is_magical': True})
        if save < spell_dc:
            damage_roll = self._damage(battle)
            return [{
                'source': entity,
                'target': target,
                'attack_name': 'vicious_mockery',
                'damage_type': self.properties['damage_type'],
                'attack_roll': None,
                'damage_roll': damage_roll,
                'advantage_mod': None,
                'adv_info': None,
                'damage': damage_roll,
                'spell_save': save,
                'dc': spell_dc,
                'cover_ac': None,
                'type': 'vicious_mockery',
                'spell': self.properties,
                'effect': self,
            }]
        return [{
            'type': 'spell_miss',
            'source': entity,
            'target': target,
            'attack_name': 'vicious_mockery',
            'attack_roll': None,
            'advantage_mod': None,
            'adv_info': None,
            'spell_save': save,
            'dc': spell_dc,
            'cover_ac': None,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item['type'] != 'vicious_mockery':
            return
        if battle and session is None:
            session = battle.session

        # Apply damage via standard damage_event so HP/log are updated.
        from natural20.utils.attack_util import damage_event
        damage_event(item, battle)

        target = item['target']
        effect = item['effect']
        # Imposes disadvantage on the target's next attack roll.
        target.register_effect(
            'attack_advantage_modifier', ViciousMockerySpell,
            effect=effect, source=item['source'], duration=10,
        )
        target.register_event_hook(
            'attack_resolved', ViciousMockerySpell,
            effect=effect, source=item['source'], duration=10,
        )
        # End by end of target's next turn as a fallback.
        target.register_event_hook(
            'end_of_turn', ViciousMockerySpell,
            effect=effect, source=item['source'], duration=10,
        )

        if session is not None:
            session.event_manager.received_event({
                'event': 'spell_buf',
                'spell': effect,
                'source': item['source'],
                'target': target,
            })

    # --- effect callbacks ---
    @staticmethod
    def attack_advantage_modifier(entity, opt=None):
        return [[], ['vicious_mockery']]

    @staticmethod
    def attack_resolved(entity, opt=None):
        # The disadvantage applies to the NEXT attack the target makes.
        # After it resolves an attack, dismiss this effect on themselves.
        effect = (opt or {}).get('effect')
        if effect is None:
            return []
        try:
            entity.dismiss_effect(effect)
        except Exception:
            pass
        return []

    @staticmethod
    def end_of_turn(entity, opt=None):
        # Safety net: at end of target's next turn, drop the effect if still
        # active (e.g. they made no attack).
        effect = (opt or {}).get('effect')
        if effect is None:
            return []
        if not getattr(effect, '_target_started_turn', False):
            effect._target_started_turn = True
            return []
        try:
            entity.dismiss_effect(effect)
        except Exception:
            pass
        return []
