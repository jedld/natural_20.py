import json

import pytest

from natural20.campaign_scaffold import CampaignExistsError, main, scaffold_campaign
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.session import Session


def test_scaffold_creates_bootable_campaign(tmp_path):
    root = scaffold_campaign(tmp_path / "dragon_lance", width=12, height=9)

    index = json.loads((root / "index.json").read_text())
    assert index["title"] == "Dragon Lance"
    assert index["map"] == "maps/start"
    assert (index["width"], index["height"]) == (12, 9)
    assert any("dm" in login["role"] for login in index["logins"])
    for key in ("login_background", "soundtracks", "default_controllers", "tile_size"):
        assert key in index

    session = Session(root_path=str(root), event_manager=EventManager())
    assert session.game_properties["starting_map"] == "maps/start"
    battle_map = Map(session, "maps/start")
    assert battle_map.size == [12, 9]
    assert not battle_map.entities


def test_scaffold_refuses_existing_campaign(tmp_path):
    root = scaffold_campaign(tmp_path / "camp", title="Original")
    with pytest.raises(CampaignExistsError):
        scaffold_campaign(root, title="Clobbered")

    assert main(["--if-missing", str(root), "--title", "Clobbered"]) == 0
    assert json.loads((root / "index.json").read_text())["title"] == "Original"
    assert main([str(root)]) == 1
