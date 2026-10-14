# Player's Handbook 2024 (expansion pack)

Opt-in content from the **2024 Player's Handbook** (Wizards of the Coast) that is **not** in the SRD 5.2. It is not bundled in `templates/` or `natural20/`. SRD 5.2 content (Archery, Magic Initiate, Weapon Mastery) lives in `templates/feats/` instead.

Contents:

- `feats/lucky.yml`, `feats/sharpshooter.yml`, `feats/crossbow_expert.yml`.
- `char_classes/ranger.yml`: the Gloom Stalker ranger subclass (on top of the SRD 5.2 ranger overlay).
- `backgrounds/wayfarer.yml`: the Wayfarer background (origin feat Lucky).
- `char_classes/warlock.yml`: the Archfey Patron warlock subclass (on top of the SRD 5.2 warlock overlay).
- `items/spells.yml`: Summon Fiend and the 2024 Blade Ward (also Hail of Thorns).
- `npcs/fiendish_spirit_{demon,devil,yugoloth}.yml`: the Summon Fiend spirits.

Campaigns opt in via `index.json`:

```json
{
  "expansion_packs": {
    "players_handbook_2024": "players_handbook_2024"
  }
}
```

Use these with `ruleset: 5e-2024` in `game.yml`.

## Feats

The feats have no Python of their own. They use the generic feat-YAML mechanics in `natural20/utils/feat_mechanics.py`, `natural20/utils/luck_points.py` and `natural20/utils/weapon_loading.py`:

| Feat | Benefit | Mechanic |
|---|---|---|
| Lucky | Luck Points = PB, long rest | `resource_pools.luck_points` (`max: proficiency_bonus`, `restore_on: long_rest`) |
| | Advantage on your own D20 Test | `luck.self_advantage` |
| | Disadvantage on an attack against you | `luck.impose_disadvantage` |
| Sharpshooter | Ignore half / three-quarters cover | `weapon_attack_rules[].ignore_cover: [half, three_quarters]` |
| | No long-range disadvantage | `weapon_attack_rules[].no_long_range_disadvantage` |
| | No disadvantage with an enemy within 5 ft | `weapon_attack_rules[].no_adjacent_enemy_disadvantage` |
| Crossbow Expert | Ignore Loading | `weapon_attack_rules[].ignore_properties: [loading]` |
| | No disadvantage with an enemy within 5 ft | `weapon_attack_rules[].no_adjacent_enemy_disadvantage` |
| | Ability modifier on the Light-property extra attack | `weapon_attack_rules[].extra_attack_ability_damage` (filtered to `property: light`) |

Simplifications:

- Lucky is offered after the d20 is rolled, not before. After your roll fails you roll another d20 and keep the higher, and after an attack hits you the attacker rolls another d20 and keeps the lower. The odds match spending the point up front.
- Lucky isn't offered on a roll that already has advantage (or, against you, disadvantage). If the roll has the opposite, the point cancels it and the first die stands.
- Lucky only works in combat and only on rolls with a known DC or AC: attacks, saving throws, death saves, and ability checks that pass a `dc`.
- The AI spends a point only when the reroll could flip the result, with at least a 25% chance (`luck.ai_min_chance`).
- The +1 Dexterity of Sharpshooter and Crossbow Expert is recorded as `ability_score_increase` but is not applied automatically. Import or build the sheet with the final scores.
- Crossbow Expert's "load without a free hand" part has no effect, since hands aren't tracked for loading.

## Gloom Stalker (ranger subclass)

Sheet key `ranger_archetype: gloom_stalker`. The base class is the SRD 5.2 ranger overlay (`templates/rulesets/5e-2024/char_classes/ranger.yml`: half-caster slots rounding up, Favored Enemy free Hunter's Mark casts, Roving, Tireless). The subclass uses the generic class-YAML blocks in `natural20/utils/class_mechanics.py`:

| Feature | Mechanic |
|---|---|
| Gloom Stalker spells (always prepared) | `subclasses.gloom_stalker.spells` |
| Dread Ambusher: initiative bonus | `initiative_bonuses` (`ability_mod:wisdom`) |
| Dread Ambusher: Ambusher's Leap | `first_turn_movement` (+10 ft) |
| Dread Ambusher: Dreadful Strike | `attack_options` (on hit, psychic 2d6 then 2d8, WIS mod uses per long rest, once per turn) |
| Umbral Sight | `senses` (darkvision 60 ft, or +60 ft, plus `evade_darkvision`) |
| Iron Mind | Feature marker; the extra saving throw proficiency comes from the sheet |
| Stalker's Flurry | `variants` on Dreadful Strike: Sudden Strike (`follow_up_attack`) and Mass Fear (`save.radius: 10`) |

Simplifications:

- Sudden Strike's extra attack is offered as a free attack action that lasts until your next turn starts, not as an attack made right away.
- Mass Fear also targets your allies within 10 ft of the target, as the feature's wording says.
- Shadowy Dodge (level 15) is listed as a feature but isn't implemented.

## Archfey Patron (warlock subclass)

Sheet key `otherworldly_patron: archfey_patron`. The base class is the SRD 5.2 warlock overlay (`templates/rulesets/5e-2024/char_classes/warlock.yml`).

| Feature | Mechanic |
|---|---|
| Archfey spells (always prepared) | `subclasses.archfey_patron.spells` |
| Steps of the Fey: free Misty Step, CHA mod per long rest | `free_casts` with the `steps_of_the_fey` pool |
| Steps of the Fey: Refreshing Step (1d10 temp HP), Taunting Step | `spell_riders` (`natural20/utils/spell_riders.py`, `natural20/utils/taunt.py`) |
| Misty Escape: Misty Step as a reaction when hit | `reaction_casts` (`natural20/utils/reaction_casts.py`) |
| Misty Escape: Disappearing Step, Dreadful Step | `spell_riders` |
| Beguiling Defenses: immune to charmed | `condition_immunities` |
| Beguiling Defenses: halve damage, attacker takes psychic damage | `hit_reactions` (pool, or spend a spell slot when it's empty) |
| Bewitching Magic (level 14) | Listed as a feature, not implemented |

## Spells

- **Summon Fiend.** `SummonSpiritSpell` with a `summon_spirit` block. You pick a demon, devil or yugoloth spirit, which scales with the slot level and acts right after you. It disappears when your concentration ends or when it drops to 0 HP (which ends the spell). The demon's Death Throes also go off when the spell ends, the devil has Devil's Sight, and the yugoloth can teleport 30 ft after each Claws attack (`teleport_after_attack`). Tokens are in `assets/token_fiendish_spirit_*.png`. Climb speed isn't modelled.
- **Blade Ward (2024).** Concentration. Attackers subtract 1d4 from attack rolls against you (`blade_ward.mode: attack_penalty`).

Attribution: Player's Handbook (2024). Not part of the Systems Reference Document. Descriptions are paraphrased.
