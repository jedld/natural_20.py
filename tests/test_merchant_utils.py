import unittest
from unittest.mock import Mock

from natural20.utils.merchant import (
    apply_price_modifier,
    build_merchant_catalog,
    execute_merchant_trade,
    is_merchant,
    parse_item_cost,
    validate_merchant_trade,
)


class TestMerchantUtils(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.session.load_thing.side_effect = lambda slug: {
            'dagger': {'name': 'Dagger', 'cost': 2, 'type': 'melee_attack', 'subtype': 'weapon'},
            'gold_piece': {'name': 'Gold Piece', 'cost': 1, 'type': 'currency'},
            'leather_armor': {'name': 'Leather', 'cost': 10, 'type': 'armor', 'subtype': 'light'},
        }.get(slug)

    def test_parse_item_cost_handles_gp_suffix(self):
        self.assertEqual(parse_item_cost('15gp'), 15.0)
        self.assertEqual(parse_item_cost('5sp'), 0.5)
        self.assertEqual(parse_item_cost(25), 25.0)

    def test_is_merchant_detects_config(self):
        entity = Mock(properties={'merchant': {'wares': [{'type': 'dagger', 'qty': 1}]}})
        self.assertTrue(is_merchant(entity))
        self.assertFalse(is_merchant(Mock(properties={})))

    def test_apply_price_modifier_discount_and_markup(self):
        self.assertEqual(apply_price_modifier(100, discount_percent=10, markup=1.0), 90.0)
        self.assertEqual(apply_price_modifier(100, discount_percent=0, markup=1.25), 125.0)

    def test_build_merchant_catalog_applies_discount(self):
        merchant = Mock()
        merchant.properties = {
            'merchant': {
                'wares': [
                    {'type': 'dagger', 'qty': 2, 'price': 2},
                    {'type': 'leather_armor', 'qty': 1},
                ],
            },
            'merchant_stock': {},
        }
        merchant.label.return_value = 'Bram'
        catalog = build_merchant_catalog(self.session, merchant, discount_percent=10)
        by_type = {row['type']: row for row in catalog}
        self.assertEqual(by_type['dagger']['unit_price'], 1.8)
        self.assertEqual(by_type['leather_armor']['unit_price'], 9.0)

    def test_validate_and_execute_trade_with_gold(self):
        merchant = Mock()
        merchant.properties = {
            'merchant': {'wares': [{'type': 'dagger', 'qty': 1, 'price': 2}]},
            'merchant_stock': {'dagger': 1},
        }
        merchant.inventory = {}
        merchant.add_item = Mock()

        buyer = Mock()
        buyer.inventory = {'gold_piece': {'qty': 5}}
        buyer.deduct_item = Mock(side_effect=lambda item, qty: buyer.inventory.__setitem__(
            item, {'qty': buyer.inventory[item]['qty'] - qty},
        ))
        buyer.add_item = Mock()

        purchase = {'items': ['dagger'], 'qty': ['1']}
        payment = {'items': ['gold_piece'], 'qty': ['2']}

        ok, message, details = validate_merchant_trade(
            self.session, merchant, buyer, purchase, payment,
        )
        self.assertTrue(ok, message)
        self.assertEqual(details['purchase_total'], 2.0)
        self.assertEqual(details['payment_total'], 2.0)

        ok, message, _ = execute_merchant_trade(
            self.session, merchant, buyer, purchase, payment,
        )
        self.assertTrue(ok, message)
        buyer.add_item.assert_any_call('dagger', 1)
        self.assertNotIn('dagger', merchant.properties['merchant_stock'])


if __name__ == '__main__':
    unittest.main()
