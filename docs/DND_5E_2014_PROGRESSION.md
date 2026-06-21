# D&D 5e 2014 Progression

Natural20 supports XP-based advancement using the D&D 5e 2014 thresholds,
plus campaign-gated advancement for milestone or event-driven games.

## Campaign Progression Mode

Configure progression in `game.yml`:

```yaml
progression:
  mode: xp
```

Supported modes:

| Mode | Behavior |
|---|---|
| `xp` | Default. XP thresholds determine when a character can level up. |
| `dm` | XP may still be tracked, but only explicit DM grants create level-up opportunities. |
| `event` | XP may still be tracked, but only configured named campaign events create level-up opportunities. |

For event-gated progression:

```yaml
progression:
  mode: event
  events:
    rescued_prince:
      label: Rescued the Prince
      levels: 1
    sealed_shadow_gate:
      label: Sealed the Shadow Gate
      target_level: 5
```

`levels` grants a number of level-ups. `target_level` grants enough level-ups
to reach that total character level.

## Character XP

Player character YAML may include:

```yaml
xp: 0
level: 1
classes:
  wizard: 1
```

If `xp` is omitted, the engine treats the character as having `0` XP. XP is campaign state and is saved through the normal save/load flow.

## Advancement Thresholds

The engine uses the 2014 character advancement table:

| Level | Total XP |
|---|---:|
| 1 | 0 |
| 2 | 300 |
| 3 | 900 |
| 4 | 2,700 |
| 5 | 6,500 |
| 6 | 14,000 |
| 7 | 23,000 |
| 8 | 34,000 |
| 9 | 48,000 |
| 10 | 64,000 |
| 11 | 85,000 |
| 12 | 100,000 |
| 13 | 120,000 |
| 14 | 140,000 |
| 15 | 165,000 |
| 16 | 195,000 |
| 17 | 225,000 |
| 18 | 265,000 |
| 19 | 305,000 |
| 20 | 355,000 |

## XP Awards

DMs can award XP through the web endpoints:

- `POST /award_xp` for manual or quest XP.
- `POST /award_encounter_xp` for monster XP from NPCs.
- `GET /xp_summary` for party XP and active encounter difficulty.

MCP clients can use `dm.award_xp` for the same mutation surface.

Manual XP can be awarded to each listed PC or split across recipients. Encounter XP uses NPC `xp` values by default and splits the total across recipients.

For non-XP progression, use:

- `POST /grant_level_up` for DM-gated level-up permissions.
- `POST /grant_event_level_up` with an `event` key for event-gated progression.
- MCP `dm.grant_level_up`, optionally with `event`, for the same grant flow.

## Level-Up Flow

When a PC reaches enough XP for the next level, the engine reports pending level-ups and the UI shows a level-up action on the character sheet. Applying a level-up updates:

- total level and per-class level;
- max HP using fixed-average hit die plus Constitution modifier by default;
- current HP by the HP gained, capped by the new maximum;
- hit dice;
- spell slot capacity while preserving spent slots;
- class feature preview data and level history.

Some class choices are still represented as pending choice metadata when the engine does not yet automate the full 2014 rule. Examples include ASI/feat choices and newly entering a multiclass.

## NPC CR And XP

NPC YAML may include both `cr` and `xp`:

```yaml
cr: 1
xp: 200
```

The engine can derive canonical 2014 XP from CR, but explicit `xp` remains authoritative so custom campaign creatures can override the default.
