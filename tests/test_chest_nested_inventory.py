"""Nested container contents on map object / chest inventory."""

from __future__ import annotations

from pathlib import Path

from natural20.concern.inventory import serialize_inventory_for_yaml, yaml_inventory_source_item
from natural20.event_manager import EventManager
from natural20.item_library.chest import Chest
from natural20.session import Session


def test_yaml_inventory_source_item_preserves_contents():
    source = yaml_inventory_source_item(
        {
            "type": "human_skin_pouch",
            "qty": 1,
            "contents": [
                {"type": "gold_piece", "qty": 11},
                {"type": "silver_piece", "qty": 60},
            ],
        }
    )
    assert source["type"] == "human_skin_pouch"
    assert source["is_container"] is True
    assert source["contents"] == [
        {"type": "gold_piece", "qty": 11},
        {"type": "silver_piece", "qty": 60},
    ]


def test_chest_loads_nested_container_contents(tmp_path: Path):
    campaign = tmp_path / "demo"
    items = campaign / "items"
    items.mkdir(parents=True)
    (campaign / "game.yml").write_text("name: Demo\nmaps: {}\n", encoding="utf-8")
    (items / "equipment.yml").write_text(
        """
human_skin_pouch:
  name: Pouch of Human Skin
  type: container
  weight: 0.5
gold_piece:
  name: Gold Piece
  type: currency
  cost: 1
silver_piece:
  name: Silver Piece
  type: currency
  cost: 0.1
""".strip(),
        encoding="utf-8",
    )
    session = Session(root_path=str(campaign), event_manager=EventManager())
    chest = Chest(
        session,
        None,
        {
            "name": "Cultist Chest",
            "type": "chest",
            "inventory": [
                {
                    "type": "human_skin_pouch",
                    "qty": 1,
                    "contents": [
                        {"type": "gold_piece", "qty": 11},
                        {"type": "silver_piece", "qty": 60},
                    ],
                }
            ],
        },
    )
    pouch = chest.inventory["human_skin_pouch"]
    assert pouch["qty"] == 1
    assert pouch.get("is_container") is True
    assert pouch["contents"] == [
        {"type": "gold_piece", "qty": 11},
        {"type": "silver_piece", "qty": 60},
    ]
    serialized = serialize_inventory_for_yaml(chest.inventory)
    assert serialized == [
        {
            "type": "human_skin_pouch",
            "qty": 1,
            "contents": [
                {"type": "gold_piece", "qty": 11},
                {"type": "silver_piece", "qty": 60},
            ],
            "is_container": True,
        }
    ]


def test_normalize_inventory_preserves_nested_contents(tmp_path: Path):
    from natural20.edit_schema import get_edit_ui_schema, normalize_submitted_values

    campaign = tmp_path / "demo"
    campaign.mkdir(parents=True)
    (campaign / "game.yml").write_text("name: Demo\nmaps: {}\n", encoding="utf-8")
    (campaign / "maps").mkdir(parents=True)

    class Session:
        root_path = str(campaign)
        game_properties = {"maps": {}}

    schema = get_edit_ui_schema(Session(), "chest")
    normalized = normalize_submitted_values(
        schema,
        {
            "inventory": [
                {
                    "type": "human_skin_pouch",
                    "qty": 1,
                    "contents": [
                        {"type": "gold_piece", "qty": 11},
                        {"type": "silver_piece", "qty": 60},
                    ],
                }
            ]
        },
    )
    assert normalized["inventory"][0]["type"] == "human_skin_pouch"
    assert normalized["inventory"][0]["contents"] == [
        {"type": "gold_piece", "qty": 11},
        {"type": "silver_piece", "qty": 60},
    ]
