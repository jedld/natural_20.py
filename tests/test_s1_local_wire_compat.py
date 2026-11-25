"""Wire-compatibility tests for the local System One-style model server.

The engine talks to TypeSafe JEV through ``typesafe_sdk`` (``webapp.
llm_handler.JevProvider`` -> ``POST /v1/systemone``). These tests train a tiny
local model from the distilled dataset and serve it with uvicorn on a local
socket, then drive the *real* SDK + provider against it — proving the engine
can be pointed at a self-hosted model with nothing but ``TYPESAFE_BASE_URL``.
"""
import os
import threading
import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
pytest.importorskip("typesafe_sdk")

import httpx  # noqa: E402

from s1_local.data import fit_tokenizer, load_records, split_records  # noqa: E402
from s1_local.inference import S1LocalPredictor  # noqa: E402
from s1_local.model import S1Config, S1SystemOne  # noqa: E402
from s1_local.server import build_app  # noqa: E402

# Prefer the deduped corpus; fall back to the raw export.
_CANDIDATE_DATASETS = [
    os.path.join("logs", "choice_training", "action_decisions_dedup.jsonl"),
    os.path.join("logs", "choice_training", "action_decisions.jsonl"),
]
DATA = next((p for p in _CANDIDATE_DATASETS if os.path.exists(p)), _CANDIDATE_DATASETS[0])


def _tiny_state():
    return (
        "You are acting for the entity \"Goblin\" in a D&D 5e battle.\n"
        "Your stats: HP 7/7, AC 15, speed 30 ft. Position: x=5, y=4.\n"
        "Conditions: none. Resources: action available.\n"
        "Nearby: player \"Aldric\" (Human Fighter) at x=7, y=4, distance 10 ft, HP 12/20.\n"
        "Return the index of the single best action for this entity."
    )


@pytest.fixture(scope="module")
def predictor():
    if not os.path.exists(DATA):
        pytest.skip("distillation dataset not present")
    records = load_records([DATA])
    train, _val = split_records(records, 0.15)
    train = train[:128]
    tokenizer = fit_tokenizer(train, 4000, 1)
    config = S1Config(vocab_size=tokenizer.vocab_size, d_model=32, n_heads=4,
                       state_layers=0, option_layers=1, cross_layers=1,
                       max_state_len=256, max_option_len=32, max_options=32,
                       n_mem_slots=8)
    import torch
    from s1_local.data import S1ChoiceDataset, collate
    from torch.utils.data import DataLoader

    model = S1SystemOne(config)
    ds = S1ChoiceDataset(train, tokenizer, 256, 32)
    dl = DataLoader(ds, batch_size=16, shuffle=True, collate_fn=collate)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-3)
    model.train()
    for _epoch in range(12):
        for batch in dl:
            logits = model(batch["state_ids"], batch["state_mask"],
                           batch["option_ids"], batch["option_mask"],
                           batch["option_token_mask"])
            logp = torch.log_softmax(logits, dim=-1)
            loss = -(batch["target"] * logp).sum(dim=-1).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
    return S1LocalPredictor(model, tokenizer, config, device="cpu")


@pytest.fixture(scope="module")
def base_url(predictor):
    """Serve the app over a real local socket, like scripts/s1_local_api_server.py."""
    import uvicorn

    app = build_app(predictor)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        raise RuntimeError("uvicorn test server did not start")
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _sdk_client(base_url):
    from typesafe_sdk import TypeSafeClient

    return TypeSafeClient(api_key="test-key", base_url=base_url, timeout=30.0)


def test_systemone_choice_shape(base_url):
    client = _sdk_client(base_url)
    options = ["Attack with scimitar", "Dash away", "Hide", "Use the potion"]
    result = client.system_one(
        state=_tiny_state(),
        questions={"action": {"type": "choice",
                              "criteria": {str(i): o for i, o in enumerate(options)}}},
    )
    assert result.model
    assert hasattr(result.usage, "input_tokens")
    ans = result.choices["action"]
    assert ans.choice in {str(i) for i in range(len(options))}
    assert 0 <= ans.confidence <= 1
    probs = ans.probabilities
    assert set(probs) == {str(i) for i in range(len(options))}
    assert abs(sum(probs.values()) - 1.0) < 1e-3
    assert probs[ans.choice] >= max(probs.values()) - 1e-9


def test_systemone_noul_shape(base_url):
    client = _sdk_client(base_url)
    result = client.system_one(
        state=_tiny_state(),
        questions={"answer": {"type": "noul",
                              "instructions": "Is this creature badly hurt?"}},
    )
    n = result.nouls["answer"]
    assert 0.0 <= n.noul <= 1.0


def test_jev_provider_decide_action(base_url):
    """The engine's JevProvider.decide_action works end-to-end vs local server."""
    from webapp.llm_handler import JevProvider

    provider = JevProvider(opts={"api_key": "test-key", "base_url": base_url})
    assert provider.initialize({"api_key": "test-key", "base_url": base_url})
    options = ["Attack", "Dash", "Dodge"]
    parsed = provider.decide_action(_tiny_state(), options)
    assert parsed is not None
    assert parsed["index"] in (0, 1, 2)
    assert parsed["probabilities"] and abs(sum(parsed["probabilities"].values()) - 1.0) < 1e-3


def test_models_endpoint(base_url):
    client = _sdk_client(base_url)
    listing = client.models.list()
    assert any(m.name for m in listing.models)


def test_request_id_header(base_url):
    resp = httpx.get(f"{base_url}/health")
    assert resp.status_code == 200
    assert resp.headers.get("x-typesafe-request-id")


def test_validation_errors(base_url):
    resp = httpx.post(f"{base_url}/v1/systemone",
                      json={"state": "x", "model": "s1-local-1", "questions": {}})
    assert resp.status_code == 422
    # criteria beyond the engine's 64/255 option cap -> 422 with details, not a crash
    resp = httpx.post(f"{base_url}/v1/systemone", json={
        "state": "x", "model": "s1-local-1",
        "questions": {"action": {"type": "choice",
                                 "criteria": {str(i): f"opt {i}" for i in range(300)}}}})
    assert resp.status_code == 422
    assert "detail" in resp.json()
