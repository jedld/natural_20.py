# Merchant Trading UI

Natural 20 includes a dual-pane merchant interface for barter-style shopping: players pick wares from the merchant, offer gold or items from their inventory, and complete the trade when the offer value meets the cart total.

## When it opens

The shop does **not** pop open automatically when you start talking. Use any of these:

1. **Talk dialog** — Click an NPC, open the JRPG dialog, then press the green **Shop** button (shown for merchants only).
2. **Map action bar** — Click the NPC's tile, then press **Shop** in the center action bar (next to Talk).
3. **NPC conversation** — The merchant LLM can emit `[OPEN_SHOP: target=speaker]` when the player asks to buy or browse wares.

You need a **player character selected as POV** to shop (the buyer). DMs can shop when controlling a PC.

## NPC configuration

Add a `merchant` section to the NPC template or map `overrides`:

```yaml
merchant:
  enabled: true
  shop_name: "Bram's Armory & Supplies"
  llm_pricing: true          # NPC LLM may adjust discount before wares load
  buyback_rate: 0.5          # player items valued at 50% of base cost when paying
  markup: 1.0                # multiplier on listed wares (before discount)
  wares:
    - type: shortsword
      qty: 3
      price: 25              # optional; defaults to item YAML `cost`
    - type: leather_armor
      qty: 2
```

Stock is tracked in `entity.properties.merchant_stock` after the first sale. Wares initialize stock on first open.

Shorthand also works: `is_merchant: true` with `merchant_wares: [...]`.

## Pricing

- Item prices use YAML `cost` (supports `gp`, `sp`, `cp`, or numeric gp).
- `gold_piece` counts as 1 gp per coin in payment or change.
- Optional per-ware `price` overrides the catalog cost.
- When `llm_pricing: true` and an NPC LLM provider is configured, `/merchant` asks the NPC model for a `discount_percent` (−50 to +50) using `npc_memory_store` context before rendering wares.

## HTTP routes

| Route | Method | Purpose |
|---|---|---|
| `/merchant` | GET | Render shop UI (`merchant_uid`, `buyer_uid`) |
| `/merchant/preview` | POST | JSON totals validation |
| `/merchant/trade` | POST | Execute atomic trade |

Blueprint: `webapp/blueprints/merchant.py` (`merchant.*` endpoints).

## UX notes

The UI follows common RPG shop patterns:

- Dual pane: wares (cart) vs. player offer
- Category filters (weapons, armor, supplies, ammo)
- Running totals and balance before commit
- Trade button enabled only when offer ≥ cart total
- Change returned as `gold_piece` when overpaid

## Wild Sheep Chase

`user_levels/wild_sheep_chase/npcs/bram_armorer.yml` — market armorer at token `AR` on `town_market` (weapons, armor, basic supplies).

**Mara (Bartender)** on `town_market` token `MB` also has `merchant` wares for tavern provisions (`ale_mug`, `bread_loaf`, `cheese_wedge`, `tavern_stew`, `rations`) with LLM relationship pricing enabled.

## Tests

- `tests/test_merchant_utils.py`
- `tests/webapp/test_merchant_trade.py`
