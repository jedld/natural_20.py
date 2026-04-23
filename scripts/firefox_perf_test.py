"""Browser-specific perf + console-error probe using Playwright Firefox.

Logs in as DM, loads the map page, runs /update benchmarks, and dumps
console messages, network errors, and Server-Timing breakdowns.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter

from playwright.sync_api import sync_playwright


def run(browser_name: str, base_url: str, username: str, password: str) -> dict:
    results: dict = {"browser": browser_name, "base_url": base_url}
    console_msgs: list[dict] = []
    page_errors: list[str] = []
    failed_requests: list[dict] = []
    response_log: list[dict] = []

    with sync_playwright() as p:
        browser_type = getattr(p, browser_name)
        browser = browser_type.launch(headless=True)
        context = browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        page.on("console", lambda msg: console_msgs.append(
            {"type": msg.type, "text": msg.text[:300], "location": str(msg.location)}
        ))
        page.on("pageerror", lambda exc: page_errors.append(str(exc)[:500]))
        page.on("requestfailed", lambda req: failed_requests.append(
            {"url": req.url, "method": req.method, "failure": req.failure}
        ))
        page.on("response", lambda resp: response_log.append(
            {"url": resp.url, "status": resp.status,
             "ct": resp.headers.get("content-type", ""),
             "cl": resp.headers.get("content-length", ""),
             "ce": resp.headers.get("content-encoding", ""),
             "st": resp.headers.get("server-timing", "")}
        ))

        # 1. Login
        t0 = time.perf_counter()
        page.goto(f"{base_url}/login", wait_until="domcontentloaded", timeout=30000)
        page.fill("input[name='username']", username)
        page.fill("input[name='password']", password)
        page.click("button[type='submit'], input[type='submit']")
        page.wait_for_url(f"{base_url}/", timeout=15000)
        login_ms = round((time.perf_counter() - t0) * 1000, 1)

        # 2. Initial nav timing
        page.goto(f"{base_url}/?perf=1", wait_until="load", timeout=30000)
        nav = page.evaluate(
            """() => {
              const t = performance.getEntriesByType('navigation')[0] || {};
              return {
                ttfb: Math.round(t.responseStart - t.requestStart),
                dom_content: Math.round(t.domContentLoadedEventEnd - t.startTime),
                load: Math.round(t.loadEventEnd - t.startTime),
                transferSize: t.transferSize, encodedBodySize: t.encodedBodySize,
                decodedBodySize: t.decodedBodySize,
              };
            }"""
        )

        # 3. /update benchmark (10 sequential)
        update_samples = page.evaluate(
            """async () => {
              const out = [];
              for (let i = 0; i < 10; i++) {
                const t = performance.now();
                const r = await fetch('/update?x=3&y=3');
                await r.text();
                out.push({
                  wall_ms: Math.round(performance.now() - t),
                  st: r.headers.get('server-timing'),
                  cl: r.headers.get('content-length'),
                  ce: r.headers.get('content-encoding'),
                  status: r.status,
                });
              }
              return out;
            }"""
        )

        # 4. Concurrency probe
        conc = page.evaluate(
            """async () => {
              const t0 = performance.now();
              const arr = await Promise.all(
                Array.from({length: 5}, () => fetch('/update?x=3&y=3').then(r => r.text()))
              );
              return { wall_ms: Math.round(performance.now() - t0), n: arr.length };
            }"""
        )

        # 5. Cached endpoints
        cache_check = page.evaluate(
            """async () => {
              const get = async (url) => {
                const t = performance.now();
                const r = await fetch(url);
                await r.text();
                return { url, wall_ms: Math.round(performance.now() - t), status: r.status, st: r.headers.get('server-timing') };
              };
              return [
                await get('/available_npcs'),
                await get('/available_npcs'),
                await get('/available_objects'),
                await get('/available_objects'),
              ];
            }"""
        )

        browser.close()

    # Aggregate findings
    err_status_counts = Counter(r["status"] for r in response_log if r["status"] >= 400)
    failed_urls = [r["url"] for r in response_log if r["status"] >= 400][:20]

    results.update({
        "login_ms": login_ms,
        "nav": nav,
        "update_samples": update_samples,
        "concurrent5": conc,
        "cache_check": cache_check,
        "console_errors": [m for m in console_msgs if m["type"] in ("error", "warning")][:30],
        "page_errors": page_errors[:20],
        "failed_requests": failed_requests[:20],
        "http_error_status_counts": dict(err_status_counts),
        "http_error_sample_urls": failed_urls,
        "response_count": len(response_log),
    })
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", default="firefox", choices=("firefox", "chromium", "webkit"))
    parser.add_argument("--url", default="http://localhost:5001")
    parser.add_argument("--user", default="dm")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--out", default=None, help="Write JSON to this path")
    args = parser.parse_args()

    res = run(args.browser, args.url, args.user, args.password)
    payload = json.dumps(res, indent=2, default=str)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(payload)
    print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
