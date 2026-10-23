# GitHub Actions CI

Workflows live in [`.github/workflows/`](../.github/workflows):

| Workflow | What it runs |
|---|---|
| `python-tests.yml` → `test` job | `pytest tests -q --ignore=tests/webapp --dist=worksteal -n auto --timeout=240 --timeout-method=thread --durations=20` (engine) |
| `python-tests.yml` → `webapp` job | `pytest n20-webapp/tests/webapp -q --dist=worksteal -n 1` |
| `js-tests.yml` | `npx jest` in `n20-webapp/` |

## Private submodules

Both CI jobs check out the private submodules (`n20-webapp`, `user_levels`)
with the composite action [`.github/actions/submodule-checkout/`](../.github/actions/submodule-checkout/action.yml),
which uses **per-repo read-only SSH deploy keys** stored as secrets:

- `N20_WEBAPP_SSH_KEY` → `jedld/n20-webapp` deploy key (read-only)
- `N20_CAMPAIGNS_SSH_KEY` → `jedld/n20-campaigns` deploy key (read-only)

Deploy keys are added under *Settings → Deploy keys* of each submodule repo.
A single account-wide key is deliberately not used (read-only blast radius per repo).
`user_levels` additionally runs `git lfs install && git -C user_levels lfs pull`
(campaign audio).

## Engine job sizing

The engine suite is wide (~2700 tests, no single test over ~60 s) and GitHub
runner speed varies a lot between runs: pytest wall time has ranged from
~31 min to ~47 min on the 4-vCPU `ubuntu-latest` runners. For that reason:

- The job runs with **60 min** `timeout-minutes` (observed worst case + margin).
- `OMP_NUM_THREADS`/`OPENBLAS_NUM_THREADS`/`MKL_NUM_THREADS`/`NUMEXPR_NUM_THREADS`
  are pinned to `1`: without it, each of the 4 xdist workers spawns a
  multi-threaded OpenBLAS pool and the thread pools thrash the 4 vCPUs
  (~25% wall-time cut locally when pinned).
- `pytest-timeout` is in `requirements.txt` and the run passes
  `--timeout=240 --timeout-method=thread --durations=20`, so a pathologically
  slow test fails **by name with a traceback** instead of silently burning the
  whole job timeout, and the slowest tests are listed on completion.

## Webapp job / env determinism

CI runners have no `n20-webapp/webapp/.env`, while developer machines do
(`webapp/app.py` calls `load_dotenv` at import). The test harness pins the
relevant differences in `n20-webapp/tests/webapp/conftest.py`:

- `TTS_ENABLED=1` is set before the per-test env snapshot: the committed
  route-inventory / endpoint-name baselines include the `tts.*` routes, and
  `webapp.app` only registers the TTS blueprint when the flag is set at
  *import* time (a parity test setting it later is too late — other modules
  already imported the app). `TTS_PROVIDER`/`TTS_DEVICE` stay unpinned;
  `app.py` already defaults to the mock provider/cpu and `test_tts_manager`
  asserts those library defaults.
- The `conftest` snapshots the shell env before any test module import and
  restores it around every test, so a local `.env` cannot leak into tests.
- `test_cosyvoice_provider` skips its reference-audio test when
  `third_party/CosyVoice` is not checked out: that checkout is a **local,
  untracked** directory (not in git), so clean CI runners never have it.

Related docs: `GITLAB_CI.md` (legacy self-hosted GitLab pipeline),
`WEBAPP_BLUEPRINTS.md` (parity harness + `scripts/generate_baseline_artifacts.py`).
