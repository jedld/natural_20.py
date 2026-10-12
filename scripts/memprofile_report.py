"""Summarize JSONL written by scripts/pytest_memprofile.py.

    python scripts/memprofile_report.py /tmp/memprof [--top 25]
"""

import argparse
import glob
import json
import os
from collections import defaultdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    ends, unfinished, worker_peak = [], [], {}
    for path in sorted(glob.glob(os.path.join(args.out_dir, "*.jsonl"))):
        started = {}
        for line in open(path):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec["ev"] == "start":
                started[rec["id"]] = rec
            else:
                started.pop(rec["id"], None)
                ends.append(rec)
                worker_peak[rec["w"]] = max(worker_peak.get(rec["w"], 0), rec["peak"])
        unfinished.extend(started.values())

    if unfinished:
        print("== Tests started but never finished (killed / OOM / timeout) ==")
        for rec in unfinished:
            print(f"  [{rec['w']}] {rec['id']}  (rss at start {rec['rss']} MB)")
        print()

    def table(title, key, fmt):
        print(f"== {title} ==")
        for rec in sorted(ends, key=lambda r: r[key], reverse=True)[: args.top]:
            print(f"  {fmt(rec)}  {rec['id']}")
        print()

    table("Slowest tests", "dur", lambda r: f"{r['dur']:8.2f}s")
    table("Largest peak RSS raise", "peak_raise",
          lambda r: f"+{r['peak_raise']:7.1f} MB (peak {r['peak']:.0f})")
    table("Largest retained RSS growth", "rss_delta",
          lambda r: f"{r['rss_delta']:+8.1f} MB")

    by_file = defaultdict(lambda: [0.0, 0.0, 0])
    for rec in ends:
        f = rec["id"].split("::")[0]
        by_file[f][0] += rec["dur"]
        by_file[f][1] += rec["rss_delta"]
        by_file[f][2] += 1
    print("== Files by total time ==")
    for f, (dur, delta, n) in sorted(by_file.items(), key=lambda kv: kv[1][0], reverse=True)[: args.top]:
        print(f"  {dur:8.1f}s  {delta:+8.1f} MB retained  {n:4d} tests  {f}")
    print()
    print("== Retained growth by file ==")
    for f, (dur, delta, n) in sorted(by_file.items(), key=lambda kv: kv[1][1], reverse=True)[: args.top]:
        print(f"  {delta:+8.1f} MB  {dur:8.1f}s  {n:4d} tests  {f}")
    print()
    print("== Per-worker peak RSS ==")
    for w, p in sorted(worker_peak.items(), key=lambda kv: kv[1], reverse=True):
        print(f"  {w}: {p:.0f} MB")
    total = sum(worker_peak.values())
    print(f"  sum of worker peaks: {total:.0f} MB across {len(worker_peak)} workers")
    print(f"\n{len(ends)} tests finished, {len(unfinished)} unfinished")


if __name__ == "__main__":
    main()
