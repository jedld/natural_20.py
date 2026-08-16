# Add Sidekick NPC Skill

Turn a campaign NPC into a party sidekick: player-controlled movement/actions, NPC-LLM conversation, optional Tasha’s class overlay.

## When to use

- Campaign YAML should list a sidekick at login or as a second character
- An NPC should be able to join/leave mid-game
- A campaign wants Expert / Spellcaster / Warrior tables (opt-in pack)

## 1. Keep them an NPC

Do **not** convert the sheet to a PlayerCharacter. Sidekicks stay in `npcs/<name>.yml`. Players never speak *as* the sidekick (`npc_conversation_mode` stays LLM).

## 2. Campaign YAML (`game.yml`)

```yaml
sidekicks:
  - entity_uid: npc_squire
    selectable: true
    spawn_with_party: true
    owners: []
    sidekick_class: sidekick_warrior
    role: attacker
  - entity_uid: npc_guide
    selectable: false
    owners: [gomerin]
    require_session:
      quest_accepted: true
```

- `selectable: true` — login character select (Sidekick section, separate from PCs).
- `character_selection.sidekick_slots: 1` in `game.yml` — each player picks **one PC and one sidekick**. Omit or `0` to keep a single hero pick (PC or sidekick).
- `owners: [username]` — second character for that user (extra POV after login).
- `require_session` — same pattern as companions.
- Runtime joins persist in `session.session_state['sidekicks']` (save/load). Do not rewrite `index.json` for mid-game joins.

## 3. Join / leave in play

- Player: **Invite to party** on the JRPG dialog (talking distance). Server asks the NPC LLM; accept with `[JOIN_PARTY]`. Clients refresh POV portraits and toast the join.
- NPC tags (same pipeline as `[GO_HOSTILE]`):
  - `[JOIN_PARTY]` or `[JOIN_PARTY: owner=@handle]`
  - `[LEAVE_PARTY]` — back to AI NPC, group `c`
  - `[GO_HOSTILE]` — also leaves as hostile (group `b`)
- DM: `dm.sidekick` (`op=join|leave|assign_owner|list`) or `POST /admin/sidekick`

## 4. Tasha pack (optional)

Copyrighted tables live only in `expansion_packs/tashas_sidekicks/`. Opt in via campaign `index.json`:

```json
"expansion_packs": { "tashas_sidekicks": "tashas_sidekicks" }
```

Class ids: `sidekick_expert`, `sidekick_spellcaster`, `sidekick_warrior`. Roles: warrior `attacker`/`defender`; spellcaster `mage`/`healer`/`prodigy`. Starting level = average PC level. CR ≤ 1/2 is pack policy (`force` override). ASI is `pending_asi` — apply via ability-score UI or `dm.set_property` (no chargen wizard in v1).

Without the pack, membership and player control still work; `apply_sidekick_class` no-ops.

## 5. Engine notes

- In-party sidekicks make death saves, count for encounter `party_size`, and travel with companions.
- Conversation prompts inject an authoritative “already in the party” block (companions by name) so YAML backstory about joining cannot make them act uncommitted.
- Extra Attack, bonus-action Help (`helpful`), NPC Second Wind, PB bump, and level-up HP are core (generic `class_feature` gates).
- Do not put campaign names or Tasha tables in `natural20/` or `templates/`.

See `docs/CAMPAIGN_BUILDING.md`, `docs/EXPANSION_PACKS.md`, `docs/CONVERSATION_RAG.md`.
