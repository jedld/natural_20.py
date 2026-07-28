---
name: n20-ngrok-remote
description: >-
  Start natural_20.py webapp for remote play through ngrok (tmux, CORS, Socket.IO).
  Use when the user asks to run the game remotely, expose the VTT via ngrok, restart
  production/ngrok mode, or debug Socket.IO 400 / xhr post error / token movement
  failures through an ngrok URL.
---

# Natural20 ngrok remote play

## Quick start

```bash
# From repo root — campaign path required
./webapp/start_ngrok.sh ../user_levels/wild_sheep_chase
```

Then in a second terminal (or tmux pane):

```bash
ngrok http 5001
```

Share the `https://….ngrok-free.dev` URL. Tell the user to hard-refresh (`Ctrl+Shift+R`) after server restarts.

## tmux layout (preferred for long sessions)

```bash
tmux new-session -d -s n20
tmux send-keys -t n20 './webapp/start_ngrok.sh ../user_levels/<campaign>' Enter
tmux split-window -t n20 -v
tmux send-keys -t n20.1 'ngrok http 5001' Enter
# URL: tmux capture-pane -t n20.1 -p | grep -i forwarding
```

Restart server only: `tmux send-keys -t n20.0 C-c ''` then re-run `start_ngrok.sh`.

## Prerequisites checklist

- [ ] `webapp/.env` `CORS_ORIGINS` includes ngrok wildcards (see `webapp/env.example`). **Localhost-only CORS breaks Socket.IO through ngrok** — browser sends `Origin: https://<subdomain>.ngrok-free.dev` and the server returns 400 `"Not an accepted origin."`
- [ ] Campaign path exists (e.g. `user_levels/wild_sheep_chase`)
- [ ] Port **5001** free (`FLASK_RUN_PORT` in `.env` / `start_web.sh`)
- [ ] ngrok installed and authenticated

## What `start_ngrok.sh` sets

| Variable | Value | Why |
|----------|-------|-----|
| `N20_USE_MINIFIED_ASSETS` | `1` | Serve `*.min.js` bundles |
| `CORS_ORIGINS` | localhost + `https://*.ngrok.*` | Flask **and** Socket.IO origin checks |
| `FLASK_DEBUG` | `0` | Stable dev server |

Uses `start_web.sh` → `python -m webapp.app` (Socket.IO threading mode). **Do not** use `flask run` or gunicorn+eventlet on Python 3.13.

## Verify before telling the user it works

Run these after the server is up:

```bash
# 1. Server responding
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5001/login

# 2. Socket.IO accepts ngrok Origin (replace URL)
ORIGIN='https://YOUR-SUBDOMAIN.ngrok-free.dev'
curl -s -H "Origin: $ORIGIN" \
  "http://127.0.0.1:5001/socket.io/?EIO=4&transport=polling" | head -c 80
# Must be 200 with {"sid":...} — NOT 400 "Not an accepted origin."

# 3. Through ngrok tunnel
curl -s -H 'ngrok-skip-browser-warning: 1' -H "Origin: $ORIGIN" \
  "https://YOUR-SUBDOMAIN.ngrok-free.dev/socket.io/?EIO=4&transport=polling" | head -c 80
```

Expected client console after hard refresh: no Socket.IO 400s; `[TTSPlayer] Initialized` (not legacy `[TTS] Player initialized (index.html)`).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `POST …/socket.io/… 400` + `xhr post error` | CORS origin rejected | Add ngrok wildcards to `webapp/.env` `CORS_ORIGINS`; restart server |
| `POST 400` only in browser, curl OK | Stale tab / old `engine.min.js` | Hard refresh; confirm `engine.min.js?v=` hash changed |
| ngrok `ERR_NGROK_8012` | Server still booting or crashed | Check tmux pane 0; CosyVoice/TTS init can take ~30s |
| `site.webmanifest` syntax error | Manifest 302s to login HTML | Harmless when unauthenticated |
| Token won't move, no map refresh | Socket disconnected | Fix CORS first, then hard refresh |
| WebSocket fails, polling works | Normal through ngrok free tier | `engine.js` uses `['polling', 'websocket']`; polling alone is fine |

## Socket.IO internals (do not regress)

- Async mode: `threading` unless `N20_USE_GUNICORN=1` + production (`cors_config.socketio_async_mode`)
- Single `io()` client in `engine.js`; TTS binds to `window.socket` (no second `io()` in `tts_player.js`)
- Server: `manage_session=True`, `cors_allowed_origins` lambda in `webapp/app.py`

## Campaign argument

```bash
./webapp/start_ngrok.sh ../user_levels/death_house
./webapp/start_ngrok.sh --edit ../user_levels/wild_sheep_chase   # map editor
```

Default campaign if omitted: `../templates`.
