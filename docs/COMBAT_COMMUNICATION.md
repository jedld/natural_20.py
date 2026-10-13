# Combat communication and intelligence-scaled tactics

AI-controlled combatants (the `llm` controller with either a generative LLM or
the JEV decision model) can coordinate with their allies, and how well they
plan depends on their Intelligence. Both systems live in the engine:

- `natural20/utils/combat_comms.py` covers who can speak, who hears, the
  per-listener "heard" inbox, and automatic callouts.
- `natural20/utils/combat_intelligence.py` maps INT to a tactics tier and
  applies that tier's limits.

## The 5e rule being modelled

PHB, *Other Activity on Your Turn*: a creature may communicate "however you are
able, through brief utterances and gestures, as you take your turn". Speaking is
free, but it is short, it happens on your own turn, and anyone nearby can hear it.

| Rule | Implementation |
|---|---|
| Only on your own turn | `issue_callout` rejects with `not_your_turn`. Legendary actions and reactions cannot speak. |
| Brief utterance | One callout per turn (`already_spoke`), capped at `max_words` (default 20). Stunned creatures speak "falteringly" (3 words). |
| Must be able to speak | Blocked when the speaker is dead, unconscious, asleep, paralyzed, or petrified, is in magical silence (`silenced` status or Silence effect), is in a beast form (Wild Shape or Polymorph), or knows no language. |
| Must be able to hear | Listeners must be conscious, not `deafened`, and not in silence. Range comes from the shared speech acoustics: whisper 5 ft, normal 30 ft, shout 60 ft (the default), with walls and doors muffling sound. |
| Language | Listeners who don't comprehend the language get the entry with `understood: false` and no text. The prompt shows "spoke in X - you could not understand it". |
| Not private | Enemies within earshot who understand the language overhear it. A callout's `overheard_by_enemies` lists them. |
| Knowledge | A callout target must be visible to the speaker (`target_not_visible`). |
| Telepathy | `telepathy: <ft>` in NPC YAML lets a creature send silently, even while silenced, to allies in range who know any language. Enemies can't overhear it. |
| No extra actions | A heard callout only informs the listener's next decision. It grants nothing mechanically. |

All in-battle speech that goes through `Entity.send_conversation` is recorded
into listeners' inboxes, including `SpeakAction` and a human player's chat. AI
allies therefore react to "Focus the vampire!" typed by a player. Inboxes live
in `battle.entities[e]['heard_callouts']`, so they are shared across controller
instances and saved with the battle. Entries expire after `memory_rounds`.

### Who speaks how

- **Generative LLM.** When a callout is allowed, the prompt offers it. The
  model replies with the action index and, optionally, a line
  `CALLOUT <kind> [target]: <words>`. With tool calling, it uses the `callout`
  tool instead. The older `speak`, `request_help`, `warn_ally`,
  `coordinate_attack`, and `taunt` tools route through the same rules.
- **JEV** (decision-only, no text output). After it picks an action, it makes
  one more decision: *what to tell its allies*. The menu comes from
  `natural20/utils/combat_strategy.py` (`strategy_options`), built only from
  what the speaker can see:
  - stay silent (always the first option)
  - call for healing (at or below 50% HP, and only when a conscious ally can
    heal: Lay on Hands, a healing spell, or a healing item)
  - revive a visible fallen (unconscious, not dead) ally, and regroup around
    the fallen when the side isn't outmatched. These come before any damage
    call, because a downed ally is the fight being lost.
  - focus fire on the enemy it is attacking, the most wounded enemy (only
    when that enemy is at or below 50% HP), or the enemy that has hit the most
    of its side. Focus options are left out when there is only one enemy,
    since everyone is already fighting it.
  - ask for help against an enemy next to it
  - protect a wounded ally, warn about an enemy next to that ally, or taunt
    an enemy to draw it off that ally
  - order a retreat when its side is badly outmatched

  `jev_decision.jev_select_callout` sends the usual state text plus the action
  just chosen. If the model fails, the deterministic fallback applies: call
  for healing at 25% HP or below, then urge reviving a fallen ally, otherwise
  announce the enemy being attacked unless an ally already called it. Heard
  callouts appear in JEV's state text under `heard:`.

Callout kinds: `focus`, `heal`, `help`, `warn`, `retreat`, `protect`, `taunt`,
`revive` (target: a fallen ally), `regroup`, and `say` (free text). Options a
creature's tier doesn't allow are left off its menu. Calls aimed at allies
(`ALLY_DIRECTED_KINDS`: `focus`, `heal`, `help`, `warn`, `retreat`, `protect`,
`revive`, `regroup`) are refused with reason `no_listening_ally` when no ally
can hear and understand the speaker. A creature whose only company is
mindless beasts doesn't shout orders at them.

### In-character wording

A callout chosen without explicit words (JEV, auto callouts, or an LLM
`CALLOUT` line with no text) is voiced by a *phraser* installed through
`combat_comms.set_callout_phraser`. The webapp installs
`webapp/combat_callout_phrasing.py`. It asks the NPC conversation LLM
(`response_mode: conversation`, so per-NPC provider overrides apply) for one
line within the word cap. The prompt carries the speaker's persona
(`description` / `backstory` / `personality`, plus `voice.prompt` and
`voice.traits`), the intent, the target, and the language or telepathy. When
the target is unconscious (a `revive` call), the prompt tells the speaker to
address conscious allies instead. The speaker's last few phrased lines this
battle (`battle.entities[e]['spoken_callouts']`) and the last few lines it
heard from others are passed as `recent_lines`, so the model doesn't repeat
itself or parrot its allies. The reply is trimmed to its first line, with speaker labels and quotes removed,
and capped. If it is empty, `[NO_RESPONSE]`, or an error, the template line is
used instead ("Focus on X!").

Only the wording changes. Listeners still receive the same structured `kind`
and `target`. The call runs synchronously on the acting creature's turn, so a
slow NPC model adds that delay to each AI turn that speaks. Opt out per
creature with `callout_phrasing: false`, or campaign-wide with
`llm_phrasing: false`.

## Intelligence tiers

These follow the DMG advice to play creatures according to their Intelligence.

| Tier | INT | Plays like |
|---|---|---|
| `instinct` | 1–3 | Attacks the nearest enemy or its last attacker. Hostile options aimed elsewhere are filtered out for both LLM and JEV. It never calls out and ignores callouts. |
| `simple` | 4–7 | Uses simple tactics. Callouts are limited to `focus`, `help`, `heal`, `retreat`, `regroup`, `taunt`, and `say`, at most 6 words. It ignores enemy callouts it overhears. |
| `tactical` | 8–13 | Focus fire and protecting allies. Full callouts. It exploits overheard enemy callouts. |
| `mastermind` | 14+ | Plans ahead: targets healers, casters, and concentration. When choosing a callout language, it picks one its allies know and nearby enemies don't. |

The tier's guidance text is prepended to the LLM combat instructions. JEV gets a
`tactics: <tier> (INT n)` line in its state. Override the tier per creature with
`tactics: instinct|simple|tactical|mastermind` in NPC or character YAML. AI-run
PCs use their own INT.

## Configuration (`game.yml`)

```yaml
combat_communication:
  enabled: true          # default true; N20_COMBAT_COMMS=0 disables globally
  max_words: 20
  memory_rounds: 1
  auto_callouts: true    # JEV announcements
  strategic_callouts: true  # JEV picks the callout from the combat-data menu (one extra decision per turn)
  llm_phrasing: true     # conversation LLM voices callouts in character
  default_volume: shout  # whisper | normal | shout
```

Tests: `tests/test_combat_comms.py`, `tests/test_npc_communication.py`,
`n20-webapp/tests/webapp/test_combat_callout_phrasing.py`.
