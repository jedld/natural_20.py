"""Merchant trading helpers — wares, pricing, and barter execution."""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Tuple

_CURRENCY_ALIASES = {
    'gp': 1.0,
    'gold': 1.0,
    'gold_piece': 1.0,
    'sp': 0.1,
    'silver': 0.1,
    'silver_piece': 0.1,
    'cp': 0.01,
    'copper': 0.01,
    'copper_piece': 0.01,
    'ep': 0.5,
    'electrum': 0.5,
    'electronum': 0.5,
}

_COST_PATTERN = re.compile(
    r'^\s*(\d+(?:\.\d+)?)\s*(gp|gold|sp|silver|cp|copper|ep|electrum)?\s*$',
    re.IGNORECASE,
)


def parse_item_cost(raw) -> float:
    """Normalize YAML ``cost`` values to gold pieces (gp)."""
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip().lower().replace(',', '')
    if not text:
        return 0.0
    if text in _CURRENCY_ALIASES:
        return float(_CURRENCY_ALIASES[text])
    match = _COST_PATTERN.match(text)
    if not match:
        try:
            return float(text)
        except (TypeError, ValueError):
            return 0.0
    amount = float(match.group(1))
    unit = (match.group(2) or 'gp').lower()
    return amount * _CURRENCY_ALIASES.get(unit, 1.0)


def merchant_config(entity) -> Optional[Dict[str, Any]]:
    """Return merchant configuration when the entity is a shopkeeper."""
    props = getattr(entity, 'properties', None) or {}
    merchant = props.get('merchant')
    if merchant is True:
        return {'wares': props.get('merchant_wares') or []}
    if isinstance(merchant, dict) and merchant.get('enabled', True):
        return merchant
    if props.get('is_merchant'):
        return props.get('merchant') if isinstance(props.get('merchant'), dict) else {'wares': props.get('merchant_wares') or []}
    return None


def is_merchant(entity) -> bool:
    return merchant_config(entity) is not None


def _ware_entries(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    wares = config.get('wares') or config.get('stock') or []
    if not isinstance(wares, list):
        return []
    return [entry for entry in wares if isinstance(entry, dict) and entry.get('type')]


def ensure_merchant_stock(entity, config: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """Initialize and return mutable merchant stock keyed by item slug."""
    props = getattr(entity, 'properties', None)
    if props is None:
        entity.properties = {}
        props = entity.properties
    stock = props.get('merchant_stock')
    if not isinstance(stock, dict):
        stock = {}
    if not stock:
        cfg = config or merchant_config(entity) or {}
        for entry in _ware_entries(cfg):
            item_type = str(entry['type'])
            try:
                qty = int(entry.get('qty', 0))
            except (TypeError, ValueError):
                qty = 0
            if qty > 0:
                stock[item_type] = qty
        props['merchant_stock'] = stock
    return props['merchant_stock']


def base_item_price(session, item_type: str, ware_entry: Optional[Dict[str, Any]] = None) -> float:
    if ware_entry and ware_entry.get('price') is not None:
        return parse_item_cost(ware_entry['price'])
    item = session.load_thing(item_type)
    if not item:
        return 0.0
    return parse_item_cost(item.get('cost'))


def apply_price_modifier(base_price: float, discount_percent: float = 0.0, markup: float = 1.0) -> float:
    """Apply merchant markup then customer discount (positive discount lowers price)."""
    price = float(base_price) * float(markup or 1.0)
    if discount_percent:
        price *= max(0.0, 1.0 - (float(discount_percent) / 100.0))
    return round(price, 2)


def item_trade_value(
    session,
    item_type: str,
    qty: int = 1,
    *,
    buyback_rate: float = 0.5,
    ware_entry: Optional[Dict[str, Any]] = None,
    discount_percent: float = 0.0,
    markup: float = 1.0,
    as_payment: bool = False,
) -> float:
    """Value of an item stack in gp for purchases or player payments."""
    try:
        qty = int(qty)
    except (TypeError, ValueError):
        qty = 0
    if qty <= 0:
        return 0.0
    if item_type == 'gold_piece':
        return float(qty)
    unit = base_item_price(session, item_type, ware_entry)
    if as_payment:
        unit *= float(buyback_rate or 0.0)
    else:
        unit = apply_price_modifier(unit, discount_percent=discount_percent, markup=markup)
    return round(unit * qty, 2)


def build_merchant_catalog(
    session,
    merchant,
    *,
    discount_percent: float = 0.0,
) -> List[Dict[str, Any]]:
    config = merchant_config(merchant) or {}
    markup = float(config.get('markup', 1.0) or 1.0)
    stock = ensure_merchant_stock(merchant, config)
    catalog = []
    for entry in _ware_entries(config):
        item_type = str(entry['type'])
        available = int(stock.get(item_type, 0) or 0)
        if available <= 0:
            continue
        item = session.load_thing(item_type) or {}
        base = base_item_price(session, item_type, entry)
        unit_price = apply_price_modifier(base, discount_percent=discount_percent, markup=markup)
        catalog.append({
            'type': item_type,
            'name': item.get('name') or item_type,
            'label': entry.get('label') or item.get('name') or item_type,
            'qty': available,
            'base_price': base,
            'unit_price': unit_price,
            'image': item.get('image', item_type),
            'category': _item_category(item),
        })
    catalog.sort(key=lambda row: (row['category'], row['name']))
    return catalog


def build_payment_catalog(session, buyer, *, buyback_rate: float = 0.5) -> List[Dict[str, Any]]:
    rows = []
    for item in buyer.inventory_items(session) or []:
        item_type = item['name']
        unit_value = item_trade_value(session, item_type, 1, buyback_rate=buyback_rate, as_payment=True)
        rows.append({
            'type': item_type,
            'name': item_type,
            'label': item.get('label') or item_type,
            'qty': int(item.get('qty') or 0),
            'unit_value': unit_value,
            'image': item.get('image', item_type),
            'category': _item_category(session.load_thing(item_type) or {}),
        })
    rows.sort(key=lambda row: (row['category'], row['label']))
    return rows


def _item_category(item: Dict[str, Any]) -> str:
    item_type = str(item.get('type') or '').lower()
    subtype = str(item.get('subtype') or '').lower()
    if item_type == 'currency' or item.get('name') == 'gold_piece':
        return 'currency'
    if subtype == 'weapon' or item_type in {'melee_attack', 'ranged_attack'}:
        return 'weapons'
    if item_type == 'armor' or subtype in {'light', 'medium', 'heavy'}:
        return 'armor'
    if item_type in {'potion', 'provisions', 'tool'}:
        return 'supplies'
    if item_type == 'ammunition':
        return 'ammunition'
    return 'other'


def _normalize_selection(payload: Optional[Dict[str, Any]]) -> List[Tuple[str, int]]:
    if not payload or not isinstance(payload, dict):
        return []
    items = payload.get('items') or []
    qtys = payload.get('qty') or []
    selected = []
    for item_type, qty in zip(items, qtys):
        try:
            amount = int(qty)
        except (TypeError, ValueError):
            amount = 0
        if amount > 0:
            selected.append((str(item_type), amount))
    return selected


def validate_merchant_trade(
    session,
    merchant,
    buyer,
    purchase_payload: Optional[Dict[str, Any]],
    payment_payload: Optional[Dict[str, Any]],
    *,
    discount_percent: float = 0.0,
) -> Tuple[bool, str, Dict[str, Any]]:
    config = merchant_config(merchant) or {}
    markup = float(config.get('markup', 1.0) or 1.0)
    buyback_rate = float(config.get('buyback_rate', 0.5) or 0.0)
    stock = ensure_merchant_stock(merchant, config)
    ware_by_type = {str(entry['type']): entry for entry in _ware_entries(config)}

    purchases = _normalize_selection(purchase_payload)
    payments = _normalize_selection(payment_payload)
    if not purchases:
        return False, 'Select at least one item to buy.', {}

    purchase_total = 0.0
    for item_type, qty in purchases:
        if qty > int(stock.get(item_type, 0) or 0):
            return False, f'Not enough stock for {item_type}.', {}
        ware_entry = ware_by_type.get(item_type)
        purchase_total += item_trade_value(
            session,
            item_type,
            qty,
            ware_entry=ware_entry,
            discount_percent=discount_percent,
            markup=markup,
            as_payment=False,
        )

    payment_total = 0.0
    for item_type, qty in payments:
        available = int((buyer.inventory.get(item_type) or {}).get('qty', 0) or 0)
        if qty > available:
            return False, f'You do not have enough {item_type}.', {}
        payment_total += item_trade_value(
            session,
            item_type,
            qty,
            buyback_rate=buyback_rate,
            as_payment=True,
        )

    purchase_total = round(purchase_total, 2)
    payment_total = round(payment_total, 2)
    if payment_total + 1e-6 < purchase_total:
        shortfall = round(purchase_total - payment_total, 2)
        return False, f'Payment is short by {shortfall} gp.', {
            'purchase_total': purchase_total,
            'payment_total': payment_total,
            'shortfall': shortfall,
        }

    return True, 'ok', {
        'purchase_total': purchase_total,
        'payment_total': payment_total,
        'change': round(payment_total - purchase_total, 2),
        'purchases': purchases,
        'payments': payments,
    }


def execute_merchant_trade(
    session,
    merchant,
    buyer,
    purchase_payload: Optional[Dict[str, Any]],
    payment_payload: Optional[Dict[str, Any]],
    *,
    discount_percent: float = 0.0,
) -> Tuple[bool, str, Dict[str, Any]]:
    ok, message, details = validate_merchant_trade(
        session,
        merchant,
        buyer,
        purchase_payload,
        payment_payload,
        discount_percent=discount_percent,
    )
    if not ok:
        return False, message, details

    stock = ensure_merchant_stock(merchant)
    purchases = details['purchases']
    payments = details['payments']

    for item_type, qty in payments:
        buyer.deduct_item(item_type, qty)
        merchant.add_item(item_type, qty)

    for item_type, qty in purchases:
        stock[item_type] = int(stock.get(item_type, 0) or 0) - qty
        if stock[item_type] <= 0:
            stock.pop(item_type, None)
        buyer.add_item(item_type, qty)

    change = float(details.get('change') or 0.0)
    if change > 0:
        buyer.add_item('gold_piece', int(change))

    return True, 'Trade completed.', details


def merchant_shop_title(merchant) -> str:
    config = merchant_config(merchant) or {}
    if config.get('shop_name'):
        return str(config['shop_name'])
    try:
        return f"{merchant.label()}'s Shop"
    except Exception:
        return 'Merchant Shop'
