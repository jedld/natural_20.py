# Add spell — reference

## File touchpoints

| Layer | Path | What to add |
|-------|------|-------------|
| YAML | `templates/items/spells.yml` | SRD text, `level`, `upcast` (when slot level changes effect), `range`, `school`, `type`, `concentration`, `duration_seconds`, `spell_class`, `spell_list_classes` |
| Class lists | `templates/char_classes/<class>.yml` | Entry under `spell_list` for appropriate level |
| Python | `natural20/spell/<slug>_spell.py` | `Spell` subclass |
| Loader | `natural20/utils/spell_loader.py` | `import` + `'FooSpell': FooSpell` in `spell_classes` |
| Tests | `tests/test_<slug>_spell.py` | Engine behavior |
| Effect icon | `webapp/static/assets/effect/<slug>.png` | 64×64-ish; shown on map tile via `JsonRenderer` → `effects: [str(effect)]` — slug must match `Effect.__str__()` (see `scripts/audit_effect_assets.py`) |
| Cast FX | `webapp/static/spell_effects.js` | `register('<slug>', renderer)` — key must match `spell_action.short_name()` |
| Persistent FX | `webapp/static/status_effects.js` | `EFFECT_CLASS`, CSS class, optional extra overlay layer |
| Minify | `npm run build:assets` | After editing `spell_effects.js` or `status_effects.js` |

Campaign-only spell YAML: `user_levels/<campaign>/items/spells.yml` merges with templates (see `docs/CAMPAIGN_BUILDING.md`).

## YAML skeleton

```yaml
hold_person:
  label: Hold Person
  casting_time: 1:action
  components:
    - verbal
    - somatic
    - material
  material: a small, straight piece of iron
  description: |
    Full SRD text including upcast paragraph.
  duration: 1m
  duration_seconds: 60
  level: 2
  upcast: true
  name: Hold Person
  range: 60
  school: enchantment
  concentration: true
  type: control
  spell_list_classes: [Bard, Cleric, Sorcerer, Warlock, Wizard]
  spell_class: Natural20::HoldPersonSpell
```

`type` hints VTT/asset generation: `control`, `debuff`, `buff` → concentration effect icons (`natural20/image_gen/game_icons.py`).

### Upcast metadata

Set `upcast: true` when casting the spell in a higher slot changes damage, targets, rays, duration pool, etc. Omit the key (or use `upcast: false`) for spells like *Shield* or *Mage Armor* that do not scale.

The action bar uses this flag first, then SRD description text, then spell-class introspection as a fallback. After adding or changing scaling behavior, run:

```bash
python scripts/sync_spell_upcast_metadata.py --write
```

Legacy aliases `higher_level: true` and `scales_with_slot: true` are still read but `upcast` is preferred.

## Python class skeleton (concentration debuff)

```python
from natural20.spell.extensions.save_check import SaveCheck
from natural20.spell.spell import Spell

class FooSpell(Spell):
    def build_map(self, orig_action):
        # select_target | select_square | select_cone | select_cube
        ...

    def resolve(self, entity, battle, spell_action, battle_map):
        # Return list of result dicts; failed saves include effect=self
        ...

    @staticmethod
    def end_of_turn(entity, opt=None):
        # Repeat save → entity.dismiss_effect(effect) on success
        ...

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'foo':
            return None
        # concentration + register_effect + event hook + statuses
        session.event_manager.received_event({
            'event': 'spell_debuff',  # or spell_buf for buffs
            'spell': item['effect'],
            'source': item['source'],
            'target': item['target'],
        })
        return item['target']

    def dismiss(self, entity, _descriptor=None, opts=None):
        # Remove statuses / modifiers
        ...
```

Register loader name = class name (`HoldPersonSpell`), file convention `hold_person_spell.py`.

## spell_loader.py

Add alongside peers:

```python
from natural20.spell.foo_spell import FooSpell
# in spell_classes dict:
'FooSpell': FooSpell,
```

## VTT wiring

### How cast animation is triggered

1. `Battle.action` → `action_animator` sets `message.spell` to `spell_action.short_name()` (snake_case slug).
2. Socket `type: 'spell'` → `engine.js` `processSpellEvent` → `SpellEffects.play(spellKey, msg)`.
3. Renderer must be registered under that slug (and optional alias with spaces).

### How active effect icon + overlay work

1. `apply()` registers `target.register_effect(..., effect=self, ...)`.
2. `entity.current_effects()` → `JsonRenderer` adds `str(effect)` to tile `effects` (usually the slug).
3. `map.html` renders `<img src=".../assets/effect/<slug>.png" alt="<slug>">`.
4. `status_effects.js` `PersistentEffects` watches `.effect img` alt/tooltip; matching `EFFECT_CLASS` keys get CSS overlays.

### status_effects.js additions

```javascript
// In EFFECT_CLASS:
hold_person: 'pe-hold-person',

// In keyOf() synonyms if needed:
if (k === 'paralyzed') k = 'hold_person';

// In createOverlayFor — optional second layer (chains, ring, etc.)
```

### spell_effects.js cast animation

Model after `bane` (debuff), `bless` (buff), or `guiding_bolt` (single-target bolt). End with `destroy(); resolve();`. Register alias:

```javascript
register('hold person', function(payload){ return play('hold_person', payload); });
```

### Effect icon PNG

Quick local asset (no API):

```bash
python3 -c "
from PIL import Image, ImageDraw
# ... draw 64x64 RGBA ...
" 
# or: scripts/generate_game_icons.py --only hold_person
```

Path: `webapp/static/assets/effect/<slug>.png` (must match `str(Spell)` / short_name).

### Build minified bundles

```bash
npm run build:assets
```

## Targeting `build_map` params

| Param | Use |
|-------|-----|
| `type: select_target` | Creature target(s) |
| `type: select_square` | AoE origin |
| `range` | Feet; enables LOS filter in `acquire_targets` |
| `num` / `min` / `max` | Multi-target (Bless, Hold Person upcast) |
| `unique_targets: true` | No duplicate targets |
| `target_types` | `enemies`, `allies`, `self`, … |
| `require_humanoid: true` | Humanoid-only (Hold Person, Charm Person) |

Server `/target` and `engine.js` must agree on `select_cone` / `select_cube` modes (see `AGENTS.md`).

## Test helpers

Mock saves for `SaveCheck` (needs `result()` and `__lt__`):

```python
class _MockSaveRoll:
    def __init__(self, total):
        self._total = total
    def result(self):
        return self._total
    def __lt__(self, other):
        return self._total < other
```

Cast in tests via `autobuild` + `SpellAction` or direct `spell.resolve` + `HoldPersonSpell.apply`.

## Reference spells by feature

| Feature | See |
|---------|-----|
| Concentration buff | `bless_spell.py`, `haste_spell.py` |
| Repeat save EoT | `slow_spell.py`, `hold_person_spell.py` |
| Multi-target upcast | `bless_spell.py`, `bane_spell.py` |
| Persistent zone | `grease_spell.py`, extensions `persistent_zone.py` |
| Save for half | `extensions/save_for_half.py`, `thunderwave_spell.py` |
| Spell attack | `firebolt_spell.py`, `evaluate_spell_attack` |
| Humanoid filter | `hold_person_spell.py`, `action_builder.acquire_targets` |
| Condition engine | `entity.py` (`paralyzed`, `incapacitated`), `weapons.py`, `attack_action.py` |
