# n20-campaigns — Natural 20 campaign content

User-authored campaigns for the [Natural 20](https://github.com/your-org/natural_20.py) engine and VTT.

Each top-level folder is one campaign (must contain `index.json` and `game.yml`).

## Use with the webapp

```bash
export N20_CAMPAIGNS_DIR=/path/to/n20-campaigns
cd ../n20-webapp
./start_web.sh wild_sheep_chase
```

Or set an absolute path:

```bash
TEMPLATE_DIR=/path/to/n20-campaigns/wild_sheep_chase ./start_web.sh
```

## SRD / shared rules data

Spells, items, and class definitions that ship with the engine live in the **engine**
repository under `templates/`. Campaign YAML files inherit from those resources via
`inherit:` directives — you do not need to duplicate SRD content here.

## Layout (per campaign)

```
my_campaign/
  index.json          # webapp bootstrap (title, map, logins, soundtracks)
  game.yml            # session config, map list, campaign flags
  maps/
  npcs/
  characters/
  items/              # campaign-specific overrides only
  assets/
  locales/
```

## Tooling

Campaign generator and asset scripts remain in the engine repo (`scripts/`). Run them
against this checkout:

```bash
python ../natural_20.py/scripts/validate_campaign.py my_campaign
python ../natural_20.py/scripts/generate_campaign_assets.py --campaign .
```

## Git policy

- Commit YAML, JSON, and small assets.
- Large generated audio/images: use Git LFS or external storage as your team prefers.
- Do **not** commit runtime saves (`saves/` is gitignored).
