# Release audit — n20-webapp public readiness

Scan of the tracked contents (and git history) of the `n20-webapp` submodule,
2026-11-24. 14k files on disk; ~1,9k tracked in git; 92 MB history pack.
Runtime state (`saves/`, `llm_logs/`, `flask_session/`, `.env`, `.ai.yaml`) is
correctly gitignored and does **not** ship.

Statuses: 🚫 release-blocker · ⚠️ flag for legal/review · 🧹 hygiene fix · ℹ️ note

## 1. Copyright / trademark — flag for review

| # | Item | Where | Notes |
|---|------|-------|-------|
| 1.1 🚫 | **"Strahd von Zarovich" campaign-character fixtures** | `tests/webapp/test_voice_framework.py` (npc_uid `npc_strahd_von_zarovich`, label "Strahd"), `tests/webapp/test_end_of_turn_animations.py:19` (`'npc_strahd'`) | Strahd is a WotC character (Curse of Strahd). This also violates our own rule (AGENTS.md: campaign-specific names must not appear in the core webapp). Rename to a generic vampire count (e.g. `npc_count_von_undying`). Test-local strings only — safe rename. |
| 1.2 ⚠️ | **"Forgotten Realms" as setting fixture** | `tests/webapp/test_entity_rag_handler.py:1847,1854` (`'world': 'Forgotten Realms'`) | WotC trademark for a campaign setting. Swap to a generic homebrew world name. |
| 1.3 ⚠️ | **"D&D Beyond" importer feature** | `webapp/dndbeyond_import.py`, `webapp/blueprints/character.py:705-735`, `webapp/app.py:1301-1338` | "D&D Beyond" is a WotC/Hasbro service mark. Nominative reference to a user's own character URL is generally tolerated, but: add a "not affiliated with / endorsed by Wizards of the Coast" disclaimer, and confirm the scraping flow matches DDB's terms before publicizing the feature. Consider naming it "character sheet URL import" in UI. |
| 1.4 ⚠️ | **D&D trademark mentions throughout** | prompts (`webapp/prompts/*.txt`), test fixtures, comments (~20 places) | Nominative use ("a D&D 5e game") is standard practice, but add the customary notice to the README, e.g. *"D&D, Dungeons & Dragons and related marks are trademarks of Wizards of the Coast LLC. This project is not affiliated with or endorsed by Wizards of the Coast."* |
| 1.5 ⚠️ | **Audio asset provenance unknown** | `webapp/static/assets/goblin_ambush.mp3` (only shipped audio) | Music is high-risk. Confirm it is self-generated/owned or replace (e.g. Kevin MacLeod CC-BY with attribution, or generated). |
| 1.6 ⚠️ | **757 bundled images** | `webapp/static/assets/`, `webapp/static/spells/`, `static/client-3d/assets/` | Appear to be locally generated via the n20 image-gen pipeline (generic SRD-style names, no official art file names found) — but provenance is undocumented. Add an `ASSET_LICENSES`/attribution note stating they are machine-generated for this project. |
| 1.7 🧹 | **Third-party library attribution** | `webapp/static/libs/` | Bootstrap (MIT), jQuery (MIT), Socket.IO (MIT) carry headers — fine. **Font Awesome Free 6.0.0 icons are CC BY 4.0** and legally require an attribution notice in the app/about page or README. Bootstrap 3's Glyphicons fonts: MIT/SIL — fine. |
| 1.8 🧹 | **No SRD attribution in this repo** | webapp README / any `*.md` | SRD 5.2 text is CC BY 4.0 and is rendered in the UI. The engine repo has `docs/ATTRIBUTION_SRD.md`; the standalone webapp repo should carry or link its own notice. |
| 1.9 🚫 | **No LICENSE in n20-webapp** | repo root (`git ls-files` → zero license files) | Without an explicit license, defaults to all-rights-reserved; a public release needs `LICENSE.md` (match the engine repo's license) + a `license` field in `pyproject.toml`. |
| 1.10 ℹ️ | **Adjacent-repo exposure (out of scope but surfaced by this scan)** | referenced from tracked manifests | The asset manifests point at `user_levels/death_house/assets/cos-cover-4k.jpg`, which is very likely official *Curse of Strahd* cover art. If the campaigns repo is ever published, that file must go. |

## 2. Secrets & personal data

* ✅ No API keys, tokens, `.env`, or `.ai.yaml` in **tracked files or git history**
  (verified by pickaxe search for `ghp_`, `sk-`, `ngrok_authtoken`, `.env` paths).
* 🚫 **Tracked build caches leak developer machine layout**:
  `webapp/scripts/.asset_manifest.json`, `.asset_manifest_assets.json`,
  `.asset_manifest_campaigns.json`, `.asset_manifest_ui.json` contain absolute
  paths (`/home/jedld/workspace/...`) and a full inventory of private campaign
  assets (portraits, `ddb-*` character sheets, Strahd art). They are outputs of
  `optimize_web_assets.py` / `optimize_images`. → Untrack all four, add
  `.asset_manifest*.json` and `*.egg-info/` to `.gitignore`. (History still
  contains them; decide whether a fresh-history release is wanted, since the
  pack is only 92 MB.)
* ⚠️ **Personal infrastructure in CORS defaults** —
  `webapp/blueprints/helpers/cors_config.py`: `http://jedld-lab:5001`,
  `https://0ad1d39fb719.ngrok.app` (dead ngrok tunnels can be reclaimed by
  strangers → allowed-origin hijack), `natural20-alb-1402295348.us-east-1.elb.amazonaws.com`.
  Remove all three; keep localhost + ngrok wildcards, require `CORS_ORIGINS` in prod.
* ℹ️ **Git history authors** include `joseph.dayo@gmail.com`. Rewrite
  (`git filter-repo`) only if desired — most projects keep author emails.

## 3. Security configuration

| # | Item | Where | Notes |
|---|------|-------|-------|
| 3.1 🚫 | **Hardcoded Flask `SECRET_KEY` literal** | `webapp/app.py:152` | With the source public, anyone can forge signed session cookies → instant DM impersonation. Use `os.environ.get('N20_SECRET_KEY') or secrets.token_hex(32)` (persist across restarts via file or env; document). Tests are unaffected. |
| 3.2 ⚠️ | **Production CORS default contains `"*"` alongside `supports_credentials=True`** | `cors_config.py:23-31` + `app.py:150` | Permissive + credentialed CORS is either ineffective or dangerously wide depending on client. Ship an empty/erroring default in prod unless `CORS_ORIGINS` is set. |
| 3.3 ⚠️ | **Aged JS libraries shipped** | `webapp/static/libs/` | jQuery **3.2.1** is referenced by templates (`character_builder.html`, `combat_selection`, `combat-log`, …) and has known XSS CVEs (CVE-2019-11324, CVE-2020-11022/23). Three jQuery and two Bootstrap major versions bundled. Dedupe + upgrade before exposing a public instance. |
| 3.4 ℹ️ | Dev scaffolds login `dm`/`admin` | `start_web.sh --new` help text (scaffold lives in engine `campaign_scaffold.py`) | Fine for local dev; print a "change the default DM password" warning when serving non-localhost. |
| 3.5 ✅ | Debug mode off | `app.py:6254` `debug=False`; `FLASK_DEBUG` env-gated | Good. |

## 4. Usability / polish

| # | Item | Where | Fix |
|---|------|-------|-----|
| 4.1 🧹 | Placeholder broken link `https://github.com/your-org/natural_20.py/...` | `README.md:81` | Point to the real engine repo URL. |
| 4.2 🧹 | Install snippet assumes sibling checkout `pip install -e ../natural_20.py` | `README.md:12` | Fine, but state the engine is on PyPI (or add the `git+…` install line) for standalone users. |
| 4.3 ℹ️ | `package.json` has `"private": true`, no license field | root `package.json` | Fine for an app (not an npm lib); just confirm intent, add license for clarity. |
| 4.4 🧹 | `pyproject.toml` lacks `license`, `authors`, `classifiers` | `pyproject.toml` | Cosmetic packaging polish. |
| 4.5 ✅ | `webapp/env.example` is comprehensive; standalone `start_web.sh` exists at repo root; parity baselines in `plans/artifacts/` are real test infrastructure | — | Keep. |
| 4.6 🧹 | `.gitignore` misses `*.egg-info/` and `.asset_manifest*.json` | root `.gitignore` | Add (see 2). |
| 4.7 ℹ️ | Repo working copy currently has large uncommitted changes from active development (submodule is dirty) | — | Commit/ship in-progress work or stash before tagging the public release. |

## Suggested pre-release checklist

Status as of 2026-11-24 remediation (engine `master`, n20-webapp `master`,
campaigns `master`):

1. ✅ Rename Strahd/Forgotten-Realms fixtures (1.1, 1.2) — done, plus the
   "Forgotten Realms backdrop" line in `entity_rag_handler.py` itself.
2. ✅ `LICENSE.md` + `pyproject` license field; SRD/D&D/trademark notices in
   the webapp README (1.4, 1.8, 1.9).
3. ✅ Untracked `.asset_manifest*.json`, extended `.gitignore` (2, 4.6).
4. ✅ `SECRET_KEY` now env/random (3.1); CORS defaults cleaned (2, 3.2).
5. ✅ README placeholder links fixed (4.1).
6. ✅ D&D Beyond importer **removed from both public repos** and relocated to
   `user_levels/private_scripts/dndbeyond_import/` (1.3; engine copies —
   `scripts/beyond_importer.py`, its tests/fixtures and
   `docs/DND_BEYOND_IMPORT.md` — moved as well). Shipped audio
   `goblin_ambush.mp3` deleted (1.5).
7. ⚠️ Still open: generated-image provenance note for the 757 bundled
   images (1.6), jQuery 3.2.1 / Bootstrap 3 upgrade (3.3), history hygiene
   decisions (gmail author, manifest blobs), and `natural20.egg-info/`
   being tracked in the engine repo.
8. (Optional) Decide on history hygiene: gmail author email, manifest blobs.
