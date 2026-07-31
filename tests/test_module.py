# This file is part quality_control_rules module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from types import SimpleNamespace

from trytond.modules.quality_control_rules.quality import QualityControlRule
from trytond.tests.test_tryton import ModuleTestCase


class QualityControlRulesTestCase(ModuleTestCase):
    'Test Quality Control Rules module'
    module = 'quality_control_rules'

    def test_quality_control_rule_on_change_quality_template(self):
        product_a = SimpleNamespace(id=1)
        product_b = SimpleNamespace(id=2)
        rule = SimpleNamespace(
            quality_template=SimpleNamespace(products=[product_a, product_b]),
            products=[],
        )

        QualityControlRule.on_change_quality_template(rule)

        self.assertEqual(rule.products, [product_a, product_b])

        rule.quality_template = None
        rule.products = [product_a]

        QualityControlRule.on_change_quality_template(rule)

        self.assertEqual(rule.products, [])


del ModuleTestCase
