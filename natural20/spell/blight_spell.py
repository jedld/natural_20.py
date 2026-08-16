from natural20.die_roll import DieRoll
from natural20.spell.extensions.save_check import SaveCheck
from natural20.spell.hold_person_spell import HoldPersonSpell
from natural20.spell.spell import Spell


def _is_plant(entity):
    race = getattr(entity, 'properties', {}).get('race') or []
    if isinstance(race, str):
        race = [race]
    if 'plant' in [str(r).lower() for r in race]:
        return True
    if callable(getattr(entity, 'plant', None)):
        try:
            return bool(entity.plant())
        except Exception:
            return False
    return False


class BlightSpell(Spell):
    """Blight (4th-level necromancy). Constitution save, 8d8 necrotic, half on success."""

    BASE_LEVEL = 4

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_target',
                'num': 1,
                'range': self.properties.get('range', 30),
                'target_types': ['enemies'],
            }],
            'next': set_target,
        }

    def _dice_count(self, spell_action=None):
        level = self.BASE_LEVEL
        if spell_action is not None:
            level = int(getattr(spell_action, 'at_level', None) or self.properties.get('level', self.BASE_LEVEL))
        extra = max(0, level - self.BASE_LEVEL)
        return 8 + extra

    def _damage(self, battle, opts=None, *, max_damage=False, spell_action=None):
        opts = opts or {}
        dice = self._dice_count(spell_action or opts.get('spell_action'))
        entity = self.source
        if max_damage:
            return DieRoll([8] * dice, 0, 8)
        return DieRoll.roll(
            f"{dice}d8",
            battle=battle,
            entity=entity,
            description='dice_roll.spells.blight',
        )

    def resolve(self, entity, battle, spell_action, _battle_map):
        target = spell_action.target
        if isinstance(target, list):
            target = target[0]
        if target is None:
            return [{
                'type': 'spell_miss',
                'source': entity,
                'target': entity,
                'attack_name': 'blight',
                'message': 'no_target',
                'spell': self.properties,
            }]

        if (callable(getattr(target, 'undead', None)) and target.undead()) or (
            callable(getattr(target, 'construct', None)) and target.construct()
        ):
            return [{
                'type': 'spell_miss',
                'source': entity,
                'target': target,
                'attack_name': 'blight',
                'message': 'immune',
                'spell': self.properties,
            }]

        dc = entity.spell_save_dc(HoldPersonSpell._caster_spell_ability(entity, spell_action))
        plant = _is_plant(target)
        save_opts = {'is_magical': True}
        if plant:
            save_opts['disadvantage'] = ['plant_blight']

        save = SaveCheck.make(target, 'constitution', dc, battle=battle, opts=save_opts)
        failed = not save.passed
        damage_roll = self._damage(
            battle,
            spell_action=spell_action,
            max_damage=plant and failed,
        )
        damage_value = damage_roll if failed else damage_roll.half()
        return [{
            'source': entity,
            'target': target,
            'attack_name': 'blight',
            'damage_type': self.properties.get('damage_type', 'necrotic'),
            'attack_roll': None,
            'damage_roll': damage_roll,
            'advantage_mod': None,
            'adv_info': None,
            'damage': damage_value,
            'spell_save': save.roll,
            'save_failed': failed,
            'dc': dc,
            'cover_ac': None,
            'type': 'spell_damage',
            'spell': self.properties,
        }]
