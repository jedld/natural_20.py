# n20-webapp — Natural 20 VTT (Flask + SocketIO)

Flask virtual tabletop that drives the [`natural20`](../natural_20.py) engine.

This repository is **standalone**: it does not vendor the engine or campaign data.
Install them separately:

```bash
# Engine (SRD templates + simulation core)
pip install -e ../natural_20.py

# Webapp
pip install -e ".[dev]"
npm install
```

## Campaign data

Campaigns live in a separate repository (for example `n20-campaigns`). Point the
webapp at a campaign directory with `TEMPLATE_DIR` or `N20_CAMPAIGNS_DIR`:

```bash
export N20_CAMPAIGNS_DIR=../n20-campaigns
./start_web.sh wild_sheep_chase
# equivalent:
# TEMPLATE_DIR=../n20-campaigns/wild_sheep_chase ./start_web.sh
```

Bundled SRD YAML (spells, items, classes) ships with the **engine** package under
`templates/` and is merged automatically when a campaign file inherits from SRD.

## Run (development)

```bash
./start_web.sh [campaign_slug_or_path]
```

Defaults to `../templates` (engine checkout) when no campaign is passed.

Production:

```bash
N20_USE_GUNICORN=1 ./start_web.sh ../n20-campaigns/wild_sheep_chase
```

## Tests

```bash
export TEMPLATE_DIR=../natural_20.py/templates
pytest tests/webapp -q
npm test
```

## Docker

```bash
docker build -t n20-webapp .
docker run --env-file webapp/.env \
  -e TEMPLATE_DIR=/campaigns/wild_sheep_chase \
  -v /path/to/n20-campaigns:/campaigns:ro \
  -p 5001:5001 n20-webapp
```

## Layout

| Path | Purpose |
|------|---------|
| `webapp/` | Flask app, blueprints, static assets, Jinja templates |
| `tests/webapp/` | HTTP/SocketIO parity tests |
| `scripts/minify.mjs` | JS asset pipeline (`npm run build:assets`) |

See also: [Repository split guide](https://github.com/your-org/natural_20.py/blob/master/docs/REPOSITORY_SPLIT.md) in the engine repo.
