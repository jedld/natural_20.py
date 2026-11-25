"""FastAPI app speaking the TypeSafe "System One" wire protocol.

Identical HTTP contract to ``https://api.typesafe.ai`` (the endpoints
``typesafe_sdk`` / ``webapp.llm_handler.JevProvider`` call):

    POST /v1/systemone   {"state": ..., "model": ..., "questions": {...}}
      -> {"model": ..., "usage": {...}, "answers": {name: {type, ...}}}
    GET  /v1/models      -> {"models": [{"name", "description", "release_date"}]}
    GET  /health         -> local liveness info (not part of the wire protocol)

Point the engine at it with ``TYPESAFE_BASE_URL`` / ``BATTLE_TYPESAFE_BASE_URL``.
"""
from __future__ import annotations

import itertools
import json
import time
from typing import Optional

try:  # optional dependency: only needed to serve, not to train
    from fastapi import FastAPI, HTTPException, Request
except ImportError:  # pragma: no cover - exercised only without fastapi
    FastAPI = HTTPException = Request = None

MODEL_NAME = "s1-local-1"
MODEL_DESCRIPTION = "Locally trained System One-style System One choice model (D&D battle decisions)."
MODEL_RELEASE_DATE = time.strftime('%Y-%m-%d')


def build_app(predictor, api_key: Optional[str] = None):
    """Create the FastAPI app around a loaded :class:`S1LocalPredictor`."""
    if FastAPI is None:
        raise RuntimeError("fastapi is required to serve the local JEV model: "
                           "pip install fastapi uvicorn")

    app = FastAPI(title="s1-local", version="1.0")

    request_counter = itertools.count(1)

    @app.middleware("http")
    async def _request_id(request: Request, call_next):
        """Echo the SDK's request-id header so clients can log/correlate calls."""
        response = await call_next(request)
        response.headers['x-typesafe-request-id'] = (
            request.headers.get('x-typesafe-request-id')
            or f"s1-local-{next(request_counter)}"
        )
        return response

    def _check_auth(request: Request) -> None:
        if not api_key:
            return
        header = request.headers.get('authorization', '')
        token = header[7:] if header.lower().startswith('bearer ') else request.headers.get('x-api-key', '')
        if token != api_key:
            raise HTTPException(status_code=401, detail="Invalid API key")

    @app.get("/v1/models")
    def models(request: Request):
        _check_auth(request)
        return {"models": [{
            "name": MODEL_NAME,
            "description": MODEL_DESCRIPTION,
            "release_date": MODEL_RELEASE_DATE,
        }]}

    @app.get("/health")
    def health():
        return {"ok": True, "model": MODEL_NAME,
                "max_options": predictor.max_options,
                "device": str(getattr(predictor, 'device', 'cpu'))}

    @app.post("/v1/systemone")
    async def system_one(request: Request):
        _check_auth(request)
        body = await request.json()
        state = body.get('state')
        questions = body.get('questions') or {}
        if state is None:
            raise HTTPException(status_code=422, detail="'state' is required")
        if not questions:
            raise HTTPException(status_code=422, detail="At least one question is required.")
        temperature = float(predictor.meta.get('temperature', 1.0))
        started = time.monotonic()
        try:
            answers = predictor.answer_questions(state, questions, temperature=temperature)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        elapsed_ms = (time.monotonic() - started) * 1000.0
        # Rough token estimate (chars/4) so usage-shaped clients still work.
        state_chars = len(state) if isinstance(state, str) else len(json.dumps(state, ensure_ascii=False))
        return {
            "model": MODEL_NAME,
            "answers": answers,
            "usage": {
                "input_tokens": max(1, state_chars // 4),
                "output_tokens": 1,
            },
            "latency_ms": round(elapsed_ms, 1),
        }

    return app


def load_predictor(checkpoint: str, device: Optional[str] = None):
    from .inference import S1LocalPredictor
    return S1LocalPredictor.load(checkpoint, device=device)
