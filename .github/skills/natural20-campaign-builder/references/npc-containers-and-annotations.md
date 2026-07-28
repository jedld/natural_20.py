# NPC map containers, tavern stock, and staff annotations

Use this when building **hub/tavern/shop** scenes where LLM NPCs should serve items, restock counters, bank payment gold, or read staff-only markings on objects.

**Engine implementation:** `webapp/npc_item_exchange.py`, `webapp/entity_rag_handler.py`, `natural20/concern/annotatable.py`, `natural20/item_library/chest.py`.

**Conversation tag reference:** [docs/CONVERSATION_RAG.md](../../../../docs/CONVERSATION_RAG.md) (item exchange and RAG sections).

**Canonical campaign example:** [user_levels/wild_sheep_chase/maps/town_market.yml](../../../../user_levels/wild_sheep_chase/maps/town_market.yml) — `BAR` and `SAFE` map tokens (local `user_levels/` folder; **gitignored** in this repo). Stocked definitions live in that campaign's `items/objects.yml` and `items/equipment.yml`.

**Reusable template baselines** (tracked in git): `templates/items/objects.yml` (`tavern_bar_counter`, `tavern_till_safe`) and `templates/items/equipment.yml` (provisions + `tavern_safe_key`). Campaign `items/*.yml` files merge on top of templates automatically.

### Naming: type key vs `@mention` handle

| Concept | Example bar | Example till safe |
|---|---|---|
| **Object type key** (`type:` in map legend) | `tavern_bar_counter` | `tavern_till_safe` |
| **`entity_uid` / `@handle`** for LLM tags | `tavern_bar` | `tavern_safe` |
| **Map token** | `BAR` | `SAFE` |

Searching the repo for `tavern_bar` will **not** find an object type — that string is the `entity_uid`. Search for `tavern_bar_counter` or `tavern_till_safe` instead.

---

## When to use

| Pattern | Use for |
|---|---|
| **Open container** (`Chest`, `state: opened`) | Bar counter, pantry, shop shelf — staff retrieve/serve without unlocking |
| **Locked container** (`Chest`, `locked: true`, `key:`) | Till safe, strongbox — payment gold, valuables |
| **`notes`** on objects | Clues **player characters** discover via Look, perception, investigation |
| **`annotations`** on objects | **NPC-only** staff knowledge (key location, till codes, procedures) |

Do not put staff procedures in `notes` if PCs should not learn them automatically. Do not put player clues in `annotations` — PCs never see annotations in conversation or `[OBSERVE]`. Annotations do **not** use `perception_dc`; allowed NPCs see them when the object is in line of sight.

---

## Open bar / shop counter (container stock)

Define an object type with `item_class: Chest`, always open and unlocked.

**Where to define:** add or override in `<campaign>/items/objects.yml` (merges with `templates/items/objects.yml`). Baseline type `tavern_bar_counter` ships in templates; campaigns add `entity_uid`, `inventory`, `notes`, and `annotations`.

```yaml
# items/objects.yml
tavern_bar_counter:
  name: Bar Counter
  description: A long oak bar with kegs, bread, cheese, and a stew pot.
  color: brown
  item_class: Chest
  lockable: false
  state: opened          # required for loot/store without opening
  passable: true
  placeable: false
  interactable: true
  token: "="
  entity_uid: tavern_bar # stable @mention handle for LLM tags
  notes:                 # visible to PCs (Look, outward appearance)
    - note: Ale, bread, cheese, and stew behind the counter.
  inventory:
    - type: ale_mug
      qty: 24
    - type: bread_loaf
      qty: 8
```

Place on the map:

```yaml
# maps/hub.yml — map.entities
- token: BAR
  layer: object
  pos: [9, 19]

# legend
BAR:
  name: tavern_bar_counter
  type: tavern_bar_counter
```

Define item slugs in `items/equipment.yml` (or inherit from `templates/items/equipment.yml` and add campaign-only entries):

```yaml
ale_mug:
  name: Mug of Ale
  type: provisions
  subtype: drink
  consumable: true
bread_loaf:
  name: Loaf of Bread
  type: provisions
  subtype: food
  consumable: true
```

**Player UI:** Humans can still use the normal chest **loot/store** interact dialog on the object. LLM staff use conversation tags (below).

---

## Locked till safe (payment gold)

```yaml
tavern_till_safe:
  name: Tavern Till Safe
  description: Iron-banded strongbox behind the bar.
  item_class: Chest
  lockable: true
  locked: true
  key: tavern_safe_key
  state: closed
  interactable: true
  entity_uid: tavern_safe
  notes:
    - note: A heavy strongbox — where the house keeps its coin.
  annotations:
    - text: "Third hook beneath the bar lip holds the safe key — staff only."
      viewers: [mara_bartender, pip_barmaid]
    - text: "Reconcile the till every tenday; Mara holds the master ledger."
      viewers: [mara_bartender, pip_barmaid]
  inventory: []
```

Staff key item and currency:

```yaml
# items/equipment.yml
tavern_safe_key:
  name: Tavern Safe Key
  type: key
gold_piece:
  name: Gold Piece (gp)
  type: currency
```

Give keys to staff NPCs:

```yaml
# map legend overrides or npcs/*.yml
default_inventory:
  - type: tavern_safe_key
    qty: 1
```

**Staff workflow (document in NPC backstory):**

1. `[INTERACT: target=@tavern_safe, action=unlock]` — requires `tavern_safe_key` in inventory
2. `[INTERACT: target=@tavern_safe, action=open]`
3. `[STORE: item=gold_piece, target=@tavern_safe, qty=N]`
4. Optionally `[INTERACT: action=close]` / `lock` when done

`[LIST_CONTAINER: target=@tavern_safe]` reports `locked` or `closed` until opened; contents are hidden while secured.

---

## `notes` vs `annotations`

| | `notes` | `annotations` |
|---|---------|---------------|
| **Audience** | All entities, including player characters | **NPCs only** (never shown to PCs) |
| **Discovery** | Look action, skill DCs on object, `[OBSERVE]` appearance | `[ANNOTATIONS]`, `[OBSERVE]` (`staff annotations:`), NPC Look — **line of sight only** |
| **YAML field** | `notes:` with `note:` text | `annotations:` with `text:` (or `note:`) |
| **Targeting** | — | Optional `viewers: [entity_uid, ...]`; omit for any NPC |
| **Perception** | `perception_dc`, `investigation_dc`, etc. | **None** — use `notes` if a roll is required |

```yaml
notes:
  - note: "Scratches on the lid — adventurers might notice this."
    perception_dc: 12

annotations:
  - text: "Key on third hook under bar lip."
    viewers: [mara_bartender, pip_barmaid]
```

Implementation: `Notable` mixin on entities (`notes`); `Annotatable` mixin on map `Object` (`annotations`).

---

## LLM conversation tags (staff NPCs)

Requires `conversation_handler: llm` on the NPC. Tags are stripped from spoken dialogue; the server executes side effects.

### Container stock

| Tag | Behavior |
|-----|----------|
| `[LIST_CONTAINER: target=@tavern_bar]` | Regenerates reply with stock summary (`ale mug x24, ...`) |
| `[LIST_CONTAINER]` | All nearby containers within 30ft (shows `locked`/`closed`/contents) |
| `[RETRIEVE: item=ale_mug, target=@tavern_bar, qty=1]` | Moves item from open, unlocked container → NPC inventory |
| `[STORE: item=bread_loaf, target=@tavern_bar, qty=2]` | Deposits from NPC inventory → container |
| `[OFFER_ITEM: item=ale_mug, target=speaker]` | Accept Item prompt; pulls from NPC inventory **or** nearby open container (e.g. bar) |

Retrieve/store require container **unlocked and opened** within 15ft and line of sight.

### Staff annotations

| Tag | Behavior |
|-----|----------|
| `[ANNOTATIONS: target=@tavern_safe]` | Regenerates reply with annotation text visible to this NPC |
| `[ANNOTATIONS]` | All nearby annotated objects within 30ft |

`[OBSERVE]` for NPCs also includes `stock:` on visible containers and `staff annotations:` on in-sight objects for allowed viewers.

### Related tags

- `[PICKUP: item=<slug>]` — ground items only
- `[TRADE: target=speaker]` / `[REQUEST_ITEM: ...]` — player/NPC item exchange dialogs
- `[INTERACT: target=@handle, action=unlock|open|close|lock]` — chest/door state

---

## NPC backstory checklist

For each tavern/shop staff NPC with LLM dialogue, include in `backstory`:

1. **Handles** — `@tavern_bar`, `@tavern_safe` (match `entity_uid` on objects)
2. **Item slugs** — exact slugs for ale, food, `gold_piece`
3. **Serve workflow** — `[OFFER_ITEM: item=ale_mug, target=speaker]` (bar is source when NPC lacks inventory)
4. **Till workflow** — unlock → open → `[STORE: item=gold_piece, target=@tavern_safe]`
5. **Inspection** — `[LIST_CONTAINER: target=@tavern_bar]` before restocking; `[ANNOTATIONS: target=@tavern_safe]` for staff markings
6. **Boundaries** — do not offer items the bar/safe does not stock; do not store in a locked/closed safe

Example one-liner for a bartender:

```
Offer drinks with [OFFER_ITEM: item=ale_mug, target=speaker] from @tavern_bar.
Bank payments: unlock @tavern_safe, open it, [STORE: item=gold_piece, target=@tavern_safe].
Check stock with [LIST_CONTAINER: target=@tavern_bar].
```

---

## Validation and testing

When adding containers or annotations:

1. `python scripts/validate_campaign.py user_levels/<slug>`
2. Confirm every `inventory[].type` resolves in campaign or `templates/` items
3. Confirm `key:` item exists and staff who need access have it in `default_inventory`
4. Confirm `entity_uid` values are unique and referenced consistently in NPC backstories
5. Run `pytest tests/webapp/test_npc_item_exchange.py tests/test_annotatable.py` if touching engine helpers

---

## Design rules

- **Open counter** — `lockable: false`, `state: opened`; place adjacent to staff spawn
- **Till safe** — start `locked: true`, `state: closed`; empty `inventory: []` unless seeding coin
- **Never** gate required player progression on staff LLM correctly using container tags; use deterministic map state or DM fallback
- **Prefer** witnessed console lines (automatic) over implying invisible transfers in dialogue alone
- **Reuse** existing `Chest` interactions for players; conversation tags mirror loot/store transfer rules
