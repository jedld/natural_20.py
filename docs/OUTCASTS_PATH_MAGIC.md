# Outcasts' Path — Spells, Divination & Quest Safety

How player magic interacts with investigation gates, NPC truth, and endings.

Erasure model (records → ritual binding → maintenance → **tithe to the Lull Beneath**) and who still remembers Reed: see [`OUTCASTS_PATH_STORY.md`](./OUTCASTS_PATH_STORY.md#erasure-rules). Eldritch patron: [`The Lull Beneath`](./OUTCASTS_PATH_STORY.md#the-lull-beneath-eldritch-truth).

**Divination near the Well:** Scrying the aquifer returns the same static as seventh-bell interference — point casters at on-site Religion/Arcana on pool, grate, or Well Beneath instead.

## Pregen spell loadouts (L5)

| PC | Notable spells | Quest impact |
|---|---|---|
| Wizard | Detect Magic, Comprehend Languages, Misty Step, Hold Person, Counterspell, Fireball | Detect Magic → Arcana Interact proofs; Misty Step is **same-map only** (cannot skip to cathedral); Fireball can help scorch altar / fight bosses |
| Cleric | Detect Magic, Guidance, Protection from Evil and Good, heals, Spiritual Weapon | Religion Interact on Path auras; Protection flavors hollow liturgy; turning altar = scorched path |
| Paladin | Bless, Cure, Protection from Evil and Good, Divine Favor + Divine Sense feature | Religion Interact grants `divine_sense_path` |
| Others | No spells / mundane | Investigation & social paths unchanged |

Spells **not** implemented as full engine classes (Zone of Truth, Scrying, Speak with Dead, Detect Thoughts, Commune) are handled as **DM/LLM fail-forward** via Interact checks that mimic them without dumping the bible.

## What could break a mystery — and how we handle it

| Magic / tactic | Risk | Campaign response |
|---|---|---|
| Scrying / Commune / remote divination | Skip maps | Path binding returns fog/static near seventh bells (prompt + deny narration). Use on-site Detect Magic / Arcana instead. |
| Speak with Dead (Reed) | Full confession | Manor **Residual Echo**: Religion check yields a **fragment** only; sets `magical_proof_reed`, not free cathedral entry alone. |
| Zone of Truth / Detect Thoughts / Charm | Forced full dump | NPCs speak careful literal truths that still mislead. Gates still need proof flags. |
| Hold Person / dominate | Skip social | Ends talks; Path elites go hostile. No auto-flags. |
| Misty Step / short teleport | Skip doors | Same map only — cannot cross `target_map` teleporters. |
| Knock | Skip locks | Prison uses social/bribe; no soft-lock. |
| Invisibility | Skip combat | Fine; proofs still required for cathedral. |
| Fireball / Dispel on altar | Soft-lock ending | Explicit **scorched-path** (Athletics shatter, Arcana study, Religion turn). |
| Detect Magic spam | Bypass investigation | Counts as **one** magical proof type; still need **two** proofs (or invitation / rose pin). |

## Cathedral entry — alternate proof math

Need **any 2** of:

**Mundane:** `manor_notes_found`, `sewer_symbol_found`, `prison_record_found`  
**Magical:** `magical_proof_rose`, `magical_proof_binding`, `magical_proof_reed`, `divine_sense_path`, `detect_magic_path_aura`

**Bypass (alone):** `ophelia_invitation` (sealed rose letter in manor)  
**Inventory proof (+1 toward count):** carrying `black_rose_pin` (sewer crates)

Examples:
- Notes + Detect Magic on rose → enter  
- Divine Sense on rose + Arcana on ledger → enter  
- Rose pin + one mundane proof → enter  
- Ophelia's invitation alone → enter (bargain path)

## Magical Interact paths (engine-backed)

| Site | Check | Flag(s) |
|---|---|---|
| Sewer rose | Arcana / Religion | `magical_proof_rose`, often also `sewer_symbol_found` |
| Prison ledger | Arcana | `magical_proof_binding`, `prison_record_found` |
| Manor notes | Arcana | `manor_notes_found`, `detect_magic_path_aura` |
| Reed residual echo | Religion / Arcana | `magical_proof_reed` |
| Ophelia invitation | Investigation / Arcana | `ophelia_invitation` (bypass) |
| Ritual altar | Arcana (study) / Religion (turn) | proof or `ritual_scorched` |
| Ritual candles | Arcana snuff | `ritual_candle_snuffed`, binding proof |

## Ending paths (magic-inclusive)

| Ending | How |
|---|---|
| Pyrrhic expose | Defeat Volo/Path without bargain/scorch |
| Ophelia bargain | Invitation or cathedral deal; she says “then we have a bargain” |
| Scorched path | Shatter altar (Athletics), turn binding (Religion), or Dispel-study then destroy |

## DM / LLM rules (also in `npc_system_prompt.txt`)

1. Never dump the full layered truth to a single spell.  
2. Divination fails **forward** into sensory clues pointing at Interact sites.  
3. Charm/ZoT → half-truths; still demand proof for gates.  
4. Celebrate Detect Magic / Divine Sense by pointing at rose, ledger, echo, altar.  
5. Fireball in the nave is allowed — Counterspell / cover / bargain fork.
