from natural20.die_roll import DieRoll
import math
import pdb
from natural20.event_manager import EventManager
from natural20.evaluator.entity_state_evaluator import EntityStateEvaluator
from typing import List, Tuple
from natural20.concern.notable import Notable
from natural20.concern.generic_event_handler import GenericEventHandler
from natural20.spell.effects.protection_effect import ProtectionEffect
import uuid
from natural20.utils.conversation import delivered_conversations
from natural20.utils.gibberish import gibberish
import i18n
class Entity(EntityStateEvaluator, Notable):

    ATTRIBUTE_TYPES = ['strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma']
    ATTRIBUTE_TYPES_ABBV = ['str', 'dex', 'con', 'int', 'wis', 'cha']

    ALL_SKILLS = ['acrobatics', 'animal_handling', 'arcana', 'athletics', 'deception', 'history',
                  'insight', 'intimidation', 'investigation', 'medicine', 'nature', 'perception',
                  'performance', 'persuasion', 'religion', 'sleight_of_hand', 'stealth', 'survival']

    SKILL_AND_ABILITY_MAP = {
        'dex': ['acrobatics', 'sleight_of_hand', 'stealth'],
        'wis': ['animal_handling', 'insight', 'medicine', 'perception', 'survival'],
        'int': ['arcana', 'history', 'investigation', 'nature', 'religion'],
        'con': [],
        'str': ['athletics'],
        'cha': ['deception', 'intimidation', 'performance', 'persuasion']
    }

    def __init__(self, name, description, attributes = None, event_manager = None):
        if attributes is None:
            attributes = {}
        if event_manager is None:
            event_manager = EventManager()
        self.name = name
        self._description = description
        self.attributes = attributes
        self.statuses = []
        self.ability_scores = {}
        self.entity_event_hooks = {}
        self.effects = {}
        self.grapples = []
        self.grappling = []
        self.flying = False
        self.casted_effects = []
        self.death_fails = 0
        self.death_saves = 0
        self.hidden_stealth = None
        self._temp_hp = 0
        self._temp_hp_source = None
        self.event_handlers = {}
        self.event_manager = event_manager
        self.concentration = None
        self.is_concealed = False
        self.is_secret = False
        self.is_admin = False
        self.perception_results = {}
        self.buttons = {}
        self.entity_uid = uuid.uuid4()
        self.is_passive = False
        self.group = None
        self.activated = False
        self.dialogue = []
        self.condition_immunities = []
        self.damage_vulnerabilities = []
        self.damage_resistances = []
        self.damage_immunities = []
        self.pocket_dimension = []
        self.equipped_effects = {}
        self.help_actions = {}
        self.conversation_buffer = []
        self.memory_buffer = []
        self.battle_music = None
        self.helping_with = set()
        self.check_results = {}
        self.owner = None
        self.targettable = True
        self.conversation_controller = None
        self.dialog = False
        # Phase 3 modifier registry. Each entry is a dict with keys:
        # ``kind``, ``source``, ``value``, ``advantage``, ``disadvantage``,
        # ``condition``. ``value`` may be an int, a dice string, or a
        # callable ``(entity, context) -> int | str | None``.
        self._modifiers = []
        # Phase 4: opt-in resource pools keyed by name. Existing
        # per-attribute counters (second_wind_count, wild_shape_count,
        # rage_count, …) keep working untouched; this dict is purely
        # additive.
        self.resources = {}
        # Attach methods dynamically
        for ability, skills in self.SKILL_AND_ABILITY_MAP.items():
            for skill in skills:
                setattr(self, f"{skill}_mod", self.make_skill_mod_function(skill, ability))
                setattr(self, f"{skill}_check", self.make_skill_check_function(skill))

    def backstory(self):
        return self.properties.get('backstory', '')

    def immune_to_condition(self, condition):
        return condition in self.condition_immunities

    def profile_image(self):
        return self.token_image()

    def passive(self):
        return self.is_passive

    def description(self):
        return self.properties.get('description', self._description)

    def alignment(self) -> str:
        return self.properties.get('alignment', 'neutral')

    def items_label(self):
      return self.t(f"entity.#{self.__class__}.item_label", default=f"{self.name} Items")

    def concentration_on(self, effect):
        if effect is None:
            raise ValueError("effect cannot be None")

        if self.concentration:
            self.dismiss_effect(self.concentration)
        self.concentration = effect

    def concealed(self):
        return self.is_concealed

    def conceal_perception_dc(self) -> int:
        return None

    def current_concentration(self):
        return self.concentration
    
    # --- Phase 3 modifier registry --------------------------------------

    def add_modifier(self, kind, source, value=0, *,
                     advantage=False, disadvantage=False, condition=None):
        """Register an attack/save/damage/check modifier on this entity.

        ``kind`` is a string like ``'attack_roll'``, ``'save_roll'``,
        ``'damage_roll'``, ``'ac'``, ``'spell_attack'``. ``value`` may be
        an int, dice string (e.g. ``'1d4'``), or callable
        ``(entity, context) -> int | str | None``. ``condition`` may be a
        callable ``(entity, context) -> bool`` that gates inclusion.
        """
        if not hasattr(self, '_modifiers') or self._modifiers is None:
            self._modifiers = []
        self._modifiers.append({
            'kind': str(kind),
            'source': source,
            'value': value,
            'advantage': bool(advantage),
            'disadvantage': bool(disadvantage),
            'condition': condition,
        })

    def remove_modifier(self, source):
        """Remove every modifier registered under ``source`` (==)."""
        if not getattr(self, '_modifiers', None):
            return
        self._modifiers = [m for m in self._modifiers if m.get('source') is not source]

    def collect_modifiers(self, kind, context=None):
        """Return all matching modifier entries for ``kind``.

        Each returned dict carries ``value`` resolved to int|str (callable
        results are evaluated), plus ``advantage`` / ``disadvantage`` flags
        and the original ``source`` for stacking checks.
        """
        out = []
        mods = getattr(self, '_modifiers', None) or []
        for m in mods:
            if m.get('kind') != kind:
                continue
            cond = m.get('condition')
            if cond is not None:
                try:
                    if not cond(self, context or {}):
                        continue
                except Exception:
                    continue
            raw = m.get('value', 0)
            if callable(raw):
                try:
                    raw = raw(self, context or {})
                except Exception:
                    raw = None
            if raw is None:
                continue
            out.append({
                'source': m.get('source'),
                'value': raw,
                'advantage': bool(m.get('advantage')),
                'disadvantage': bool(m.get('disadvantage')),
            })
        return out

    # --- Phase 4 resource pool helpers ---------------------------------

    def _resources_dict(self):
        if not hasattr(self, 'resources') or self.resources is None:
            self.resources = {}
        return self.resources

    def register_resource(self, name, max_value, *, restore_on='long_rest', current=None):
        """Create or update a named ResourcePool on this entity."""
        from natural20.resource_pool import ResourcePool
        pools = self._resources_dict()
        existing = pools.get(name)
        if existing is not None:
            existing.max_value = int(max_value)
            existing.restore_on = restore_on
            if current is not None:
                existing.current = int(current)
            else:
                existing.current = min(existing.current, existing.max_value)
            return existing
        pool = ResourcePool(name, max_value, restore_on=restore_on, current=current)
        pools[name] = pool
        return pool

    def get_resource(self, name):
        return self._resources_dict().get(name)

    def resource_value(self, name, default=0):
        pool = self._resources_dict().get(name)
        return pool.current if pool is not None else default

    def has_resource(self, name, n=1):
        pool = self._resources_dict().get(name)
        return pool is not None and pool.available(n)

    def consume_resource(self, name, n=1):
        pool = self._resources_dict().get(name)
        if pool is None:
            return False
        return pool.consume(n)

    def restore_resource(self, name, n=None):
        pool = self._resources_dict().get(name)
        if pool is None:
            return None
        return pool.restore(n)

    def restore_resources(self, rest_kind):
        """Refill every pool whose ``restore_on`` matches ``rest_kind``."""
        for pool in self._resources_dict().values():
            pool.restore_for(rest_kind)

    def kind_of_door(self):
        """
        Returns True if this entity is a kind of door, False otherwise.
        This is used to determine if the entity can be interacted with as a door.
        """
        return self.properties.get('kind_of_door', False)

    def class_descriptor(self):
        return self.name.lower()

    def class_feature(self, feature):
        return False

    def class_and_level(self):
        return []

    def conversable(self):
        return False

    def conversation_history(self, listener):
        history = []
        
        for message in self.conversation_buffer:
            if message['source'] == self and (message.get("target") == "all" or listener in message.get('directed_to', [])):
                language = message.get('language', 'common')
                if language in listener.languages():
                    history.append({
                        'source': self.label(),
                        'target': listener.label(),
                        'message': message['message'],
                        'language': language,
                        'type': 'entity'
                    })
                else:
                    # If the listener does not understand the language, use gibberish
                    message['message'] = gibberish(message['message'], language=language)
            if self in message.get('directed_to', []):
                language = message.get('language', 'common')
                history.append({
                    'source': message['source'].label(),
                    'message': message['message'],
                    'target': self.label(),
                    'language': language,
                    'type': 'player'
                })
        return history
    
    def conversation_keywords(self):
        """
        Returns a list of keywords that this entity can respond to in conversations.
        This is used to trigger specific actions or responses based on the conversation context.
        """
        return self.properties.get('converstation_keywords', [])
 
    def conversation(self, outgoing=True, listener_languages=None):
        if listener_languages is None:
            listener_languages = ["common"]

        if not isinstance(listener_languages, list):
            listener_languages = [listener_languages]

        if outgoing:
            outgoing_messages = []
            for message in self.conversation_buffer:
                if message['source'] == self:
                    if  message.get('language') and message['language'] in listener_languages:
                        outgoing_messages.append(message['message'])
                    else:
                        outgoing_messages.append(gibberish(message['message'], language=message.get('language', 'common')))
            return outgoing_messages
        else:
            incoming_messages = []
            for message in self.conversation_buffer:
                if message['target'] == self:
                    if message['language'] in listener_languages:
                        incoming_messages.append(message['message'])
                    else:
                        incoming_messages.append(gibberish(message['message'], language=message.get('language', 'common')))
            return incoming_messages

    def receive_conversation(self, source, message, language=None,  directed_to=None):
        if language is None:
            language = "common"
        if directed_to is None:
            directed_to = []
        self.conversation_buffer.append({ 'source': source, 'directed_to': directed_to, 'message': message, 'target': self, 'language': language, 'time' : self.session.game_time })
        self.memory_buffer.append({ 'source': source, 'directed_to': directed_to, 'message': message, 'target': self, 'language': language, 'time' : self.session.game_time })
        self.resolve_trigger('conversation', { 'source': source, 'message': message, 'memory_buffer': self.memory_buffer,
                                              'target': self, 'language': language })
        if self.conversation_controller:
            self.conversation_controller.process_message(self, source, message, language, self.memory_buffer, directed_to)

    def send_conversation(self, message, distance_ft=30, targets=None, language=None, volume=None) -> List[Tuple['Entity', str, List['Entity']]]:
        if language is None:
            language = "common"
        language = language.lower()
        self.conversation_buffer.append({ 'source': self, 'message': message, 'directed_to': targets, 'targets': targets, 'language': language, 'distance_ft': distance_ft, 'volume': volume })
        self.memory_buffer.append({ 'source': self, 'message': message, 'directed_to': targets, 'targets': targets, 'language': language, 'distance_ft': distance_ft, 'volume': volume })
        self.session.event_manager.received_event({"source": self,
                                                   "event" : 'conversation',
                                                   "message" : message,
                                                   "language" : language,
                                                   "targets" : targets,
                                                   "distance_ft": distance_ft,
                                                   "volume": volume})
        entity_map = self.session.map_for_entity(self)
        nearby = []

        for delivery in delivered_conversations(self, message, entity_map, distance_ft=distance_ft, mode=volume, targets=targets, language=language):
            other_entity = delivery['entity']
            rendered_message = delivery['message']
            nearby.append([other_entity, rendered_message, targets])
            other_entity.receive_conversation(self, rendered_message, language=language, directed_to=targets)

        return nearby


    def clear_conversation_buffer(self):
        self.conversation_buffer = []

    def armor_class(self):
        return 0

    def equipped_ac(self):
        return self.armor_class()

    def any_class_feature(self, features):
        return False

    def is_npc(self):
        return False

    def object(self):
        return False
    
    def secret(self) -> bool:
        return self.is_secret
    
    def secret_perception_dc(self) -> int:
        return self.properties.get('secret_perception_dc', self.properties.get('secret_dc', None))

    def expertise(self, prof):
        return prof in self.properties.get('expertise', [])

    def is_two_handed_weapon(self, weapon):
        weapon_properties = weapon.get('properties', [])
        if not weapon_properties:
            return False
        return 'versatile' in weapon_properties and self.used_hand_slots() <= 1.0

    # Returns the proficiency bonus of this entity
    # @return [Integer]
    def proficiency_bonus(self):
        return self.properties.get('proficiency_bonus', 2)

    def make_skill_mod_function(self, skill, ability):
        def skill_mod():
            if self.is_npc() and skill in self.properties.get('skills', {}):
                return self.properties['skills'][skill]

            modifiers = getattr(self, f"{ability}_mod")()
            if self.proficient(skill):
                bonus = self.proficiency_bonus() * 2 if self.expertise(skill) else self.proficiency_bonus()
            else:
                bonus = 0
                # Bard - Jack of All Trades: add half proficiency (rounded
                # down) to ability checks the entity is not proficient in.
                if self.any_class_feature(['jack_of_all_trades']):
                    bonus = self.proficiency_bonus() // 2
            return modifiers + bonus
        return skill_mod

    def make_skill_check_function(self, skill):
        def skill_check(battle=None, **opts):
            advantage_modifiers = []
            disavantage_modifiers = []
            if self.is_npc() and self.properties.get('skills', {}).get(skill):
                modifiers = self.properties['skills'][skill]
            else:
                modifiers = getattr(self, f"{skill}_mod")()

            description = opts.get('description', f"dice roll for {skill}")

            if self.poisoned():
                disavantage_modifiers.append('poisoned')

            for _, v in self.help_actions.items():
                v.helping_with.remove(self)
                advantage_modifiers.append('helped')

            self.help_actions.clear()

            advantage = len(advantage_modifiers) > 0
            disadvantage = len(disavantage_modifiers) > 0

            # If both advantage and disadvantage are active, they cancel out
            if advantage and disadvantage:
                advantage = disadvantage = False

            roll = DieRoll.roll_with_lucky(self, f"1d20+{modifiers}",
                                           description=description,
                                           advantage=advantage,
                                           disadvantage=disadvantage,
                                           battle=battle)
            roll.metadata['skill'] = skill
            roll.metadata['is_ability_check'] = True
            return roll
        return skill_check

    def __str__(self):
        return f"{self.name}"

    def __repr__(self):
        return f"{self.name}"
    
    def effects_str(self):
        return [str(effect['effect']) for effect in self.current_effects()]

    def name(self):
        return self.name

    def hit_points(self):
        return self.hp()

    def hp(self):
        return self.attributes["hp"]

    def max_hp(self):
        return self.attributes.get('max_hp', self.properties.get('max_hp', 0))

    def set_hp(self, hp, override_max=False):
        if override_max:
            self.attributes["hp"] = hp
            self.attributes["max_hp"] = hp
        else:
            self.attributes["hp"] = min(hp, self.max_hp())

    def temp_hp(self):
        return self._temp_hp

    def temp_hp_source(self):
        return self._temp_hp_source

    def grant_temp_hp(self, amount, source=None, effect=None):
        if amount is None:
            return self._temp_hp

        amount = int(amount)
        if amount <= 0:
            if effect and self._temp_hp_source == effect:
                self.clear_temp_hp(effect=effect)
            return self._temp_hp

        previous = self._temp_hp
        replace = False

        if effect and self._temp_hp_source == effect:
            replace = True
        elif amount > previous:
            replace = True

        if not replace:
            return self._temp_hp

        self._temp_hp = amount
        self._temp_hp_source = effect
        return self._temp_hp

    def clear_temp_hp(self, effect=None):
        if effect is not None and self._temp_hp_source is not None and self._temp_hp_source != effect:
            return

        self._temp_hp = 0
        self._temp_hp_source = None

    # Returns the character hit die
    # @return [dict]
    def hit_die(self):
        return self._current_hit_die

    def darkvision(self, distance):
        if not self.properties.get('darkvision'):
            return False
        adjusted_darkvision_distance = self.properties.get('darkvision')
        if adjusted_darkvision_distance < distance:
            return False
        return True

    def blinded(self):
        _result = self.eval_effect('blinded_override', opts={'value': self.statuses})
        if _result:
            return True
        else:
            return 'blinded' in self.statuses

    def blindsight(self, distance):
        if not self.properties.get('blindsight'):
            return False
        adjusted_blindsight_distance = self.properties.get('blindsight')
        if adjusted_blindsight_distance < distance:
            return False
        return True

    def has_blindsight(self):
        return self.properties.get('blindsight')


    def label(self):
        if self.properties.get('label'):
            return self.properties.get('label')
        return i18n.t(self.name)

    def token_image(self):
        return self.properties.get('token_image') or f"token_{(self.properties.get('kind') or self.properties.get('sub_type') or self.properties.get('name').replace(' ', '_')).lower()}.png"

    def token_size(self):
        square_size = self.size()

        if square_size == 'tiny':
            return 1
        elif square_size == 'small':
            return 1
        elif square_size == 'medium':
            return 1
        elif square_size == 'large':
            return 2
        elif square_size == 'huge':
            return 3
        else:
            raise ValueError(f"invalid size {square_size}")

    def size_identifier(self):
        square_size = self.size()
        if square_size == 'tiny':
            return 0
        elif square_size == 'small':
            return 1
        elif square_size == 'medium':
            return 2
        elif square_size == 'large':
            return 3
        elif square_size == 'huge':
            return 4
        elif square_size == 'gargantuan':
            return 5
        else:
            raise ValueError(f"invalid size {square_size}")

    def languages(self):
        languages = self.properties.get('languages', [])
        # Ensure we always return a list, never None
        if languages is None:
            languages = []

        # Speak With Animals (modified) grants temporary beast comprehension.
        try:
            from natural20.utils.animal_communication import has_animal_communication
            if has_animal_communication(self.session, entity=self):
                return sorted(set(list(languages) + ['beast']))
        except Exception:
            pass

        return languages

    def long_jump_distance(self):
        if not self.ability_scores.get('str'):
            return 0
        return self.strength()

    def passive_perception(self):
        return self.properties.get('passive_perception', 10 + self.wis_mod())

    def passive_insight(self):
        return self.properties.get('passive_insight', 10 + self.wis_mod())

    def passive_investigation(self):
        return self.properties.get('passive_investigation', 10 + self.int_mod())

    # def perception_check(self, battle, advantage=False, disadvantage=False):
    #     entity_state = battle.entity_state_for(self)
    #     if not entity_state:
    #         return 0
    #     self.make_skill_check('perception', battle, advantage, disadvantage)
    #     return DieRoll.roll(f"1d20+{self.wis_mod()}", description="perception check", entity=self, battle=battle, advantage=advantage)

    def drop_grapple(self):
        for target in self.grappling:
            self.ungrapple(target)

    def dead(self):
        return 'dead' in self.statuses

    def undead(self):
        return 'undead' in self.properties.get('race', [])

    def race(self):
        race = self.properties.get('race', [])
        return " ".join(race)

    def add_casted_effect(self, effect):
        if effect not in self.casted_effects:
            self.casted_effects.append(effect)

    def has_casted_effect(self, effect: str):
        casted_effects_id = [effect['effect'].id for effect in self.casted_effects]
        return effect in casted_effects_id

    def has_spell_effect(self, spell):
        active_effects = [effect for effects in self.effects.values() for effect in effects if not effect.get('expiration') or effect.get('expiration') > self.session.game_time]
        return any(effect['effect'].id == spell for effect in active_effects)


    def register_effect(self, effect_type, handler, method_name=None, effect=None, source=None, duration=None):
        if effect and isinstance(effect, dict):
            raise Exception(f"Effect {effect} is a dict")
        if effect_type not in self.effects:
            self.effects[effect_type] = []
        effect_descriptor = {
            'handler': handler,
            'method': method_name if method_name is not None else effect_type,
            'effect': effect,
            'source': source
        }
        if duration is not None:
            effect_descriptor['expiration'] = self.session.game_time + int(duration)
        self.effects[effect_type].append(effect_descriptor)

    def register_event_hook(self, event_type, handler, method_name=None, source=None, effect=None, duration=None):
        if event_type not in self.entity_event_hooks:
            self.entity_event_hooks[event_type] = []
        event_hook_descriptor = {
            'handler': handler,
            'method': method_name if method_name is not None else event_type,
            'effect': effect,
            'source': source
        }
        if duration is not None:
            event_hook_descriptor['expiration'] = self.session.game_time + int(duration)
        self.entity_event_hooks[event_type].append(event_hook_descriptor)

    def ability_mod(self, type):
        mod_type = {
            'wisdom': 'wis',
            'dexterity': 'dex',
            'constitution': 'con',
            'intelligence': 'int',
            'charisma': 'cha',
            'strength': 'str'
        }.get(type, None)
        if mod_type:
            return self.modifier_table(self.ability_scores.get(mod_type))
        else:
            return None

    def do_help(self, battle, target):
        if not target:
            raise ValueError("Target is required")

        # drop other help actions
        for other_targets in self.helping_with:
            # help_actions on the recipient is keyed by the helper; the value
            # is the helper itself (consumed by callers via dict.values()).
            other_targets.help_actions.pop(self, None)

        target.help_actions[self] = self
        self.helping_with.add(target)

    # Checks if an item is equipped
    # @param item_name [String,Symbol]
    # @return [Boolean]
    def equipped(self, item_name):
        return item_name in [item['name'] for item in self.equipped_items()]

    # Equips an item
    # @param item_name [String,Symbol]
    def equip(self, item_name, ignore_inventory=False):
        self.properties['equipped'] = self.properties.get('equipped', [])
        item_name_str = str(item_name)
        if ignore_inventory:
            self.properties['equipped'].append(item_name_str)
            self.resolve_trigger('equip')
            return
        item = self.deduct_item(item_name)
        if item:
            self.properties['equipped'].append(item_name_str)
            self.resolve_trigger('equip')
            loaded_item = self.session.load_equipment(item_name)
            if loaded_item and loaded_item.get('effect'):
                for effect in loaded_item['effect']:
                    self.add_equiped_effect(item_name, effect)
        else:
            # Fallback: try to load from session (magic items not in inventory)
            loaded_item = self.session.load_thing(item_name)
            if loaded_item:
                self.properties['equipped'].append(item_name_str)
                self.resolve_trigger('equip')
                if loaded_item.get('effect'):
                    for effect in loaded_item['effect']:
                        self.add_equiped_effect(item_name, effect)

    def add_equiped_effect(self, item_name, effect):
        loaded_item = self.session.load_equipment(item_name)
        if loaded_item.get('effect'):
            for effect in loaded_item['effect']:
                if effect == 'protection':
                    self.equipped_effects[item_name] = ProtectionEffect(self)

    def make_dead(self, battle=None):
        if not self.dead():
            # If this entity is configured for a phase transition (e.g. a
            # multi-form boss), attempt the morph instead of dying outright.
            if self._maybe_phase_transition(battle=battle):
                return

            self.session.event_manager.received_event({ 'source': self, 'event': 'died' })
            # print(f"{self.name} died. :(")
            self.drop_grapple()
            if 'dead' not in self.statuses:
                self.statuses.append('dead')
            self.do_prone()

            if 'stable' in self.statuses:
                self.statuses.remove('stable')
            if 'unconscious' in self.statuses:
                self.statuses.remove('unconscious')

            # dismiss all effects
            for effect in self.casted_effects:
                self.dismiss_effect(effect['effect'])

            # Fire YAML-registered 'died' event hooks (e.g. spawn, message).
            try:
                self.resolve_trigger('died', { 'battle': battle })
            except Exception:
                pass

            self.after_death()

    def _maybe_phase_transition(self, battle=None):
        """If self.properties['phase_transition'] is configured, swap this
        entity for a fresh NPC of the configured form, preserving position,
        group, controller, and initiative slot. Returns True if the
        transition fired (and the caller should skip the normal death path),
        False otherwise.

        YAML schema (on the npc that will transition):
            phase_transition:
              npc: walter_graveborn       # required: target npc sub_type
              label: "Walter, the Graveborn"  # optional override label
              keep_uid: true              # optional, default true
              narration: "..."            # optional read-aloud text
              overrides: { ... }          # optional npc property overrides
        """
        cfg = self.properties.get('phase_transition') if hasattr(self, 'properties') else None
        if not cfg:
            return False
        # Guard against re-entry / repeat transitions.
        if self.properties.get('_phase_transitioned'):
            return False
        self.properties['_phase_transitioned'] = True

        if isinstance(cfg, str):
            cfg = { 'npc': cfg }
        target_npc = cfg.get('npc')
        if not target_npc:
            return False

        # Resolve the map this entity currently occupies.
        target_map = None
        try:
            target_map = self.session.map_for(self)
        except Exception:
            target_map = None
        if target_map is None:
            # Cannot transition without a map; allow normal death.
            self.properties.pop('_phase_transitioned', None)
            return False
        try:
            position = target_map.position_of(self)
        except Exception:
            position = None
        if position is None:
            self.properties.pop('_phase_transitioned', None)
            return False

        # Build the next-phase NPC.
        from natural20.npc import Npc
        overrides = dict(cfg.get('overrides') or {})
        if cfg.get('label') and 'label' not in overrides:
            overrides['label'] = cfg['label']
        keep_uid = cfg.get('keep_uid', True)
        if keep_uid:
            overrides['entity_uid'] = self.entity_uid
        try:
            new_entity = Npc(self.session, target_npc, {
                'name': cfg.get('name', self.name),
                'overrides': overrides,
                'rand_life': False,
            })
        except Exception:
            self.properties.pop('_phase_transitioned', None)
            return False

        # Capture group/controller/initiative from current battle (if any).
        prior_group = None
        prior_controller = None
        prior_initiative = None
        if battle is not None and self in getattr(battle, 'entities', {}):
            state = battle.entities[self]
            prior_group = state.get('group')
            prior_controller = state.get('controller')
            prior_initiative = state.get('initiative')

        # Release engulfed / grappled targets and casted effects on old form.
        for effect in list(self.casted_effects):
            self.dismiss_effect(effect['effect'])
        self.drop_grapple()

        # Remove the old entity from the map (silent: not flagged as dead).
        try:
            target_map.remove(self, battle=battle)
        except Exception:
            pass

        # Add the new entity at the same square.
        try:
            target_map.add(new_entity, position[0], position[1], group=prior_group or 'b')
        except Exception:
            pass

        # Splice into the active battle preserving the initiative slot.
        if battle is not None:
            try:
                if self in battle.entities:
                    del battle.entities[self]
                if self in battle.combat_order:
                    idx = battle.combat_order.index(self)
                    battle.combat_order[idx] = new_entity
                state = {
                    'group': prior_group or 'b',
                    'action': 0,
                    'bonus_action': 0,
                    'reaction': 0,
                    'movement': 0,
                    'stealth': 0,
                    'statuses': set(),
                    'active_perception': 0,
                    'active_perception_disadvantage': 0,
                    'free_object_interaction': 0,
                    'legendary_actions': 0,
                    'target_effect': {},
                    'two_weapon': None,
                    'positions_entered': {},
                    'controller': prior_controller,
                    'help_with': {},
                }
                if prior_initiative is not None:
                    state['initiative'] = prior_initiative
                else:
                    state['initiative'] = new_entity.initiative(battle)
                battle.entities[new_entity] = state
                battle.groups.setdefault(prior_group or 'b', set()).add(new_entity)
                self.session.register_entity(new_entity)
            except Exception:
                pass

        # Emit a structured event for UI / logs.
        try:
            self.session.event_manager.received_event({
                'source': self,
                'event': 'phase_transition',
                'next_form': new_entity,
                'narration': cfg.get('narration'),
            })
        except Exception:
            pass

        return True

    def observe(self, entity_map, range_ft=30):
        map_entities = entity_map.entities_in_range(self, range_ft)
        nearby = []

        for other_entity in map_entities:
            if other_entity == self:
                continue
            if not other_entity.conversable():
                continue

            line_of_sight = entity_map.can_see(self, other_entity)
            if not line_of_sight:
                continue

            nearby.append([other_entity,  entity_map.distance(self, other_entity) * entity_map.feet_per_grid])
        return nearby
    
    def after_death(self):
        pass

    def can_hide(self):
        return self.properties.get("can_hide", False)

    def cover_ac(self):
        return self.properties.get("cover_ac", 0)

    def make_unconscious(self):
        if not self.unconscious() and not self.dead():
            self.drop_grapple()
            self.event_manager.received_event({ 'source': self, 'event': 'unconscious' })
            # print(f"{self.name} is unconscious.")

            self.do_prone()
            self.statuses.append('unconscious')

            # dismiss all effects
            for effect in self.casted_effects:
                self.dismiss_effect(effect['effect'])


    def lockpick(self, battle=None):
        proficiency_mod = self.dex_mod()
        if self.proficient("thieves_tools"):
            bonus = self.proficiency_bonus() * 2 if self.expertise("thieves_tools") else self.proficiency_bonus()
        else:
            bonus = 0
        proficiency_mod += bonus
        return DieRoll.roll_with_lucky(self, "1d20+{proficiency_mod}",
                            description=self.t('dice_roll.thieves_tools'),
                            battle=battle)

    def saving_throw_mod(self, save_type):
        modifier = self.ability_mod(save_type)
        if modifier is None:
            return 0
        modifier += self.proficiency_bonus() if self.proficient(f"{save_type}_save") else 0
        return modifier

    # Default radius (feet) used when scanning for hostile creatures that
    # would prevent a rest from occurring.
    REST_HOSTILE_RADIUS_FT = 60

    def _resolve_rest_map(self, battle_map):
        """Return a Map for rest-precondition checks, or None if unavailable."""
        if battle_map is not None:
            return battle_map
        session = getattr(self, 'session', None)
        if session is None:
            return None
        resolver = getattr(session, 'map_for_entity', None)
        if not callable(resolver):
            return None
        try:
            return resolver(self)
        except Exception:
            return None

    def _nearby_hostiles(self, battle, battle_map, radius_ft=None):
        """Return alive, conscious, opposing entities within ``radius_ft``."""
        if battle_map is None:
            return []
        if radius_ft is None:
            radius_ft = self.REST_HOSTILE_RADIUS_FT
        session = getattr(self, 'session', None)
        try:
            candidates = battle_map.entities_in_range(self, radius_ft)
        except Exception:
            return []

        my_group = getattr(self, 'group', None)
        if battle is not None:
            state = None
            try:
                state = battle.entity_state_for(self)
            except Exception:
                state = None
            if state and state.get('group'):
                my_group = state['group']

        hostiles = []
        for other in candidates:
            if other is self:
                continue
            try:
                if other.dead() or other.unconscious():
                    continue
            except Exception:
                continue

            if battle is not None:
                try:
                    if battle.opposing(self, other):
                        hostiles.append(other)
                        continue
                except Exception:
                    pass

            other_group = getattr(other, 'group', None)
            if battle is not None:
                try:
                    other_state = battle.entity_state_for(other)
                    if other_state and other_state.get('group'):
                        other_group = other_state['group']
                except Exception:
                    pass

            # When either side has no group we cannot determine hostility, so
            # treat the creature as non-hostile.  Campaigns that want a more
            # restrictive policy should assign group labels.
            if not my_group or not other_group:
                continue
            if session is not None:
                try:
                    if not session.opposing(my_group, other_group):
                        continue
                except Exception:
                    continue
            hostiles.append(other)
        return hostiles

    def _check_rest_preconditions(self, battle, battle_map, kind):
        """Validate shared rest preconditions for short and long rests."""
        if battle is not None and getattr(battle, 'started', False):
            raise ValueError(f"cannot take a {kind} rest while combat is in progress")
        hostiles = self._nearby_hostiles(battle, battle_map)
        if hostiles:
            names = ", ".join(
                getattr(h, 'name', None) or getattr(h, 'label', lambda: 'unknown')()
                for h in hostiles[:3]
            )
            raise ValueError(
                f"cannot take a {kind} rest while hostile creatures are nearby: {names}"
            )

    def _check_long_rest_location(self, battle_map):
        """Honor map/campaign opt-outs (``allow_long_rest: false``)."""
        if battle_map is not None:
            map_props = getattr(battle_map, 'properties', None) or {}
            if map_props.get('allow_long_rest') is False:
                reason = map_props.get('long_rest_denied_message') \
                    or "long rests are not permitted in this location"
                raise ValueError(reason)
        session = getattr(self, 'session', None)
        if session is not None:
            game_props = getattr(session, 'game_properties', None) or {}
            if game_props.get('allow_long_rest') is False:
                reason = game_props.get('long_rest_denied_message') \
                    or "long rests are not permitted in this campaign"
                raise ValueError(reason)

    def _consume_long_rest_rations(self):
        """Consume one ration from the entity's inventory; raise if absent.

        Only entities with an ``inventory`` mapping (player characters and
        NPCs that track gear) participate; entities without an inventory are
        treated as creatures that do not need to eat for long-rest purposes.
        """
        inventory = getattr(self, 'inventory', None)
        if inventory is None:
            return
        if self.item_count('rations') < 1:
            raise ValueError("a long rest requires at least 1 ration to consume")
        self.deduct_item('rations', 1)

    def rest_status(self, battle=None, battle_map=None, require_rations=False):
        """Return a structured availability report for short/long rests.

        Does not raise; returns a dict like::

            {
                'short': {'allowed': bool, 'reasons': [str, ...],
                          'force_overrides': bool},
                'long':  {'allowed': bool, 'reasons': [str, ...],
                          'force_overrides': bool, 'requires_rations': bool,
                          'rations_available': int},
            }

        ``force_overrides`` is True when ``force=True`` would bypass every
        listed reason (currently the case for combat/hostile/location guards;
        missing rations cannot be force-bypassed).
        """
        battle_map = self._resolve_rest_map(battle_map)
        in_combat = bool(battle is not None and getattr(battle, 'started', False))

        short_reasons = []
        if in_combat:
            short_reasons.append("Combat is in progress")
        hostiles = self._nearby_hostiles(battle, battle_map)
        if hostiles:
            names = ", ".join(
                getattr(h, 'name', None) or getattr(h, 'label', lambda: 'unknown')()
                for h in hostiles[:3]
            )
            short_reasons.append(f"Hostile creatures nearby: {names}")

        long_reasons = list(short_reasons)
        # Map / campaign opt-out
        if battle_map is not None:
            map_props = getattr(battle_map, 'properties', None) or {}
            if map_props.get('allow_long_rest') is False:
                long_reasons.append(
                    map_props.get('long_rest_denied_message')
                    or "Long rests are not permitted in this location"
                )
        session = getattr(self, 'session', None)
        if session is not None:
            game_props = getattr(session, 'game_properties', None) or {}
            if game_props.get('allow_long_rest') is False:
                long_reasons.append(
                    game_props.get('long_rest_denied_message')
                    or "Long rests are not permitted in this campaign"
                )

        rations_available = 0
        rations_blocking = False
        if getattr(self, 'inventory', None) is not None:
            try:
                rations_available = int(self.item_count('rations') or 0)
            except Exception:
                rations_available = 0
            if require_rations and rations_available < 1:
                long_reasons.append("No rations available to consume")
                rations_blocking = True

        return {
            'short': {
                'allowed': not short_reasons,
                'reasons': short_reasons,
                'force_overrides': bool(short_reasons),
            },
            'long': {
                'allowed': not long_reasons,
                'reasons': long_reasons,
                # Force can bypass everything *except* missing rations.
                'force_overrides': bool(long_reasons) and not rations_blocking,
                'requires_rations': bool(require_rations),
                'rations_available': rations_available,
            },
        }

    def short_rest(self, battle, prompt=False, force=False, battle_map=None):
        """Take a short rest (D&D 5e SRD).

        Spends hit dice (interactively if the controller exposes
        ``prompt_hit_die_roll``, otherwise greedily up to max HP), revives a
        stable but unconscious creature to 1 HP, dispatches per-class
        ``short_rest_for_<klass>`` hooks (Second Wind, Arcane Recovery,
        warlock pact slots, etc.), and fires a ``short_rest`` event/trigger
        so registered effects can react.

        Restrictions (waived when ``force=True``):

        * A short rest may not begin while a battle is in progress.
        * No hostile creature (opposing group, alive and conscious) may be
          within :pyattr:`REST_HOSTILE_RADIUS_FT` of the resting entity.

        ``battle_map`` is used to scan for nearby hostiles; when omitted the
        current map is resolved from ``self.session.map_for_entity(self)``.
        """
        if not force:
            self._check_rest_preconditions(battle, self._resolve_rest_map(battle_map), 'short')

        controller = battle.controller_for(self) if battle is not None else None

        # hit die management
        if prompt and controller and hasattr(controller, 'prompt_hit_die_roll'):
            while sum(self._current_hit_die.values()) > 0:
                ans = controller.prompt_hit_die_roll(self, [k for k, v in self._current_hit_die.items() if v > 0])

                if ans == 'skip':
                    break
                else:
                    self.use_hit_die(ans, battle=battle)
        else:
            while self.hp() < self.max_hp():
                available_die = [die for die, num in self._current_hit_die.items() if num > 0]
                available_die.sort()

                if not available_die:
                    break

                old_hp = self.hp()

                self.use_hit_die(available_die[0], battle=battle)

                if self.hp() == old_hp:
                    break

        if self.unconscious() and self.stable():
            self.heal(1)

        # Per-class short-rest hooks (Second Wind reset, pact slots, Arcane
        # Recovery, channel divinity, ki, etc.)  Each is optional.
        for klass in self._iter_class_names():
            hook = getattr(self, f"short_rest_for_{klass}", None)
            if callable(hook):
                hook(battle)

        # Reset breath weapon usage on short rest (Dragonborn racial trait)
        if hasattr(self, 'breath_weapon_used'):
            self.breath_weapon_used = False

        self.restore_resources('short_rest')
        self.resolve_trigger('short_rest')
        self.event_manager.received_event({'source': self, 'event': 'short_rest'})

    def _iter_class_names(self):
        """Yield class names for dispatching per-class rest hooks.

        Player characters expose ``c_class()`` returning a ``{klass: level}``
        dict; NPCs and other entities have no class hooks.
        """
        c_class = getattr(self, 'c_class', None)
        if callable(c_class):
            try:
                classes = c_class()
            except Exception:
                classes = None
            if isinstance(classes, dict):
                for klass in classes.keys():
                    yield klass

    def use_hit_die(self, die_type, battle=None):
        if die_type in self._current_hit_die and self._current_hit_die[die_type] > 0:
            self._current_hit_die[die_type] -= 1
            hit_die_roll = DieRoll.roll(f"d{die_type}", battle=battle, entity=self, description="hit die")
            self.event_manager.received_event({'source': self, 'event': 'hit_die', 'roll': hit_die_roll})
            self.heal(hit_die_roll.result())

    def grappled(self):
        return 'grappled' in self.statuses

    def do_grapple(self, target):
        if not target.immune_to_condition('grappled'):
            self.grappling.append(target)

    def is_grappling(self):
        return len(self.grappling) > 0

    def grappling_targets(self):
        return self.grappling

    # @param target [Natural20::Entity]
    def ungrapple(self, target):
        if target in self.grappling:
            self.grappling.remove(target)
        if target in target.grapples:
            target.grapples.remove(self)
        if len(target.grapples)==0 and 'grappled' in target.statuses:
            target.statuses.remove('grappled')


    def unconscious(self):
        return not self.dead() and 'unconscious' in self.statuses

    def conscious(self):
        return not self.dead() and not self.unconscious()

    def poisoned(self):
        if self.eval_effect('poisoned', opts={'value': self.statuses}):
            return True
        return 'poisoned' in self.statuses

    def invisible(self):
        return 'invisible' in self.statuses
    
    def opaque(self, _origin):
        return False
    
    def damage_threshold(self):
        return 0
    
    def passable(self, _origin):
        return True
    
    def token_image_transform(self):
        return None

    def stand(self):
        self.statuses.remove('prone')

    def standing_jump_distance(self):
        if not self.ability_scores.get('str'):
            return 0
        return int(self.strength() / 2)

    def resistant_to(self, damage_type, source=None, weapon=None):
        """Check if entity resists the given damage type.

        ``source`` is the attacking entity (used to check for magical
        weapons/equipment). ``weapon`` is the weapon dict (optional —
        inferred from ``source`` when omitted).

        Creatures with "non-magical bludgeoning/piercing/slashing"
        resistances ignore the resistance when the attacker wields a
        magical weapon (``magical: true`` in the weapon definition).
        """
        for res in self.effective_resistances():
            # Handle "non-magical <type>" resistances
            if res.startswith('non-magical '):
                base_type = res[len('non-magical '):]
                if base_type == damage_type and not self._is_attack_magical(source, weapon):
                    return True
            elif res == damage_type:
                return True
        return False

    def _is_attack_magical(self, source=None, weapon=None):
        """Return True when the attack originates from a magical source.

        Magical weapons (``magical: true``) and spells count as magical.
        """
        if weapon is not None:
            if weapon.get('magical', False):
                return True
        if source is not None:
            # Check equipped weapons for magical property
            if hasattr(source, 'equipped_weapons') and hasattr(source, 'session'):
                for wkey in source.equipped_weapons(source.session):
                    w = source.session.load_weapon(wkey)
                    if w and w.get('magical', False):
                        return True
            # Spells are inherently magical
            if hasattr(source, 'current_spell') and source.current_spell:
                return True
        return False

    def immune_to(self, damage_type, source=None, weapon=None):
        return damage_type in self.effective_immunities()

    def effective_immunities(self):
        if self.has_effect('immunity_override'):
            return self.eval_effect('immunity_override', { "stacked": True, "value" : self.damage_immunities})
        return self.damage_immunities

    def effective_resistances(self):
        if self.has_effect('resistance_override'):
            return self.eval_effect('resistance_override', { "stacked": True, "value" : self.resistances})
        # Barbarian - Rage (5e SRD): while raging, gain resistance to
        # bludgeoning, piercing, and slashing damage.
        if getattr(self, 'is_raging', None) and self.is_raging():
            extra = ['bludgeoning', 'piercing', 'slashing']
            base = list(self.resistances or [])
            for dt in extra:
                if dt not in base:
                    base.append(dt)
            return base
        return self.resistances

    def disengage(self, battle):
        entity_state = battle.entity_state_for(self)
        if entity_state and 'disengage' in entity_state.get('statuses', []):
            return True
        return False
    
    def do_disengage(self, battle):
        entity_state = battle.entity_state_for(self)
        entity_state['statuses'].add('disengage')

    def has_reaction(self, battle):
        if not battle:
            return True

        return battle.entity_state_for(self).get('reaction', 0) > 0

    def has_action(self, battle):
        if not battle:
            return True

        return battle.entity_state_for(self).get('action', 0) > 0

    def has_bonus_action(self, battle):
        if not battle:
            return True

        return battle.entity_state_for(self).get('bonus_action', 0) > 0

    def hidden(self):
        return 'hidden' in self.statuses
    
    def unsqueeze(self):
        if 'squeezed' in self.statuses:
            self.statuses.remove('squeezed')

    def preception_check(self, battle):
        entity_state = battle.entity_state_for(self)
        if not entity_state:
            return 0

        return entity_state.get('active_perception', 0)
    
    def grapple(self, target):
        if not hasattr(self, 'grappling'):
            self.grappling = []
        self.grappling.append(target)

    def is_flying(self):
        return bool(self.flying)
    
    def fly(self):
        if self.properties.get('speed_fly'):
            self.flying = True

    def land(self):
        self.flying = False
    
    def can_fly(self):
        return self.properties.get('speed_fly')
    
    def melee_distance(self):
        return 0
    
    def entered_melee(self, map, entity, pos_x, pos_y):
        entity_1_sq = map.entity_squares(self)
        entity_2_sq = map.entity_squares_at_pos(entity, pos_x, pos_y)

        for entity_1_pos in entity_1_sq:
            for entity_2_pos in entity_2_sq:
                cur_x, cur_y = entity_1_pos
                pos_x, pos_y = entity_2_pos

                distance = math.floor(math.sqrt((cur_x - pos_x)**2 + (cur_y - pos_y)**2) * map.feet_per_grid) # one square - 5 ft

                # determine melee options
                if distance <= self.melee_distance() + 2.5:
                    return True

        return False
    
    def hand_slots_required(self, item):
        if item['type'] == 'armor':
            return 0.0
        elif item['light']:
            return 0.5
        elif item['two_handed']:
            return 2.0
        else:
            return 1.0

    def used_hand_slots(self, weapon_only=False):
        equipped_items = [item for item in self.equipped_items() if item['subtype'] == 'weapon' or (not weapon_only and item['type'] == 'shield')]
        hand_slots = sum(self.hand_slots_required(item) for item in equipped_items)

        return hand_slots
    
    def make_prone(self):
        self.do_prone()

    def make_standing(self):
        self.stand()

    def use(self, entity, result, session=None):
        raise NotImplementedError("Entity.use must be implemented by subclasses")
    
    def vulnerable_to(self, damage_type):
        return damage_type in self.damage_vulnerabilities

    def initiative_bonus(self):
        return self.dex_mod()

    def initiative(self, battle=None):
        if self.invisible():
            advantage = True
        else:
            advantage = False
        roll = DieRoll.roll_with_lucky(self, f"1d20+{self.initiative_bonus()}", description="initiative",
                                       advantage=advantage,
                                       battle=battle)
        value = float(roll.result()) + self.ability_scores.get('dex') / 100.0
        if battle:
            battle.event_manager.received_event({ "source": self,
                                     "event": "initiative",
                                     "roll": roll,
                                     "value" : value})
        else:
            self.event_manager.received_event({ "source": self,
                                        "event": "initiative",
                                        "roll": roll,
                                        "value" : value})
        return value

    def strength(self):
        _str = self.ability_scores.get('str')
        if self.has_effect('strength_override'):
          _str = self.eval_effect('strength_override', { "strength" : _str})
        return _str

    def str_mod(self):
        return self.modifier_table(self.strength())

    def con_mod(self):
        return self.modifier_table(self.ability_scores.get('con'))

    def wis_mod(self):
        return self.modifier_table(self.ability_scores.get('wis'))

    def cha_mod(self):
        return self.modifier_table(self.ability_scores.get('cha'))

    def int_mod(self):
        return self.modifier_table(self.ability_scores.get('int'))

    def dex_mod(self):
        return self.modifier_table(self.ability_scores.get('dex'))
    
    def ability_score_dex(self):
        return self.ability_scores.get('dex')
    
    def ability_score_str(self):
        return self.strength()

    def ability_score_con(self):
        return self.ability_scores.get('con')

    def ability_score_int(self):
        return self.ability_scores.get('int')

    def ability_score_wis(self):
        return self.ability_scores.get('wis')

    def ability_score_cha(self):
        return self.ability_scores.get('cha')
    
    def casted_leveled_spells(self, battle=None):
        if battle:
            return len(battle.entity_state_for(self).get('casted_level_spells', [])) > 0
        return False

    def modifier_table(self, value):
        mod_table = [[0, 1, -5],
                     [1, 1, -5],
                     [2, 3, -4],
                     [4, 5, -3],
                     [6, 7, -2],
                     [8, 9, -1],
                     [10, 11, 0],
                     [12, 13, 1],
                     [14, 15, 2],
                     [16, 17, 3],
                     [18, 19, 4],
                     [20, 21, 5],
                     [22, 23, 6],
                     [24, 25, 7],
                     [26, 27, 8],
                     [28, 29, 9],
                     [30, 30, 10]]

        for low, high, mod in mod_table:
            if value is None:
                return None
            if low <= value <= high:
                return mod
        return None
    
    def drop_concentration(self):
        if self.concentration:
            self.session.event_manager.received_event({
                    'source': self, 'event': 'concentration_end',
                    'effect': self.concentration})
            self.concentration = None

    def dismiss_effect(self, effect, opts={}):
        if opts is None:
            opts = {}
        
        if self.concentration == effect:
            self.drop_concentration()

        dismiss_count = 0
        if hasattr(effect, 'action') and effect.action and \
            hasattr(effect.action, 'target') and effect.action.target:
            if isinstance(effect.action.target,list):
                for target in effect.action.target:
                    dismiss_count += target.remove_effect(effect, opts)
            else:
                dismiss_count = effect.action.target.remove_effect(effect, opts)

        dismiss_count += self.remove_effect(effect, opts)
        return dismiss_count

    def remove_effect(self, effect, opts={}):
        def resolve_effect(effect_id):
            for f in self.casted_effects:
                if f['effect'].id == effect_id:
                    effect = f['effect']
                    return effect
            return None

        if isinstance(effect, str):
            effect = resolve_effect(effect)
            if not effect:
                return 0

        removed_effects = {}
        if hasattr(effect, 'source') and effect.source:
            for f in effect.source.casted_effects:
                if f['effect'].id == effect.id:
                    removed_effects[f['effect'].id] = f

            effect.source.casted_effects = [f for f in effect.source.casted_effects if f['effect'].id != effect.id]

        dismiss_count = 0

        new_effects = {}
        for key, value in self.effects.items():
            for f in value:
                if f['effect'].id == effect.id:
                    removed_effects[f['effect'].id] = f
                    dismiss_count += 1

            new_effects[key] = [f for f in value if f['effect'].id not in removed_effects]
        self.effects = new_effects

        new_entity_event_hooks = {}
        for key, value in self.entity_event_hooks.items():
            delete_hooks = [f for f in value if f['effect'] == effect]
            dismiss_count += len(delete_hooks)
            new_entity_event_hooks[key] = [f for f in value if f not in delete_hooks]
        self.entity_event_hooks = new_entity_event_hooks

        # call the dismiss hooks
        for f in removed_effects.values():
            if f['effect'] and hasattr(f['effect'], 'dismiss'):
                f['effect'].dismiss(self, f, opts)

        return dismiss_count

    def wearing_armor(self):
        return any(item['type'] in ['armor', 'shield'] for item in self.equipped_items())

    def has_multiattack(self):
        return self.properties.get('multiattack', None) is not None

    def reset_turn(self, battle):
        entity_state = battle.entity_state_for(self)
        if not entity_state:
            raise ValueError("entity has not been added to the battle yet")

        total_legendary_actions = 0
        if 'legendary_actions' in self.properties:
            total_legendary_actions = 3

        entity_state.update({
            'action': 1,
            'bonus_action': 1,
            'reaction': 1,
            'movement': self.speed(),
            'free_object_interaction': 1,
            'active_perception': 0,
            'active_perception_disadvantage': 0,
            'two_weapon': None,
            'martial_arts_pending': False,
            'action_surge': None,
            'multiattack_started': False,
            'casted_level_spells': [],
            'positions_entered': {},
            'legendary_actions': total_legendary_actions
        })

        self._reset_spiritual_weapon(battle)

        # clear help actions
        for _, v in self.help_actions.items():
            v.helping_with.remove(self)
        self.help_actions.clear()

        battle.dismiss_distract(self)

        if 'dodge' in entity_state['statuses']:
            entity_state['statuses'].remove('dodge')

        if 'disengage' in entity_state['statuses']:
            entity_state['statuses'].remove('disengage')

        battle.event_manager.received_event({'source': self, 'event': 'start_of_turn'})
        self.resolve_trigger('start_of_turn')
        try:
            from natural20.combat_script import process_combat_script
            process_combat_script(self, battle)
        except Exception:
            pass
        self._cleanup_effects()

        if not self.has_multiattack():
            return entity_state

        multiattack_groups = {}
        for a in self.properties["actions"]:
            if a.get("multiattack_group"):
                group = a["multiattack_group"]
                multiattack_groups.setdefault(group, []).append(a["name"])

        entity_state["multiattack"] = multiattack_groups
        entity_state["multiattack_hits"] = {}
        for a in self.properties["actions"]:
            if a.get("multiattack_group"):
                group = a["multiattack_group"]
                entity_state["multiattack_hits"][group] = {}

        return entity_state

    def _reset_spiritual_weapon(self, battle):
        if self.has_casted_effect('spiritual_weapon'):
          weapon_effect = None
          for effect in self.casted_effects:
            if effect.get('effect').id == 'spiritual_weapon':
              spiritual_weapon = effect['effect'].spiritual_weapon
              weapon_effect = effect
              break

          assert spiritual_weapon, "spiritual_weapon not found"
          assert isinstance(spiritual_weapon, Entity), "spiritual_weapon is not an Entity"

          if weapon_effect.get('expiration') and weapon_effect['expiration'] > self.session.game_time:
            spiritual_weapon.reset_turn(battle)

    def restrained(self):
        c_restrained = self.eval_effect('restrained_override', { "stacked": True, "value" : False})
        if c_restrained:
            return c_restrained
        return 'restrained' in self.statuses

    def resolve_trigger(self, event_type, opts=None) -> list:
        results = []
        if opts is None:
            opts = {}
        if event_type in self.entity_event_hooks:
            available_hooks = [effect for effect in self.entity_event_hooks[event_type] if not effect.get('expiration') or effect['expiration'] > self.session.game_time]
            if len(available_hooks) == 0:
                return []

            for active_hook in available_hooks:
                _temp_results = getattr(active_hook['handler'], active_hook['method'])(self, {**opts, 'effect': active_hook['effect']})
                if _temp_results:
                    results.extend(_temp_results)
        return results

    def update_state(self, state):
        if state == 'active':
            self.is_passive = False
        elif state == 'passive':
            self.is_passive = True
        elif state == 'prone':
            self.do_prone()
        elif state == 'unconscious':
            self.make_unconscious()
        elif state == 'conscious':
            self.make_conscious()
        elif state == 'dead':
            self.make_dead()
        elif state == 'untargettable':
            self.targettable = False


    def do_grappled_by(self, grappler):
        if not self.immune_to_condition('grappled'):
            if 'grappled' not in self.statuses:
                self.statuses.append('grappled')
            if grappler not in self.grapples:
                self.grapples.append(grappler)
            return grappler.do_grapple(self)

    def grappled_by(self, grappler) -> bool:
        if self.grappled():
            return False
        return grappler in self.grapples

    def escape_grapple_from(self, grappler):
        if grappler in self.grapples:
            self.grapples.remove(grappler)
        if len(self.grapples) == 0 and 'grappled' in self.statuses:
            self.statuses.remove('grappled')
        grappler.ungrapple(self)
        self.resolve_trigger('escape_grapple_from', {'grappler': grappler})

    def _cleanup_effects(self):
        for _, value in self.effects.items():
            delete_effects = [f for f in value if f.get('expiration') and f['expiration'] <= self.session.game_time]
            for effect in delete_effects:
                self.dismiss_effect(effect)

        self.entity_event_hooks = {k: [f for f in value if not f.get('expiration') or f['expiration'] > self.session.game_time] for k, value in self.entity_event_hooks.items()}

        delete_casted_effects = [f for f in self.casted_effects if f.get('expiration') and f['expiration'] <= self.session.game_time]
        for effect in delete_casted_effects:
            self.dismiss_effect(effect['effect'])


    # Checks if an entity still has an action available
    # @param battle [Natural20::Battle]
    def action(self, battle=None):
        if battle is None:
            return True

        entity_state = battle.entity_state_for(self)
        if entity_state is None:
            return True

        return (entity_state.get('action', 0) > 0)

    def total_actions(self, battle):
        if battle:
            entity_state = battle.entity_state_for(self)
            if not entity_state:
                return 1

            return entity_state.get('action')
        else:
            return 1

    def total_reactions(self, battle):
        if battle:
            entity_state = battle.entity_state_for(self)
            if not entity_state:
                return 1
            return entity_state.get('reaction')
        else:
            return 1

    def total_legendary_actions(self, battle):
        if battle:
            entity_state = battle.entity_state_for(self)
            if not entity_state:
                return 0
            return entity_state.get('legendary_actions')
        else:
            return 0

    def free_object_interaction(self, battle):
        if battle is None:
            return True

        entity_state = battle.entity_state_for(self)
        if entity_state is None:
            return True

        return (entity_state.get('free_object_interaction', 0) > 0)

    def total_bonus_actions(self, battle):
        if battle is None:
            return 1

        entity_state = battle.entity_state_for(self)
        if entity_state is None:
            return 1

        return entity_state.get('bonus_action')

    def available_movement(self, battle):
        if battle is None:
            return self.speed()

        if self.grappled() or self.unconscious():
            return 0

        entity_state = battle.entity_state_for(self)
        if entity_state:
            return entity_state.get('movement')
        else:
            return self.speed()

    def available_spells(self, battle, touch=False):
        return []

    def familiar(self):
      return self.properties.get('familiar', False)

    def speed(self):
        if self.restrained():
            return 0

        c_speed = self.properties.get('speed_fly',0) if self.is_flying() else self.properties['speed']

        if self.has_effect('speed_override'):
            c_speed = self.eval_effect('speed_override', { "stacked": True, "value" : c_speed})

        return c_speed
    
    def swim_speed(self):
        return self.properties.get('speed_swim', 0)
    
    def stable(self):
        return 'stable' in self.statuses
    
    def prone(self):
        return 'prone' in self.statuses

    def use_reckless_attack(self):
        self.reckless_attack_active = True

    def is_reckless(self):
        if bool(getattr(self, 'reckless_attack_active', False)):
            return True
        if self.properties.get('reckless'):
            return True
        return 'reckless' in getattr(self, 'statuses', [])
    
    def do_prone(self):
        if not self.immune_to_condition('prone'):
            if 'prone' not in self.statuses:
                self.statuses.append('prone')

    # Hides the entity in battle with a specified stealth value
    # @param battle [Natural20::Battle]
    # @param stealth [Integer]
    def do_hide(self, stealth):
        if stealth is None:
            raise ValueError("stealth cannot be None")
        if 'hidden' not in self.statuses:
            self.statuses.append('hidden')
        self.hidden_stealth = stealth

    def squeezed(self):
        return 'squeezed' in self.statuses
    
    def do_dodge(self, battle):
        entity_state = battle.entity_state_for(self)
        entity_state['statuses'].add('dodge')

    def incapacitated(self):
        return 'incapacitated' in self.statuses or 'unconscious' in self.statuses or \
            'sleep' in self.statuses or 'dead' in self.statuses

    def dodge(self, battle):
        if not battle:
            return False

        entity_state = battle.entity_state_for(self)
        if not entity_state:
            return False

        return 'dodge' in entity_state.get('statuses', [])
    
    def break_stealth(self):
        if 'hidden' in self.statuses:
            self.statuses.remove('hidden')
        self.hidden_stealth = None

    # @param map [Natural20::BattleMap]
    def push_from(self, map, pos_x, pos_y, distance=5):
        x, y = map.entity_or_object_pos(self)
        effective_token_size = self.token_size() - 1
        ofs_x, ofs_y = 0, 0

        if pos_x in range(x, x + effective_token_size + 1) and pos_y not in range(y, y + effective_token_size + 1):
            ofs_y = distance if pos_y < y else -distance
        elif pos_y in range(y, y + effective_token_size + 1) and pos_x not in range(x, x + effective_token_size + 1):
            ofs_x = distance if pos_x < x else -distance
        elif [pos_x, pos_y] == [x - 1, y - 1]:
            ofs_x = distance
            ofs_y = distance
        elif [pos_x, pos_y] == [x + effective_token_size + 1, y - 1]:
            ofs_x = -distance
            ofs_y = distance
        elif [pos_x, pos_y] == [x - 1, y + effective_token_size + 1]:
            ofs_x = distance
            ofs_y = -distance
        elif [pos_x, pos_y] == [x + effective_token_size + 1, y + effective_token_size + 1]:
            ofs_x = -distance
            ofs_y = -distance
        else:
            # Source isn't strictly adjacent (e.g. caller is reach-attacking
            # from 2 squares away, or token sizes/effects pushed the source
            # one square off the bounding ring). Fall back to a directional
            # push along the sign of the delta from the bounding box so the
            # turn doesn't crash with a 500.
            if pos_x < x:
                ofs_x = distance
            elif pos_x > x + effective_token_size:
                ofs_x = -distance
            if pos_y < y:
                ofs_y = distance
            elif pos_y > y + effective_token_size:
                ofs_y = -distance
            if ofs_x == 0 and ofs_y == 0:
                # Source overlaps target; nothing to push from.
                return x, y

        # convert to squares
        ofs_x //= map.feet_per_grid
        ofs_y //= map.feet_per_grid

        # If no movement is needed, return current position
        if ofs_x == 0 and ofs_y == 0:
            return x, y
        
        # Find the furthest valid position by stepping along the push direction
        furthest_x, furthest_y = x, y
        
        # Calculate step direction
        step_x = 1 if ofs_x > 0 else (-1 if ofs_x < 0 else 0)
        step_y = 1 if ofs_y > 0 else (-1 if ofs_y < 0 else 0)
        
        # For straight-line movement (horizontal or vertical), step one square at a time
        if ofs_x == 0:  # Pure vertical movement
            for step in range(1, abs(ofs_y) + 1):
                next_x = x
                next_y = y + step * step_y
                if map.placeable(self, next_x, next_y):
                    furthest_x, furthest_y = next_x, next_y
                else:
                    break
        elif ofs_y == 0:  # Pure horizontal movement
            for step in range(1, abs(ofs_x) + 1):
                next_x = x + step * step_x
                next_y = y
                if map.placeable(self, next_x, next_y):
                    furthest_x, furthest_y = next_x, next_y
                else:
                    break
        else:  # Diagonal movement - step along the longer axis and interpolate the shorter
            max_steps = max(abs(ofs_x), abs(ofs_y))
            for step in range(1, max_steps + 1):
                # Calculate interpolated position
                progress = step / max_steps
                next_x = x + int(ofs_x * progress)
                next_y = y + int(ofs_y * progress)
                
                if map.placeable(self, next_x, next_y):
                    furthest_x, furthest_y = next_x, next_y
                else:
                    break
        
        # If we couldn't move at all from the starting position, return current position
        # This maintains backward compatibility while allowing entities to "not move" rather than fail completely
        return furthest_x, furthest_y

    def trigger_event(self, event_name, battle, session, map, event):
        if event_name in self.event_handlers:
            callback = self.event_handlers[event_name]
            event['trigger'] = event_name
            return callback(battle, session, self, map, event)

    def npc(self):
        return False

    def has_effect(self, effect_type):
        for item in self.equipped_items():
            for effect in item.get('effect', []):
                if effect == 'protection':
                    effect_obj = ProtectionEffect(self)
                    if hasattr(effect_obj, effect_type):
                        return True

        if effect_type not in self.effects:
            return False

        if not self.effects[effect_type]:
            return False

        active_effects = [effect for effect in self.effects[effect_type] if not effect.get('expiration') or effect['expiration'] > self.session.game_time]

        return bool(active_effects)

    # @param map [Natural20::BattleMap]
    # @param target_position [Array<Integer,Integer>]
    # @param adjacent_only [Boolean] If false uses melee distance otherwise uses fixed 1 square away
    def melee_squares(self, map, target_position=None, adjacent_only=False, squeeze=False) -> List[Tuple[int, int]]:
        result = []
        if adjacent_only:
            cur_x, cur_y = target_position or map.entity_or_object_pos(self)
            entity_squares = map.entity_squares_at_pos(self, cur_x, cur_y, squeeze)
            for sq in entity_squares:
                for x_off in range(-1, 2):
                    for y_off in range(-1, 2):
                        if x_off == 0 and y_off == 0:
                            continue

                        # adjust melee position based on token size
                        adjusted_x_off = x_off
                        adjusted_y_off = y_off

                        position = (sq[0] + adjusted_x_off, sq[1] + adjusted_y_off)

                        if (position in entity_squares) or (position in result) or (position[0] < 0) or (position[0] >= map.size[0]) or (position[1] < 0) or (position[1] >= map.size[1]):
                            continue

                        result.append(position)
        else:
            melee_distance = self.melee_distance()
            if melee_distance is None or melee_distance <= 0:
                # Entities with no melee attack still interact with adjacent squares.
                melee_distance = 5
            feet_per_grid = map.feet_per_grid if map.feet_per_grid and map.feet_per_grid > 0 else 5
            step = max(1, int(melee_distance // feet_per_grid))
            cur_x, cur_y = target_position or map.entity_or_object_pos(self)
            for x_off in range(-step, step+1):
                for y_off in range(-step, step+1):
                    if x_off == 0 and y_off == 0:
                        continue

                    # adjust melee position based on token size
                    adjusted_x_off = x_off
                    adjusted_y_off = y_off

                    if x_off < 0:
                        adjusted_x_off -= self.token_size() - 1
                    if y_off < 0:
                        adjusted_y_off -= self.token_size() - 1

                    position = (cur_x + adjusted_x_off, cur_y + adjusted_y_off)

                    if (position[0] < 0) or (position[0] >= map.size[0]) or (position[1] < 0) or (position[1] >= map.size[1]):
                        continue

                    result.append(position)
        return result
    
    # Retrieves the item count of an item in the entity's inventory
    # @param inventory_type [str]
    # @return [int]
    def item_count(self, inventory_type):
        if self.inventory is None:
            return 0

        if inventory_type not in self.inventory:
            return 0
        return self.inventory[inventory_type]['qty']
    
    def attack_roll_mod(self, weapon):
        modifier = self.attack_ability_mod(weapon)

        if self.proficient_with_weapon(weapon):
            modifier += self.proficiency_bonus()

        # Magic weapon bonus to attack rolls
        magic_bonus = weapon.get('magic_bonus', 0)
        if magic_bonus:
            modifier += magic_bonus

        return modifier


    def attack_ability_mod(self, weapon):
        modifier = 0

        if weapon['type'] == 'melee_attack':
            weapon_properties = weapon.get('properties', [])
            if weapon_properties is None:
                weapon_properties = []
            # Monk - Martial Arts: may use DEX in place of STR for monk
            # weapons and unarmed strikes (5e SRD).
            if (
                getattr(self, 'class_feature', None)
                and self.class_feature('martial_arts')
                and getattr(self, 'is_monk_weapon', None)
                and self.is_monk_weapon(weapon)
            ):
                modifier = max(self.str_mod(), self.dex_mod())
            elif 'finesse' in weapon_properties:
                modifier = max(self.str_mod(), self.dex_mod())
            else:
                modifier = self.str_mod()
        elif weapon['type'] == 'ranged_attack':
            if self.class_feature('archery'):
                modifier = self.dex_mod() + 2
            else:
                modifier = self.dex_mod()

        return modifier

    def proficient_with_weapon(self, weapon):
        if isinstance(weapon, str):
            weapon = self.session.load_thing(weapon)

        if weapon['name'] == 'Unarmed Attack':
            return True

        proficiency_types = self.properties.get('weapon_proficiencies', [])
        for prof in proficiency_types:
            if weapon['proficiency_type'] and (prof in weapon['proficiency_type'] or prof == weapon['name'].replace(" ", "_")):
                return True

        return False

    def equipped_weapons(self, session, valid_weapon_types=['ranged_attack', 'melee_attack']):
        weapon_attacks = []
        for item in self.properties.get('equipped', []):
            weapon_detail = session.load_weapon(item)
            if weapon_detail is None:
                continue
            if weapon_detail['type'] not in valid_weapon_types:
                continue
            if 'ammo' in weapon_detail and not self.item_count(weapon_detail['ammo']) > 0:
                continue
            weapon_attacks.append(item)

        return weapon_attacks

    def equipped_items(self):
        equipped_arr = self.properties.get('equipped', [])
        equipped_list = []
        for k in equipped_arr:
            item = self.session.load_thing(k)
            if not item:
                raise Exception(f"unknown item {k}")
            equipped_list.append(self._to_item(k, item))

        return equipped_list
    
    def unequipped_items(self):
        inventory = self.inventory
        unequipped_list = []
        for k in inventory.keys():
            item = self.session.load_thing(k)
            if not item.get('equippable', False):
                continue

            if not item:
                raise Exception(f"unknown item {k}")
            item_info = self._to_item(k, item)
            item_info['qty'] = inventory[k]['qty']
            unequipped_list.append(item_info)

        return unequipped_list
    
    def equipped_armor(self):
        return [item for item in self.equipped_items() if item['type'] in ['armor', 'shield']]
    
    def equipped_metallic_armor(self):
        return [item for item in self.equipped_items() if item['type'] == 'armor' and item['metallic']]
    
    def is_familiar(self):
        return self.properties.get('familiar')

    def proficient_with_equipped_armor(self):
        shields_and_armor = self.equipped_armor()
        if len(shields_and_armor) == 0:
            return True

        for item in shields_and_armor:
            if not self.proficient_with_armor(item['name']):
                print(f"not proficient with {item['name']}")
                return False

        return True

    def save_throw(self, save_type, battle=None, opts=None):
        """
        Perform a saving throw for the entity
        """
        if opts is None:
            opts = {}

        modifier = self.ability_mod(save_type)
        if modifier is None:
            raise ValueError(f"invalid ability {save_type}")

        modifier += self.proficiency_bonus() if self.proficient(f"{save_type}_save") else 0
        op = '+' if modifier >= 0 else ''

        advantages = []
        disadvantages = []

        if save_type in ['dexterity', 'strength'] and not self.proficient_with_equipped_armor():
            disadvantages.append('armor_proficiency_missing')

        if self.restrained() and save_type == 'dexterity':
            disadvantages.append('restrained')

        if opts.get('is_magical', False):
            if save_type in ['intelligence', 'wisdom', 'charisma'] and self.class_feature('gnome_cunning'):
                advantages.append('gnome_cunning')

        frightened_check = False
        if opts.get('condition') == 'frightened' or opts.get('saving_throw_type') == 'frightened':
            frightened_check = True
        conditions = opts.get('conditions')
        if isinstance(conditions, (list, tuple)) and 'frightened' in conditions:
            frightened_check = True
        if frightened_check and self.class_feature('fearless'):
            advantages.append('fearless')

        has_advantage = len(advantages) > 0
        has_disadvantage = len(disadvantages) > 0
        advantage_str = ",".join(advantages) if len(advantages) > 0 else ""
        disadvantage_str = ",".join(disadvantages) if len(disadvantages) > 0 else ""
        save_roll = DieRoll.roll(f"d20{op}{modifier}", advantage=has_advantage, disadvantage=has_disadvantage, battle=battle, entity=self,
                            description=f"dice_roll.{save_type}_saving_throw", advantage_str=advantage_str, disadvantage_str=disadvantage_str)

        if self.has_effect('saving_throw_override'):
            save_roll = self.eval_effect('saving_throw_override', { 'save_roll' : save_roll })

        if self.has_effect('bless'):
            save_roll += DieRoll.roll("1d4", description="bless", entity=self, battle=battle)

        if self.has_effect('bane'):
            bane_pen = DieRoll.roll("1d4", description="bane", entity=self, battle=battle)
            save_roll += DieRoll.roll("-" + str(bane_pen.result()), entity=self, battle=battle)

        # Generic, additive modifier hook for new effects (Bardic Inspiration,
        # Bless variants, paladin auras, etc.). Effects register against
        # 'save_modifier' and may return either a numeric bonus or a
        # ``DieRoll`` to add to the roll. The hook is consulted last so it
        # composes with the legacy bless/bane handling above without
        # changing behavior for entities that have no such effect.
        if self.has_effect('save_modifier'):
            mod = self.eval_effect('save_modifier', {
                'stacked': True, 'value': 0,
                'ability': save_type, 'battle': battle,
            })
            if mod:
                if hasattr(mod, 'result'):
                    save_roll += mod
                else:
                    sign = '+' if int(mod) >= 0 else ''
                    save_roll += DieRoll.roll(f"{sign}{int(mod)}",
                                              description="save_modifier",
                                              entity=self, battle=battle)

        # Phase 3 modifier registry: any effect that registered a
        # ``save_roll`` modifier (Bardic Inspiration, paladin auras, etc.)
        # contributes here. ``value`` may be an int or a dice string.
        registry_mods = self.collect_modifiers('save_roll', {
            'ability': save_type, 'battle': battle,
        })
        for entry in registry_mods:
            v = entry['value']
            if isinstance(v, str) and v:
                save_roll += DieRoll.roll(v, description=f"save_modifier:{entry.get('source')}",
                                          entity=self, battle=battle)
            else:
                try:
                    iv = int(v)
                except Exception:
                    continue
                if iv == 0:
                    continue
                sign = '+' if iv >= 0 else ''
                save_roll += DieRoll.roll(f"{sign}{iv}",
                                          description=f"save_modifier:{entry.get('source')}",
                                          entity=self, battle=battle)

        return save_roll

    def skills(self):
        return self.properties.get('skills', [])
    
    def proficient(self, prof):
        return (prof in self.properties.get('skills', []) or
                prof in self.properties.get('tools', []) or
                prof in self.properties.get('weapon_proficiencies', []) or
                prof in [f"{p}_save" for p in self.properties.get('saving_throw_proficiencies', [])])

    def proficient_with_armor(self, item):
        armor = self.session.load_thing(item)
        if not armor:
            raise Exception(f"unknown item {item}")
        if armor['type'] not in ['armor', 'shield']:
            raise Exception(f"not armor {item}")

        if armor['type'] == 'armor':
            return self.proficient(f"{armor['subtype']}_armor")
        
        elif armor['type'] == 'shield':
            return self.proficient('shields')

        return False

    def _to_item(self, k, item):
        return {
            'name': k,
            'ac' : item.get('ac', None),
            'description': item.get('description', None),
            'bonus_ac' : item.get('bonus_ac', None),
            'damage' : item.get('damage', None),
            'damage_2' : item.get('damage_2', None),
            'damage_type' : item.get('damage_type', None),
            'range' : item.get('range', None),
            'range_max' : item.get('range_max', None),
            'label': item.get('label', str(item.get('name')).capitalize()),
            'image': item.get('image', k),
            'type': item.get('type'),
            'subtype': item.get('subtype'),
            'light': item.get('properties') and 'light' in item.get('properties', []),
            'two_handed': item.get('properties') and 'two_handed' in item.get('properties', []),
            'light_properties': item.get('light'),
            'proficiency_type': item.get('proficiency_type'),
            'metallic': bool(item.get('metallic')),
            'properties': item.get('properties'),
            'effect': item.get('effect', []),
            'qty': 1,
            'equipped': True,
            'weight': item.get('weight')
        }
    # Removes Item from inventory
    # @param ammo_type [str]
    # @param amount [int]
    # @return [dict]
    def deduct_item(self, ammo_type, amount=1):
        if ammo_type not in self.inventory:
            return None

        qty = self.inventory[ammo_type]['qty']
        self.inventory[ammo_type]['qty'] = max(qty - amount, 0)
        if self.inventory[ammo_type]['qty'] == 0:
            return self.inventory.pop(ammo_type)
        return self.inventory[ammo_type]
    
    # Removes an item from the inventory
    # @param ammo_type [Symbol,String]
    # @param amount [Integer]
    # @return [Hash]
    def remove_item(self, ammo_type, amount=1):
        return self.deduct_item(ammo_type, amount)


    # Adds an item to your inventory
    # @param ammo_type [Symbol,String]
    # @param amount [Integer]
    # @param source_item [Object]
    def add_item(self, ammo_type, amount=1, source_item=None):
        if ammo_type not in self.inventory:
            self.inventory[ammo_type] = {
                'qty': 0,
                'type': source_item.type if source_item else ammo_type
            }
            # Preserve container contents if source_item is a container
            if source_item and isinstance(source_item, dict) and 'contents' in source_item:
                self.inventory[ammo_type]['contents'] = source_item['contents'].copy()

        qty = self.inventory[ammo_type].get('qty', 1)
        self.inventory[ammo_type]['qty'] = qty + amount

    def ranged_spell_attack(self, battle, spell, advantage=False, disadvantage=False):
        spell_classes = spell.get('spell_list_classes', [])
        class_types = spell_classes if spell_classes else ['wizard']
        attack_modifers = [self.spell_attack_modifier(class_type=class_type.lower()) for class_type in class_types]
        return DieRoll.roll(f"1d20+{max(attack_modifers)}", description=f"Ranged Spell Attack: {spell['name']}", entity=self, battle=battle, advantage=advantage, disadvantage=disadvantage)

    def melee_spell_attack(self, battle, spell, advantage=False, disadvantage=False):
        spell_classes = spell.get('spell_list_classes', [])
        class_types = spell_classes if spell_classes else ['wizard']
        attack_modifers = [self.spell_attack_modifier(class_type=class_type.lower()) for class_type in class_types]
        return DieRoll.roll(f"1d20+{max(attack_modifers)}", description=f"Melee Spell Attack: {spell['name']}", entity=self, battle=battle, advantage=advantage, disadvantage=disadvantage)

    def multiattack(self, battle, npc_action):
        if not npc_action:
            return False
        if not self.has_multiattack():
            return False

        entity_state = battle.entity_state_for(self)

        if not entity_state.get("multiattack", False):
            return False

        if not npc_action.get("multiattack_group", False):
            return False

        for _, attacks in entity_state["multiattack"].items():
            if npc_action["name"] in attacks:
                return True

        return False

    # Unequips a weapon
    # @param item_name [String,Symbol]
    # @param transfer_inventory [Boolean] Add this item to the inventory?
    def unequip(self, item_name, transfer_inventory=True):
        if item_name in self.properties['equipped']:
            self.properties['equipped'].remove(item_name)
            if transfer_inventory:
                self.add_item(item_name)

    def spell_save_dc(self, ability_type='intelligence'):
        return 8 + self.proficiency_bonus() + self.ability_mod(ability_type)

    def spell_attack_modifier(self, class_type='wizard'):
        method_name = f"{class_type.lower()}_spell_attack_modifier"
        if hasattr(self, method_name):
            return getattr(self, method_name)()

        return 0
    
    def health_percent(self):
        return int((self.hp() / self.properties['max_hp']) * 100)

    # Returns the available spells for the current user
    # @param battle [Natural20::Battle]
    # @return [Dict]
    def spell_list(self, battle, touch=False):
        prepared_spells = self.prepared_spells()
        spell_list = {}
        for spell in prepared_spells:
            details = self.session.load_spell(spell)
            if not details:
                continue

            if touch:
                if not details.get('range', None) == 5:
                    continue

            qty, resource = details['casting_time'].split(':')

            disable_reason = []
            if resource == 'action' and battle and battle.ongoing() and self.total_actions(battle) == 0:
                disable_reason.append('no_action')
            if resource == 'reaction':
                disable_reason.append('reaction_only')

            if resource == 'bonus_action' and battle and battle.ongoing() and self.total_bonus_actions(battle) == 0:
                disable_reason.append('no_bonus_action')
            elif resource == 'hour' and battle and battle.ongoing():
                disable_reason.append('in_battle')
            if details['level'] > 0:
                slot_available = False
                for spell_class_type in details.get('spell_list_classes', []):
                    class_key = spell_class_type.lower()
                    if hasattr(self, 'next_spell_slot_level'):
                        next_slot = self.next_spell_slot_level(class_key, details['level'])
                        if next_slot is not None:
                            slot_available = True
                            break
                    else:
                        if self.spell_slots_count(details['level'], class_key) > 0:
                            slot_available = True
                            break

                if not slot_available:
                    disable_reason.append('no_spell_slot')

            spell_list[spell] = details.copy()
            spell_list[spell]['disabled'] = disable_reason

        return spell_list
    
    def allow_targeting(self):
        return self.targettable and not self.properties.get('spiritual', False)
    
    def allow_talk(self):
        return len(self.languages()) > 0

    def equipped_npc_weapons(self, session=None):
        return [item['name'] for item in self.equipped_items() if item["subtype"] == 'weapon']

    def take_damage(self, dmg: int, battle=None, damage_type='piercing', \
                    session=None, item=None,
                    critical=False, roll_info=None, sneak_attack=None):
        if session is None:
            if battle and battle.session:
                session = battle.session
            else:
                session = self.session

        if self.class_feature("lightning_absorption") and damage_type == 'lightning':
            self.session.event_manager.received_event({
                'source': self, 'event': 'damage_absorption',
                'damage': dmg,
                'damage_type': damage_type})
            self.heal(dmg)
            return

        if self.immune_to(damage_type):
            self.session.event_manager.received_event({
                'source': self, 'event': 'damage_immunity',
                'damage_type': damage_type})
            return

        # Extract source and weapon from item context for magical attack checks
        _source = item.get('source') if item else None
        _weapon = item.get('weapon') if item else None
        resistant = self.resistant_to(damage_type, source=_source, weapon=_weapon)
        vulnerable = self.vulnerable_to(damage_type)

        # D&D 5e (2014): resistance and vulnerability cancel out.
        if resistant and vulnerable:
            total_damage = dmg
        elif resistant:
            total_damage = int(dmg // 2)
        elif vulnerable:
            total_damage = dmg * 2
        else:
            total_damage = dmg
        damage_threshold_active = False
        temp_hp_before = self._temp_hp
        temp_hp_source = self._temp_hp_source

        if total_damage < self.damage_threshold():
            total_damage = 0
            damage_threshold_active = True

        effective_damage = total_damage
        attacker = item.get('source') if item else None
        should_trigger_damage = dmg > 0 and (effective_damage > 0 or temp_hp_before > 0)

        if should_trigger_damage:
            damage_opts = {
                'dmg': effective_damage,
                'damage_type': damage_type,
                'raw_damage': dmg,
                'battle': battle,
                'item': item,
                'attacker': attacker,
                'temp_hp_before': temp_hp_before
            }
            self.resolve_trigger('damage', damage_opts)

        temp_hp_absorbed = 0
        if effective_damage > 0 and temp_hp_before > 0:
            temp_hp_absorbed = min(effective_damage, temp_hp_before)
            total_damage = max(0, total_damage - temp_hp_absorbed)
            self._temp_hp = max(0, self._temp_hp - temp_hp_absorbed)
            if self._temp_hp == 0 and temp_hp_before > 0:
                depletion_opts = {
                    'battle': battle,
                    'item': item,
                    'attacker': attacker,
                    'effect': temp_hp_source
                }
                self.resolve_trigger('temp_hp_depleted', depletion_opts)
                self.clear_temp_hp(effect=temp_hp_source)

        self.attributes["hp"] -= total_damage
        instant_death = False

        # Half-Orc Relentless Endurance: when reduced to 0 HP but not killed
        # outright, drop to 1 HP instead. Once per long rest.
        if (self.hp() <= 0
                and total_damage > 0
                and not self.unconscious()
                and not (self.hp() < 0 and abs(self.hp()) >= self.properties.get('max_hp', 0))
                and self.class_feature('relentless_endurance')
                and not getattr(self, 'relentless_endurance_used', False)):
            self.attributes['hp'] = 1
            self.relentless_endurance_used = True
            session.event_manager.received_event({
                'source': self,
                'event': 'relentless_endurance',
            })

        if self.unconscious():
            if 'stable' in self.statuses:
                self.statuses.remove('stable')
            self.death_fails += 2 if critical else 1

            complete = False
            if self.death_fails >= 3:
                complete = True
                self.make_dead()
                self.death_saves = 0
                self.death_fails = 0
            if battle:
                session.event_manager.received_event({'source': self, 'event': 'death_fail', 'saves': self.death_saves,
                                                    'fails': self.death_fails, 'complete': complete})

        if self.hp() < 0 and abs(self.hp()) >= self.properties['max_hp']:
            instant_death = True
            self.make_dead(battle=battle)

        elif self.hp() <= 0:
            self.make_dead(battle=battle) if self.npc() or self.object() else self.make_unconscious()
            # drop concentration spells
            if self.concentration:
                self.dismiss_effect(self.concentration)

        elif self.hp() > 0:
            if self.concentration:
                # make a concentration check
                concentration_check = self.save_throw('constitution', battle)
                # Concentration DC is based on damage actually taken.
                diffculty_class = max([10, total_damage // 2])
                if concentration_check.result() < diffculty_class:
                    session.event_manager.received_event({'source': self,
                                                       'event': 'concentration_check',
                                                       'result': 'failure',
                                                       'effect' : self.concentration,
                                                       'roll': concentration_check,
                                                       'dc': diffculty_class
                                        })
                    self.dismiss_effect(self.concentration)
                else:
                    session.event_manager.received_event({'source': self,
                                                       'event': 'concentration_check',
                                                       'result': 'success',
                                                       'effect' : self.concentration,
                                                       'roll': concentration_check,
                                                       'dc': diffculty_class
                                        })

        if self.hp() <= 0:
            self.attributes["hp"] = 0

        session.event_manager.received_event({'source': self, 'event': 'damage', 'total_damage': total_damage, 'damage_threshold_active': damage_threshold_active, 'value': dmg, 'damage_type': damage_type, 'roll_info': roll_info, 'instant_death': instant_death, 'sneak_attack': sneak_attack, 'temp_hp_absorbed': temp_hp_absorbed})

        if battle and item and total_damage > 0:
            self.on_take_damage(battle, item)

        # Damage-triggered reaction spells (e.g. Hellish Rebuke).
        # Fire only when the target is still able to react and the source is
        # not the spell's own follow-up damage.
        if (battle is not None
                and total_damage > 0
                and self.conscious()
                and attacker is not None
                and attacker is not self
                and not (item and item.get('source_spell') == 'hellish_rebuke')):
            try:
                from natural20.utils.attack_util import after_take_damage_hook
                after_take_damage_hook(battle, self, attacker, item or {})
            except Exception:
                # Reaction-trigger failures must never break the main damage flow.
                pass

    def on_take_damage(self, battle, _damage_params):
        controller = battle.controller_for(self)
        if controller and hasattr(controller, 'attack_listener'):
            controller.attack_listener(battle, self)

    def current_effects(self):
        active_effects = []
        for _, value in self.effects.items():
            for effect in value:
                if not effect.get('expiration') or effect['expiration'] > self.session.game_time:
                    active_effects.append(effect)
        return active_effects

    def eval_effect(self, effect_type, opts=None):
        if not opts:
            opts = {}

        if not self.has_effect(effect_type):
            return None

        if effect_type in self.effects:
            active_effects = [effect for effect in self.effects[effect_type] if not effect.get('expiration') or effect['expiration'] > self.session.game_time]
        else:
            active_effects = []

        if not opts.get('stacked'):
            active_effects = [active_effects[-1]] if active_effects else []

        result = None
        if active_effects:
            result = opts.get('value')
            for active_effect in active_effects:
                opts.update( { "effect": active_effect['effect'], "value" : result })
                result = getattr(active_effect['handler'], active_effect['method'])(self, opts)

        for item in self.equipped_items():
            for effect in item.get('effect', []):
                if effect == 'protection':
                    effect_obj = ProtectionEffect(self)
                if hasattr(effect_obj, effect_type):
                    result = getattr(effect_obj, effect_type)(self, opts)

        return result
    
    def make_stable(self):
        if 'stable' not in self.statuses:
            self.statuses.append("stable")
        self.death_fails = 0
        self.death_saves = 0

    def make_conscious(self):
        if 'unconscious' in self.statuses:
            self.statuses.remove("unconscious")
        if 'stable' in self.statuses:
            self.statuses.remove("stable")

    def heal(self, original_amt):
        if self.dead():
            return

        amt = original_amt
        if self.has_effect("heal_override"):
            amt = self.eval_effect("heal_override", {"heal": original_amt})

        if (amt < original_amt):
            self.event_manager.received_event({'source': self, 'event': 'negative_heal', 'previous': original_amt, 'new': amt, 'value': amt})
        prev_hp = self.hp()

        self.attributes["hp"] = min(self.max_hp(), self.hp() + amt)

        if self.hp() > 0 and amt > 0:
            self.death_saves = 0
            self.death_fails = 0
            if self.unconscious():
                print(f"{self.name} is now conscious because of healing and has {self.hp()} hp")
                self.make_conscious()
            self.event_manager.received_event({'source': self, 'event': 'heal', 'previous': prev_hp, 'new': self.hp, 'value': amt})


    def light_properties(self):
        bright = [0]
        dim = [0]

        for item in (self.equipped_items() or []):
            if not item.get('light_properties'):
                continue

            bright.append(item['light_properties'].get('bright', 0))
            dim.append(item['light_properties'].get('dim', 0))

        bright = max(bright)
        dim = max(dim)

        # check for light overrides
        light_override = self.eval_effect('light_override', {
            'bright': bright,
            'dim': dim
        })

        if light_override:
            bright = light_override.get('bright', bright)
            dim = light_override.get('dim', dim)

        if dim <= 0 and bright <= 0:
            return None

        return {'dim': dim, 'bright': bright}
    
    def death_saving_throw(self, battle=None):
        roll = DieRoll.roll_with_lucky(self, '1d20', description='dice_roll.death_saving_throw', battle=battle)
        if roll.nat_20():
            self.make_conscious()
            self.heal(1)
            # print(f"{self.name} rolled a natural 20 on a death saving throw and is now conscious with 1 hp")
            self.event_manager.received_event({'source': self, 'event': 'death_save', 'roll': roll, 'saves': self.death_saves,
                                                    'fails': self.death_fails, 'complete': True, 'stable': True, 'success': True})
        elif roll.result() >= 10:
            self.death_saves += 1
            complete = False
            # print(f"{self.name} succeeded a death saving throw ({self.death_saves}/3)")
            if self.death_saves >= 3:
                complete = True
                self.death_saves = 0
                self.death_fails = 0
                self.make_stable()
                # print(f"{self.name} is now stable")
            self.event_manager.received_event({'source': self, 'event': 'death_save', 'roll': roll, 'saves': self.death_saves,
                                                    'fails': self.death_fails, 'complete': complete, 'stable': complete})
        else:
            if roll.nat_1():
                # print(f"{self.name} rolled a natural 1 on a death saving throw :(")
                self.death_fails += 2 
            else:
                self.death_fails += 1

            complete = False
            if self.death_fails >= 3:
                complete = True
                self.make_dead()
                self.death_saves = 0
                self.death_fails = 0
                # print(f"{self.name} failed the final death saving throw and died")

            self.event_manager.received_event({'source': self, 'event': 'death_fail', 'roll': roll, 'saves': self.death_saves,
                                                   'fails': self.death_fails, 'complete': complete})


    def attach_handler(self, event_name, callback):
        self.event_handlers[event_name] = callback

    def usable_items(self):
        usable = []

        for k, v in self.inventory.items():
            item_details = self.session.load_equipment(k)

            if not item_details or not item_details.get('usable', False):
                continue
            if item_details['consumable'] and v['qty'] == 0:
                continue

            usable.append({
                'name': str(k),
                'label': item_details.get('label', str(k)),
                'image': item_details.get('image', k),
                'item': item_details,
                'qty': v['qty'],
                'consumable': item_details['consumable']
            })
        return usable

    def other_items(self):
        other = []
        for k, v in self.inventory.items():
            item_details = self.session.load_equipment(k)
            if not item_details or item_details.get('usable', False):
                continue
            other.append({
                'name': str(k),
                'label': item_details.get('label', item_details.get('name', k)),
                'item': item_details,
                'image': item_details.get('image', k),
                'type': item_details.get('type', 'other'),
                'qty': v['qty']
            })
        return other

    def read_item(self, item_name):
        item = self.session.load_thing(item_name)
        if not item:
            return None
        if item.get('events'):
            for event in item['events']:
                if event['event'] == 'read':
                    generic_handler = GenericEventHandler(self.session, None, event)
                    generic_handler.handle(self)
        return item, item.get('content', None)

    def has_spells(self):
        if not self.properties.get('prepared_spells', None):
            return False
        return len(self.properties['prepared_spells']) > 0

    def has_item(self, item_name):
        if self.inventory and item_name in self.inventory:
            return True
        if item_name in self.equipped_items():
            return True
        return False

    # Returns items in the "backpack" of the entity
    # @return [List]
    def inventory_items(self, session):
        items = []
        for k, v in self.inventory.items():
            item = session.load_thing(k)
            if item is None:
                raise Exception(f"unable to load unknown item {k}")
            if v['qty'] > 0:
                items.append({
                    'name': k,
                    'label': v['label'] if v.get('label',None) else str(k),
                    'qty': v['qty'],
                    'image': item.get('image', k),
                    'equipped': False,
                    'weight': item.get('weight', None)
                })
        return items
    
    # Returns the weight of all items in the inventory in lbs
    # @return [float] weight in lbs
    def inventory_weight(self, session):
        total_weight = 0.0
        for item in self.inventory_items(session) + self.equipped_items():
            weight = float(item['weight']) if item.get('weight', None) else 0.0
            total_weight += weight * item['qty']
        return total_weight
    
    def dexterity_check(self, bonus=0, battle=None, description=None):
        disadvantage = not self.proficient_with_equipped_armor() if battle is None else False
        if self.poisoned():
            disadvantage = True
        roll = DieRoll.roll_with_lucky(
            self,
            f"1d20+{self.dex_mod() + bonus}",
            disadvantage=disadvantage,
            description=description or 'dice_roll.dexterity',
            battle=battle
        )
        roll.metadata['ability'] = 'dexterity'
        roll.metadata['is_ability_check'] = True
        return roll

    def perception_proficient(self):
        return self.proficient('perception')

    def investigation_proficient(self):
        return self.proficient('investigation')

    def insight_proficient(self):
        return self.proficient('insight')

    def stealth_proficient(self):
        return self.proficient('stealth')

    def acrobatics_proficient(self):
        return self.proficient('acrobatics')

    def athletics_proficient(self):
        return self.proficient('athletics')

    def medicine_proficient(self):
        return self.proficient('medicine')
    
    # removes all equipped. Used for tests
    def unequip_all(self):
        self.properties['equipped'].clear()

    # Checks if item can be equipped
    # @param item_name [String,Symbol]
    # @return [str]
    def check_equip(self, item_name):
        weapon = self.session.load_thing(item_name)
        if weapon and weapon.get('subtype') == 'weapon' or weapon['type'] in ['shield', 'armor'] or weapon.get('equippable', False):
            hand_slots = self.used_hand_slots() + self.hand_slots_required(self._to_item(item_name, weapon))
            armor_slots = len([item for item in self.equipped_items() if item['type'] == 'armor'])
            if hand_slots > 2.0:
                return 'hands_full'
            elif armor_slots >= 1 and weapon['type'] == 'armor':
                return 'armor_equipped'
            else:
                return 'ok'
        else:
            return 'unequippable'
  
    # Returns the carrying capacity of an entity in lbs
    # @return [float] carrying capacity in lbs
    def carry_capacity(self):
        return self.ability_scores.get('str', 1) * 15.0

    def to_dict(self):
        return {
            'name': self.name,
            'properties': self.properties,
            'attributes': self.attributes,
            'inventory': self.inventory,
            'effects': self.effects,
            'status': self.statuses,
            'death_saves': self.death_saves,
            'death_fails': self.death_fails,
            'concentration': self.concentration,
            'casted_effects': self.casted_effects,
            'grapples': self.grapples,
            'temp_hp' : self._temp_hp,
            'group' : self.group,
            'activated' : self.activated,
            'help_actions': self.help_actions,
            'helping_with': list(self.helping_with),
            'resources': {name: pool.to_dict() for name, pool in (getattr(self, 'resources', None) or {}).items()},
        }

    def long_rest(self, battle=None, battle_map=None, force=False, require_rations=False):
        """Take a long rest.

        Restrictions (waived when ``force=True``):

        * Combat must not be in progress.
        * No hostile creature may be within :pyattr:`REST_HOSTILE_RADIUS_FT`.
        * The current map and/or campaign must not opt out of long rests via
          ``allow_long_rest: false`` on the map properties or game.yml.
        * When ``require_rations=True`` the entity must have at least one
          ``rations`` item in its inventory; the ration is consumed.

        ``require_rations`` defaults to ``False`` so that legacy programmatic
        callers (and unit tests that do not stage rations) are unaffected;
        the web layer opts in.
        """
        resolved_map = self._resolve_rest_map(battle_map)
        if not force:
            self._check_rest_preconditions(battle, resolved_map, 'long')
            self._check_long_rest_location(resolved_map)
            if require_rations:
                self._consume_long_rest_rations()
        self.attributes['hp'] = self.properties['max_hp']
        self.death_saves = 0
        self.death_fails = 0
        self.statuses.clear()
        self.casted_effects.clear()
        self.grapples.clear()
        self.drop_concentration()
        self._temp_hp = 0
        # Half-Orc Relentless Endurance recharges on a long rest.
        if hasattr(self, 'relentless_endurance_used'):
            self.relentless_endurance_used = False
        # Tabaxi Feline Agility recharges on a long rest as a fallback.
        if hasattr(self, 'feline_agility_used'):
            self.feline_agility_used = False
        # Reset breath weapon usage on long rest (Dragonborn racial trait)
        if hasattr(self, 'breath_weapon_used'):
            self.breath_weapon_used = False

        # Recover spent hit dice: floor(level/2), minimum 1, capped at max
        # per die type.  PCs track per-class hit-die maxima; NPCs use a
        # single npc_type bucket (max stored on _max_hit_die).
        max_hit_die = getattr(self, 'max_hit_die', None) or getattr(self, '_max_hit_die', None) or {}
        total_max = sum(max_hit_die.values()) if max_hit_die else 0
        if total_max > 0:
            recover = max(1, total_max // 2)
            for die_type in sorted(self._current_hit_die.keys()):
                if recover <= 0:
                    break
                # Compute the per-die-type max.  PCs key max_hit_die by class
                # name and we don't have a class->die mapping here, so cap at
                # total_max which is always >= per-die-type count.
                current = self._current_hit_die.get(die_type, 0)
                room = total_max - current
                if room <= 0:
                    continue
                grant = min(recover, room)
                self._current_hit_die[die_type] = current + grant
                recover -= grant

        # Per-class long-rest hooks (paladin lay on hands pool, etc.).
        for klass in self._iter_class_names():
            hook = getattr(self, f"long_rest_for_{klass}", None)
            if callable(hook):
                hook(None)

        self.restore_resources('long_rest')
        self.resolve_trigger('long_rest')
        self.event_manager.received_event({'source': self, 'event': 'long_rest'})

    def t(self, key, **kwargs):
        return self.session.t(key, kwargs)

    def has_help(self):
        """Check if the entity has any help actions available"""
        return len(self.help_actions) > 0