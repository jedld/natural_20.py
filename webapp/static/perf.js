/* Lightweight client-side performance instrumentation.
 *
 * Activation:
 *   - Append ?perf=1 to the URL, OR
 *   - Run localStorage.setItem('vtt.perf','1') in devtools, OR
 *   - Press Ctrl+Shift+P at any time to toggle the overlay.
 *
 * No-op when inactive. Captures:
 *   - Navigation timing milestones (DNS/TCP/TTFB/DOMContentLoaded/load)
 *   - $.ajax round-trip stats per URL (count, avg, p95, max, last)
 *   - Socket.IO inbound event rate (per event name)
 *   - Long tasks (>50ms) and per-second FPS samples
 *
 * Exposes window.__perf for console inspection:
 *   __perf.snapshot()          // print summary
 *   __perf.routes()            // raw route stats
 *   __perf.events()            // raw socket event counts
 *   __perf.show() / __perf.hide() / __perf.toggle()
 */
(function () {
  'use strict';

  function isEnabled() {
    try {
      if (location.search.indexOf('perf=1') !== -1) return true;
      return localStorage.getItem('vtt.perf') === '1';
    } catch (e) {
      return false;
    }
  }

  var enabled = isEnabled();

  // -------- core stats ---------
  var routes = Object.create(null); // url -> {count, total, max, last, samples[]}
  var events = Object.create(null); // event name -> {count, total, max, last, lastTs}
  var longTasks = { count: 0, totalMs: 0, max: 0 };
  var fps = { last: 0, samples: [] };
  var nav = null;

  function addRoute(url, ms, status) {
    var key = url.split('?')[0];
    var b = routes[key];
    if (!b) { b = routes[key] = { count: 0, total: 0, max: 0, last: 0, samples: [], errors: 0 }; }
    b.count++;
    b.total += ms;
    if (ms > b.max) b.max = ms;
    b.last = ms;
    if (status >= 400) b.errors++;
    if (b.samples.length >= 100) b.samples.shift();
    b.samples.push(ms);
  }

  function p95(arr) {
    if (!arr.length) return 0;
    var s = arr.slice().sort(function (a, b) { return a - b; });
    return s[Math.min(s.length - 1, Math.floor(s.length * 0.95))];
  }

  // -------- $.ajax wrapping (covers Utils.ajaxGet and ajaxPost) --------
  function instrumentJQuery() {
    if (typeof window.jQuery === 'undefined' || !jQuery.ajaxPrefilter) {
      return setTimeout(instrumentJQuery, 100);
    }
    jQuery.ajaxPrefilter(function (options) {
      options._perfStart = (window.performance && performance.now) ? performance.now() : Date.now();
      var origComplete = options.complete;
      options.complete = function (jqXHR, textStatus) {
        try {
          var t1 = (window.performance && performance.now) ? performance.now() : Date.now();
          var elapsed = t1 - options._perfStart;
          addRoute(options.url || '(unknown)', elapsed, jqXHR ? jqXHR.status : 0);
        } catch (e) { /* swallow */ }
        if (typeof origComplete === 'function') {
          try { origComplete.apply(this, arguments); } catch (e) { /* swallow */ }
        }
      };
    });
  }

  // -------- Socket.IO inbound event tracking --------
  // Hook by patching io() — both legacy `io(opts)` and `io(url, opts)` forms.
  function instrumentSocketIO() {
    if (typeof window.io === 'undefined') {
      return setTimeout(instrumentSocketIO, 100);
    }
    var origIo = window.io;
    function wrap(socket) {
      if (!socket || socket.__perfWrapped) return socket;
      socket.__perfWrapped = true;
      // socket.io v3+ supports onAny.
      if (typeof socket.onAny === 'function') {
        socket.onAny(function (event /*, ...args */) {
          var b = events[event];
          var now = (window.performance && performance.now) ? performance.now() : Date.now();
          if (!b) { b = events[event] = { count: 0, lastTs: now, ratePerSec: 0 }; }
          b.count++;
          var dt = now - b.lastTs;
          if (dt > 0) {
            // Exponential moving average of inter-arrival -> rate per second.
            var inst = 1000 / dt;
            b.ratePerSec = b.ratePerSec ? b.ratePerSec * 0.85 + inst * 0.15 : inst;
          }
          b.lastTs = now;
        });
      }
      return socket;
    }
    window.io = function () {
      var s = origIo.apply(window, arguments);
      try { wrap(s); } catch (e) { /* swallow */ }
      return s;
    };
    // Preserve any properties on the original io (managers, etc).
    for (var k in origIo) {
      try { window.io[k] = origIo[k]; } catch (e) { /* readonly */ }
    }
  }

  // -------- Long task observer + FPS sampler --------
  function instrumentLongTasks() {
    if (typeof PerformanceObserver === 'undefined') return;
    try {
      var po = new PerformanceObserver(function (list) {
        list.getEntries().forEach(function (e) {
          longTasks.count++;
          longTasks.totalMs += e.duration;
          if (e.duration > longTasks.max) longTasks.max = e.duration;
        });
      });
      po.observe({ entryTypes: ['longtask'] });
    } catch (e) { /* not all browsers support longtask */ }
  }

  function instrumentFPS() {
    var frames = 0;
    var lastReport = (window.performance && performance.now) ? performance.now() : Date.now();
    function loop(now) {
      frames++;
      if (now - lastReport >= 1000) {
        fps.last = Math.round(frames * 1000 / (now - lastReport));
        if (fps.samples.length >= 60) fps.samples.shift();
        fps.samples.push(fps.last);
        frames = 0;
        lastReport = now;
      }
      requestAnimationFrame(loop);
    }
    requestAnimationFrame(loop);
  }

  // -------- Navigation timing --------
  function captureNavTiming() {
    try {
      var entries = (performance.getEntriesByType && performance.getEntriesByType('navigation')) || [];
      var n = entries[0];
      if (!n) {
        // Fallback to legacy API.
        var t = performance.timing;
        if (!t) return;
        nav = {
          dns_ms: t.domainLookupEnd - t.domainLookupStart,
          tcp_ms: t.connectEnd - t.connectStart,
          ttfb_ms: t.responseStart - t.requestStart,
          response_ms: t.responseEnd - t.responseStart,
          dom_ms: t.domContentLoadedEventEnd - t.responseEnd,
          load_ms: t.loadEventEnd - t.navigationStart,
        };
      } else {
        nav = {
          dns_ms: Math.round(n.domainLookupEnd - n.domainLookupStart),
          tcp_ms: Math.round(n.connectEnd - n.connectStart),
          ttfb_ms: Math.round(n.responseStart - n.requestStart),
          response_ms: Math.round(n.responseEnd - n.responseStart),
          dom_ms: Math.round(n.domContentLoadedEventEnd - n.responseEnd),
          load_ms: Math.round(n.loadEventEnd - n.startTime),
          transfer_kb: n.transferSize ? Math.round(n.transferSize / 1024) : null,
        };
      }
    } catch (e) { /* swallow */ }
  }

  // -------- Overlay UI --------
  var overlay = null;
  var overlayTimer = null;

  function ensureOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.id = 'perf-overlay';
    overlay.style.cssText = [
      'position:fixed', 'right:8px', 'bottom:8px', 'z-index:99999',
      'background:rgba(10,12,18,0.92)', 'color:#dfe6ff',
      'font:11px/1.35 ui-monospace,Menlo,Consolas,monospace',
      'padding:8px 10px', 'border:1px solid rgba(255,255,255,0.18)',
      'border-radius:8px', 'max-width:420px', 'max-height:60vh',
      'overflow:auto', 'box-shadow:0 6px 18px rgba(0,0,0,0.5)',
      'pointer-events:auto'
    ].join(';');
    document.body.appendChild(overlay);
    return overlay;
  }

  function fmt(ms) { return ms.toFixed(0) + 'ms'; }

  function renderOverlay() {
    if (!overlay) return;
    var lines = [];
    lines.push('<b style="color:#ffd166">Perf overlay</b> &nbsp;<span style="opacity:.6">Ctrl+Shift+P to toggle</span>');
    if (nav) {
      lines.push('Nav: TTFB ' + fmt(nav.ttfb_ms) + ' &middot; DOM ' + fmt(nav.dom_ms) + ' &middot; load ' + fmt(nav.load_ms) +
                 (nav.transfer_kb != null ? ' &middot; ' + nav.transfer_kb + ' KB' : ''));
    }
    lines.push('FPS ' + fps.last + ' &middot; longTasks ' + longTasks.count + ' (max ' + fmt(longTasks.max) + ')');

    var rRows = [];
    Object.keys(routes).forEach(function (k) {
      var b = routes[k];
      rRows.push({
        url: k,
        count: b.count,
        avg: b.total / b.count,
        max: b.max,
        p95: p95(b.samples),
        last: b.last,
        errors: b.errors,
      });
    });
    rRows.sort(function (a, b) { return (b.avg * b.count) - (a.avg * a.count); });
    if (rRows.length) {
      lines.push('<div style="margin-top:6px;color:#ffd166">Top AJAX (sorted by total time)</div>');
      lines.push('<table style="width:100%;border-collapse:collapse">' +
        '<tr style="opacity:.7"><td>url</td><td style="text-align:right">n</td><td style="text-align:right">avg</td><td style="text-align:right">p95</td><td style="text-align:right">max</td></tr>' +
        rRows.slice(0, 8).map(function (r) {
          return '<tr><td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + r.url +
            (r.errors ? ' <span style="color:#ff7777">(' + r.errors + ' err)</span>' : '') +
            '</td><td style="text-align:right">' + r.count +
            '</td><td style="text-align:right">' + fmt(r.avg) +
            '</td><td style="text-align:right">' + fmt(r.p95) +
            '</td><td style="text-align:right">' + fmt(r.max) + '</td></tr>';
        }).join('') +
        '</table>');
    }

    var eRows = Object.keys(events).map(function (k) {
      return { name: k, count: events[k].count, rate: events[k].ratePerSec || 0 };
    }).sort(function (a, b) { return b.count - a.count; });
    if (eRows.length) {
      lines.push('<div style="margin-top:6px;color:#ffd166">Inbound socket events</div>');
      lines.push('<table style="width:100%;border-collapse:collapse">' +
        '<tr style="opacity:.7"><td>event</td><td style="text-align:right">n</td><td style="text-align:right">~/s</td></tr>' +
        eRows.slice(0, 8).map(function (r) {
          return '<tr><td>' + r.name + '</td><td style="text-align:right">' + r.count +
            '</td><td style="text-align:right">' + r.rate.toFixed(1) + '</td></tr>';
        }).join('') +
        '</table>');
    }

    overlay.innerHTML = lines.join('<br>');
  }

  function showOverlay() {
    ensureOverlay();
    if (overlayTimer) return;
    renderOverlay();
    overlayTimer = setInterval(renderOverlay, 1000);
  }

  function hideOverlay() {
    if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
    overlay = null;
    if (overlayTimer) { clearInterval(overlayTimer); overlayTimer = null; }
  }

  function toggleOverlay() {
    if (overlay) { hideOverlay(); }
    else { showOverlay(); }
  }

  // Toggle hotkey is always installed (cheap) so users can opt-in mid-session.
  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey && e.shiftKey && (e.key === 'P' || e.key === 'p')) {
      e.preventDefault();
      try { localStorage.setItem('vtt.perf', overlay ? '0' : '1'); } catch (err) { /* noop */ }
      toggleOverlay();
    }
  });

  // Public API for console inspection.
  window.__perf = {
    enabled: function () { return enabled || !!overlay; },
    routes: function () { return routes; },
    events: function () { return events; },
    longTasks: function () { return longTasks; },
    fps: function () { return fps; },
    nav: function () { return nav; },
    show: showOverlay,
    hide: hideOverlay,
    toggle: toggleOverlay,
    snapshot: function () {
      var out = { nav: nav, fps: fps.last, longTasks: longTasks, routes: {}, events: {} };
      Object.keys(routes).forEach(function (k) {
        var b = routes[k];
        out.routes[k] = { count: b.count, avg: +(b.total / b.count).toFixed(1), p95: +p95(b.samples).toFixed(1), max: +b.max.toFixed(1), errors: b.errors };
      });
      Object.keys(events).forEach(function (k) { out.events[k] = events[k].count; });
      console.table(out.routes);
      console.table(out.events);
      console.log('nav', out.nav, 'fps', out.fps, 'longTasks', out.longTasks);
      return out;
    },
  };

  // Always instrument (cheap) so on-the-fly toggling has data to show.
  instrumentJQuery();
  instrumentSocketIO();
  instrumentLongTasks();
  instrumentFPS();

  if (document.readyState === 'complete') {
    captureNavTiming();
  } else {
    window.addEventListener('load', function () { setTimeout(captureNavTiming, 0); });
  }

  if (enabled) {
    if (document.body) showOverlay();
    else document.addEventListener('DOMContentLoaded', showOverlay);
  }
})();
