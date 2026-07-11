# Test Memory Diagnostics

Tools and workflows for running tests safely, diagnosing memory issues, and auto-fixing failures.

## Quick Start

### Run tests safely (memory-isolated)

```bash
# Run all tests with per-test memory profiling
python scripts/run_tests_with_memory_monitor.py --mem-profile

# Run tests in isolated subprocesses (prevents OOM cascade)
python scripts/run_tests_with_memory_monitor.py --isolated

# Run with memory threshold alerting (default 500MB)
python scripts/run_tests_with_memory_monitor.py --mem-profile --mem-threshold 500

# Run specific test file
python scripts/run_tests_with_memory_monitor.py tests/test_battle.py

# Run with auto-fix and auto-xfail for persistent failures
python scripts/run_tests_with_memory_monitor.py --auto-fix --auto-xfail
```

### Diagnose memory hogs

```bash
# Run diagnostic on all tests (safe, isolated subprocesses)
python scripts/diagnose_memory_hogs.py

# Filter by keyword
python scripts/diagnose_memory_hogs.py -k "test_spell"

# Save report to JSON
python scripts/diagnose_memory_hogs.py --report test_memory_profiles/report.json

# Custom batch size and memory limit
python scripts/diagnose_memory_hogs.py --batch 5 --limit-mb 4096
```

### Test sweep (batch runner)

```bash
# Run tests in batches with auto-fix
python scripts/test_sweep.py --batch-size 10 --auto-fix --auto-xfail

# Parallel batch execution
python scripts/test_sweep.py --parallel 4 --batch-size 5

# Generate report
python scripts/test_sweep.py --report test_sweep_report.json
```

### pytest-memprof-plugin (direct pytest usage)

```bash
# Enable per-test memory profiling
pytest --mem-profile

# Memory threshold + report
pytest --mem-profile --mem-threshold 300 --mem-report mem_report.json

# Auto-mark memory hogs as xfail
pytest --mem-profile --mem-auto-xfail

# Generate baseline
python scripts/pytest_memprof_plugin.py --generate-baseline tests/
```

## Tool Reference

### `scripts/run_tests_with_memory_monitor.py`

Full-featured pytest runner with:
- Background RSS/VMS monitoring via `psutil`
- Per-test memory profiling via `tracemalloc`
- Isolated subprocess mode for OOM containment
- Auto-fix strategies for common failures
- JSON report output

| Flag | Description |
|---|---|
| `--mem-profile` | Enable per-test memory profiling |
| `--isolated` | Run each test in isolated subprocess |
| `--max-mem-pct <N>` | Alert at N% system memory (default: 85) |
| `--max-mem-mb <N>` | Hard limit per subprocess (MB) |
| `--auto-fix` | Attempt automatic fixes |
| `--auto-xfail` | Mark persistent failures as xfail |
| `--group-by-memory` | Sort tests by memory usage |
| `--report-file <path>` | Save JSON report |

### `scripts/diagnose_memory_hogs.py`

Identifies memory-hungry tests by running each in isolation:
- Collects per-test memory delta (RSS before/after)
- Tracks top allocation sites via `tracemalloc`
- Outputs sorted report of top N consumers
- Detects timeouts (>120s per test)

| Flag | Description |
|---|---|
| `--top <N>` | Show top N consumers (default: 20) |
| `--limit-mb <N>` | Memory limit per subprocess (default: 4096) |
| `--batch <N>` | Tests per batch (default: 5) |
| `--report <path>` | Save JSON report |

### `scripts/test_sweep.py`

Batch runner with parallel execution and auto-fix:
- Runs tests in configurable batch sizes
- Parallel batch execution via ThreadPoolExecutor
- Auto-fix strategies for ImportError, FileNotFoundError, AssertionError
- Auto-xfail for persistent failures

| Flag | Description |
|---|---|
| `--batch-size <N>` | Tests per batch (default: 10) |
| `--parallel <N>` | Parallel workers (0 = sequential) |
| `--auto-fix` | Attempt fixes |
| `--auto-xfail` | Mark as xfail |

### `scripts/pytest_memprof_plugin.py`

Standalone pytest plugin for memory profiling:
- `pytest_configure` hook enables tracemalloc
- `pytest_runtest_setup/teardown` hooks capture snapshots
- `pytest_sessionfinish` exports JSON report

## Auto-Fix Strategies

| Error Type | Strategy |
|---|---|
| `ImportError` / `ModuleNotFoundError` | Suggests `pip install` or path fix |
| `AttributeError` | Suggests API verification |
| `FileNotFoundError` | Suggests fixture path check |
| `AssertionError` | Extracts failed assertion |
| `KeyError` | Suggests default value or YAML fix |

## Memory Baseline Comparison

Generate a baseline, then detect regressions:

```bash
# Generate baseline
python scripts/pytest_memprof_plugin.py --generate-baseline tests/

# Detect regressions
pytest --mem-profile --mem-baseline test_memory_profiles/baseline.json
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `N20_MEM_THRESHOLD_MB` | 500 | Alert threshold |
| `N20_MEM_TOP_FRAMES` | 10 | Top allocations to show |
| `N20_MEM_BASELINE` | - | Baseline JSON path |
| `N20_MEM_ISOLATED` | 0 | Enable isolation |

## Troubleshooting

## Recent Fixes (2026-07-11)

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| `test_spell_action.py` — 12 failures | `event_manager.py:441` `spell_buf` handler expected `event['spell'].name` but `absorb_elements_spell.py` passes a string | Changed to `event['spell'].name if hasattr(event['spell'], 'name') else event['spell']` |
| `test_rest_restrictions.py` — 4 failures | `fighter.py:92,139` referenced `self.martial_archetype` which doesn't exist on non-Fighter entities | Changed to `getattr(self, 'martial_archetype', None)` |
| `test_lay_on_hands_action.py` — 1 failure | Autobuild included self-target when paladin at full HP, causing "Target cannot benefit" error | Added `exclude_self` param in `build_map()` when `source.hp() >= source.max_hp()` |

## Changelog

### v2 — 2026-07-11
- Added `exclude_self` conditional in [`LayOnHandsAction.build_map()`](natural20/actions/lay_on_hands_action.py:52-69) to prevent full-HP self-target from failing autobuild.
- Fixed [`EventLogger` spell_buf handler](natural20/event_manager.py:441) to handle both string and object spell references.
- Fixed [`Fighter` mixin](natural20/entity_class/fighter.py:92,139) to use `getattr()` for `martial_archetype`.

## Troubleshooting

### Tests crash with OOM

1. Run with isolation: `python scripts/run_tests_with_memory_monitor.py --isolated`
2. Diagnose: `python scripts/diagnose_memory_hogs.py tests/test_suspect.py`
3. Run in small batches: `python scripts/diagnose_memory_hogs.py --batch 1`

### Slow tests

1. Check `diagnostic_report.json` for timeout tests
2. Add `--timeout` marker or skip with `@pytest.mark.slow`

### Memory regressions

1. Run baseline on a known-good commit
2. Compare current run: `pytest --mem-profile --mem-baseline baseline.json`
3. Check `top_allocations` in report for leak sources
