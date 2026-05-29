# Adventure: A Wild Sheep Chase

Campaign path: `user_levels/wild_sheep_chase/`

Full DM/player notes: [user_levels/wild_sheep_chase/README.md](../user_levels/wild_sheep_chase/README.md)

## Run

```bash
cd webapp && TEMPLATE_DIR=../user_levels/wild_sheep_chase python -m flask run
```

Requires `LLM_PROVIDER` (and related env vars) for `/talk` with Finethir, Guz, and Noke.

## Engine coverage

| Adventure element | Implementation |
|-------------------|----------------|
| Scene 1 hook + scroll | Narration + `scroll_speak_animals` note + LLM Finethir; `game.yml` `conversation_item_offers` blocks repeat offers after accept/use; witnessed accept/use lines feed Finethir's `/talk` context |
| Scene 2 Guz fight | `town_market` tavern + market; tables (half cover), crowd (difficult terrain); **Guz `reckless: true`** (advantage both ways) |
| Quest accept | LLM keyword `agreed to help` → session state + road teleporter + signpost; **Finethir companion travel** via `game.yml` `companions` |
| Scene 3 treehouse | 5 linked maps, placeholder `background_image` per map |
| Passphrase bridge | Keyword `Mae Tref Cathode` → hint stone + living bridge |
| Scene 4 wand | Keyword `noke defeated` reveals wand; **`arcana_check`** on `wand_true_polymorph` with margin-based malfunction messages |
| Noke spells | `enlarge_reduce`, `haste`, `polymorph` spells + Noke `prepared_spells` |
| Bed dragon | **`combat_script.flee_countdown`** on Noke (3 rounds → spawn `bed_dragon_wyrmling` at `noke_bed`) |

## Automated vs manual

| Former gap | Status |
|------------|--------|
| Guz Reckless | **Automated** — `reckless: true` on `npcs/guz.yml` |
| Enlarge/Reduce, Haste, Polymorph | **Automated** — spell classes + Noke `prepared_spells` |
| Wand malfunction | **Mostly automated** — Arcana interact check with `outcomes_by_margin`; extreme table rows may still need DM narration |
| 3-round bed dragon | **Automated** — `combat_script` on `ahmed_noke.yml` |
| Finethir follows | **Automated** — `companions` in `game.yml` + teleporter / `switch_map` sync |

## LLM directives

NPCs may use `[REQUEST_CHECK: skill=arcana, target=speaker, dc=15]` (and other skills listed in `REQUEST_CHECK_SKILLS` in `webapp/entity_rag_handler.py`) in addition to persuasion/intimidation.
