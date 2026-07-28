# D&D 5e Dark Horror/Noir Adventure Recommendations for Natural 20 Engine

## Executive Summary

This document evaluates the best D&D 5e dark horror, gothic horror, and noir adventures for implementation in the Natural 20 engine. Recommendations are ranked by **story quality**, **AI engine compatibility**, and **immediate implementation value**.

---

## Engine Capability Analysis

The Natural 20 engine (based on `user_levels/death_house/` structure) supports:

| Feature | Status | Notes |
|---|---|---|
| Multi-map navigation | ✅ | Teleporter transitions, fog effects per map |
| NPC dialog & voice | ✅ | `backstory`, `conversation_buffer`, `voice` config |
| Combat (turn-based) | ✅ | Full battle loop with controllers |
| Spell system | ✅ | YAML definitions + Python classes |
| Status effects | ✅ | Grappled, paralyzed, blinded, etc. |
| Save/load game | ✅ | `savegame.yml` pattern |
| Soundtracks | ✅ | background/battle/ambient tracks |
| TPK victory narration | ✅ | Map-specific endings |
| Entity registry | ✅ | UID-based lookup |
| Dynamic lighting/fog | ✅ | Per-map effect config |
| Cones/AoE targeting | ✅ | `squares_in_cone`, `squares_in_adjacent_cube` |
| Inventory | ✅ | Equipment, magic items |
| Journal system | ✅ | `journal_utils.py` |
| Time tracking | ✅ | `Session.increment_game_time` |
| Conversation witnesses | ✅ | `conversation_witness.py` |
| NPC memory | ✅ | `npc_memory_store.py` |
| LLM-powered NPCs | ✅ | `LlmMcpController`, voice synthesis |

---

## Tier 1: Ready-to-Implement (Already Engine-Compatible)

### 1. Death House (Curse of Strahd Prologue) ⭐⭐⭐⭐⭐
**Status:** Already implemented in `user_levels/death_house/`
- **Levels:** 1-3
- **Source:** Curse of Strahd (Volo's Guide)
- **Theme:** Gothic horror, haunted house, family tragedy
- **Maps needed:** 6-7 rooms across 4 floors
- **AI compatibility:** Excellent — the existing implementation proves this works perfectly

**Current Implementation Features:**
- Multi-floor progression (basement → 2nd → 3rd → attic)
- Ghost children (Rose & Thorn Durst) as narrative hooks
- Shambling mound boss (Walter)
- Fog effects, soundtracks, TPK narrations
- LLM-powered NPC dialog with voice synthesis

**Recommendation:** This is the **canonical starting point** for horror content. Use it as a template for new horror modules.

---

### 2. Down the Outcast's Path (Thyros Investigation) ⭐⭐⭐⭐⭐
**Levels:** 5-7
**Theme:** Urban noir, mystery, political conspiracy, memory-erasure horror
**Status:** Implemented in `user_levels/outcasts_path/`
**Maps:** city_gate, city_streets, tavern (Drowning Rat), investigator_manor, sewers, prison, cathedral
**AI Compatibility:** Excellent

**Why this works:**
- Strong investigation/mystery framework — LLM NPC dialog + Interact clue checks
- Cathedral gated until two session proofs (`manor_notes_found` / `sewer_symbol_found` / `prison_record_found`)
- Ophelia bargain and scorched-altar endings wired via `victory_narration.variants`
- Canonical murder: Ophelia ordered the hit; Volo signed the forgetting

**Key NPCs for LLM integration:**
- Kester Volo (corrupt magistrate)
- Lady Ophelia (ambitious Path leader / bargainer; ordered Reed's murder)
- Whisper, Detective Jaro, Sister Agnes, Marcus Reed (ghost), Tavern Keeper

---

### 3. Phantom Share (Tales from the Yawning Portal) ⭐⭐⭐⭐
**Levels:** 5-7
**Theme:** Supernatural horror, ghost ship, crew curse
**Maps needed:** 5-6 (ship interior, hold, captain's quarters, deck)
**AI Compatibility:** Very Good

**Why this works:**
- Claustrophobic ship setting (perfect for VTT tile-based maps)
- Ghost crew mechanics (phase in/out — great for effects system)
- Environmental hazards (storm, ship integrity)
- Classic haunted ship trope with great atmosphere

**Maps needed:**
```
maps/
  ship_exterior.yml  # Approach view
  deck.yml           # Open deck (storm effects)
  captain_quarters.yml  # Story clues
  hold.yml           # Cargo/monsters
  brig.yml           # Prison section
  cabin.yml          # Final confrontation
```

**Engine features to leverage:**
- Dynamic fog/water effects
- Soundtracks (storm, creaking ship, ghostly choir)
- Status effects (cursed, possessed)
- Limited visibility effects

---

## Tier 2: High Quality, Moderate Implementation

### 4. The Beast of Graensen'skov (DriveThruRPG) ⭐⭐⭐⭐
**Levels:** 3-5
**Theme:** Folk horror, werewolf, isolated village
**Maps needed:** 3-4 (village, forest, cave)
**AI Compatibility:** Very Good

**Why this works:**
- Small village setting (easy map set)
- Werewolf mechanics (transformation — effects system)
- Suspicion/paranoia mechanics (conversation system)
- Classic folk horror atmosphere

**Maps needed:**
```
maps/
  village.yml        # Village center, inn
  forest.yml         # Dark woods
  cave.yml           # Werewolf lair
  graveyard.yml      # Optional supernatural area
```

**Engine features to leverage:**
- `event_manager.py` for full moon transformation events
- Status effects (werewolf curse, infection)
- NPC suspicion tracking

---

### 5. The Haunting of Castle Krigar (Homebrew-style Horror) ⭐⭐⭐⭐
**Levels:** 1-4
**Theme:** Psychological horror, haunted castle, sanity mechanics
**Maps needed:** 6-8
**AI Compatibility:** Excellent

**Why this works:**
- Castle setting with many rooms
- Psychological horror (hallucinations — visual effects)
- Sanity/insanity mechanics (new status effects)
- Each room tells part of a dark story

**Engine features to leverage:**
- Map-specific narrations
- Visual effects (fog, distortion, darkness)
- LLM NPC dialog for ghost interactions
- Journal for clue tracking

---

## Tier 3: Epic Campaigns (Large Implementation)

### 6. Ravenloft: Domains of Dread (Van Richten's Guide) ⭐⭐⭐⭐⭐
**Levels:** Any (modular)
**Theme:** Gothic horror anthology, multiple domains
**Maps needed:** Variable per domain
**AI Compatibility:** Excellent

**Why this is special:**
- Each Domain is a self-contained horror story
- Can implement Domain-by-Domain
- Built-in Darklord mechanics (LLM bosses)
- The Mists provide natural map transitions

**Recommended first Domain: Domain of Woe (Strahd)**
- Already partially implemented
- Can extend beyond Death House

**Other Domains:**
- **Icewind Dale** (frozen horror)
- **The Shattered Swamp** (swamp horror — shambling mound territory)
- **Barovia** (gothic castle)
- **Dementlieu** (aristocratic intrigue horror)

---

### 7. Descent into Avernus ⭐⭐⭐⭐
**Levels:** 1-10
**Theme:** Infernal horror, devil conspiracy, Hell invasion
**Maps needed:** 8-12
**AI Compatibility:** Good

**Why this works:**
- Descent into Hell is a natural map progression
- Devil NPCs (LLM dialog potential)
- Corruption mechanics (status effects)
- Epic scale horror

---

## Recommended Implementation Order

| Priority | Adventure | Levels | Effort | Why First? |
|---|---|---|---|---|
| **P0** | Death House | 1-3 | ✅ Done | Already implemented |
| **P1** | Down the Outcast's Path | 5-7 | Medium | Best noir/mystery fit |
| **P2** | Phantom Share | 5-7 | Medium | Ship maps are VTT-friendly |
| **P3** | Beast of Graensen'skov | 3-5 | Low | Small map count |
| **P4** | Ravenloft Domain | Any | High | Modular, extendable |

---

## Detailed Campaign Design: Down the Outcast's Path

### Story Overview

> In the city of Thyros, a renowned investigator has been murdered under mysterious circumstances. The party is summoned to his manor to discover what he was working on before his death. They uncover a web of political conspiracy, a secret society, and a corrupt magistrate who will stop at nothing to maintain his power.

### Maps

```yaml
# maps/city_gate.yml
- Entry point to Thyros
- Guard NPC dialog (LLM)
- Transition to city streets

# maps/city_streets.yml  
- Hub area, connects to all locations
- Tavern (information gathering)
- Market (random encounters)
- Inn (rest point)

# maps/investigator_manor.yml
- Starting location
- Clues and evidence
- Journal system integration
- Possible ambush

# maps/sewers.yml
- Dungeon section
- Rat swarm encounters
- Hidden cult passage
- Dark atmosphere (fog + limited vision)

# maps/prison.yml
- Rescue mission
- Guard NPCs
- Lockpicking mechanics
- Escape route

# maps/cathedral.yml
- Final confrontation
- Secret society headquarters
- Magical hazards
- Magistrate final boss
```

### Key NPCs

| NPC | Role | LLM Voice Style |
|---|---|---|
| Kester Volo | Corrupt magistrate | Smooth, authoritative, hidden menace |
| Lady Ophelia | Secret society leader | Elegant, calculating, seductive danger |
| Marcus Reed | Dead investigator (ghost) | Urgent, fragmented, desperate |
| Sister Agnes | Healer with secrets | Religious, fearful, guilt-ridden |
| Detective Jaro | Rival investigator | Gruff, suspicious, competitive |
| "Whisper" | Informant | Nervous, quick, unreliable |

### Engine Features Required

```python
# New status effects needed
- "suspicion" — tracks NPC attitudes
- "cursed" — magical affliction
- "infiltrated" — player has disguise

# Journal entries needed
- "clue_guard_statement"
- "clue_tavern_witness"
- "clue_manor_notes"
- "clue_sewer_symbol"
- "clue_prison_record"

# Conversation witness tracks
- "investigation_progress"
- "society_membership_revealed"
- "magistrate_corruption_proven"
```

---

## File Structure Template for New Campaigns

```
user_levels/<campaign_name>/
├── game.yml                    # Campaign metadata
├── index.json                  # Login, maps, characters
├── savegame.yml               # Save slot template
├── npc_system_prompt.txt      # LLM NPC behavior
│
├── assets/
│   ├── login_background.jpg   # Login screen
│   ├── token_*.png            # Entity tokens
│   ├── maps/
│   │   ├── map1.png           # Map images
│   │   └── ...
│   ├── sounds/
│   │   ├── background.mp3
│   │   └── battle.mp3
│   └── characters/
│       └── character_art.png
│
├── maps/
│   ├── game_map.yml           # Starting map
│   ├── map1.yml               # Map definitions
│   ├── map2.yml
│   ├── monsters.yml           # Monster spawns
│   └── entity_token_map.csv   # Token ID mapping
│
├── npcs/
│   ├── npc1.yml               # NPC stat blocks
│   ├── npc2.yml
│   └── ...
│
├── characters/
│   ├── pc1.yml                # Pre-made PCs
│   └── pc2.yml
│
├── items/
│   ├── equipment.yml          # Weapons/armor
│   ├── magic_items.yml        # Magic items
│   ├── objects.yml            # Interactive objects
│   └── spells.yml             # Custom spells
│
├── char_classes/
│   ├── wizard.yml
│   └── ...                    # Class configs
│
├── races/
│   ├── human.yml
│   └── ...                    # Race configs
│
├── backgrounds/
│   └── criminal.yml           # Background configs
│
├── locales/
│   └── en.yml                 # Flavor text
│
└── feats/
    └── ...                    # Optional feats
```

---

## Implementation Checklist

For each new campaign:

- [ ] Create `game.yml` with campaign metadata
- [ ] Create `index.json` with login accounts, character selection, map list
- [ ] Design and create map images (PNG, tile-based)
- [ ] Create `.yml` map files with entity placement, teleporters, effects
- [ ] Define NPC stat blocks in `npcs/*.yml`
- [ ] Set up NPC backstory/voice for LLM dialog
- [ ] Create character sheets in `characters/`
- [ ] Define custom items/spells in `items/`
- [ ] Configure soundtracks
- [ ] Set up TPK/victory narrations
- [ ] Add map-specific narration triggers
- [ ] Test save/load cycle
- [ ] Run webapp parity tests after route changes

---

## Tips for AI-Engine-Specific Design

1. **Use LLM NPCs strategically**: Characters that need unique dialog, emotional range, or reactive storytelling benefit most from LLM control.

2. **Design for conversation flow**: NPCs with `backstory` and `conversation_buffer` create the best player interactions.

3. **Use status effects for horror**: Paranoia, curses, possession, and sanity loss make excellent horror mechanics.

4. **Map transitions as story beats**: Teleporter effects can trigger narrations, sound changes, and atmosphere shifts.

5. **Journal for mystery tracking**: Use the journal system to let players track clues, evidence, and NPC relationships.

6. **Limited visibility for horror**: Fog, darkness, and restricted vision effects create tension.

7. **Soundtracks for mood**: Layer ambient tracks (background, battle, specific NPC themes) for immersive horror.

---

## References

- Existing implementation: [`user_levels/death_house/`](../user_levels/death_house/)
- Blueprint docs: [`docs/WEBAPP_BLUEPRINTS.md`](./WEBAPP_BLUEPRINTS.md)
- Core engine: [`natural20/`](../natural20/)
- Webapp: [`webapp/`](../webapp/)
