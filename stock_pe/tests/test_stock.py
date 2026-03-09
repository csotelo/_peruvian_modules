# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
import unittest
import doctest
import datetime
from decimal import Decimal
from dateutil.relativedelta import relativedelta
from functools import partial
from collections import defaultdict

import trytond.tests.test_tryton
from trytond.tests.test_tryton import ModuleTestCase, with_transaction
from trytond.tests.test_tryton import doctest_teardown
from trytond.tests.test_tryton import doctest_checker
from trytond.transaction import Transaction
from trytond.exceptions import UserWarning
from trytond.pool import Pool

from trytond.modules.company.tests import create_company, set_company


class StockTestCase(ModuleTestCase):
    'Test Stock module'
    module = 'stock'
    longMessage = True

    @with_transaction()
    def test_moves_netweight(self):
        'Test Move.netweight'
        pool = Pool()
        Uom = pool.get('product.uom')
        Template = pool.get('product.template')
        Product = pool.get('product.product')
        Location = pool.get('stock.location')
        Move = pool.get('stock.move')
        Shipment = pool.get('stock.shipment.out')

        kg, = Uom.search([('name', '=', 'Kilogram')])
        g, = Uom.search([('name', '=', 'Gram')])
        template, = Template.create([{
                    'name': 'Test Move.internal_quantity',
                    'type': 'goods',
                    'list_price': Decimal(1),
                    'cost_price': Decimal(0),
                    'cost_price_method': 'fixed',
                    'default_uom': kg.id,
                    }])
        product, = Product.create([{
                    'template': template.id,
                    }])
        supplier, = Location.search([('code', '=', 'SUP')])
        storage, = Location.search([('code', '=', 'STO')])
        company = create_company()
        currency = company.currency
        with set_company(company):
            tests = [
                (kg, 10, 10, 0),
                (g, 100, 0.1, 1),
                (g, 1, 0, 0),  # rounded
                (kg, 35.23, 35.23, 2),  # check infinite loop
            ]
            for uom, quantity, internal_quantity, ndigits in tests:
                move, = Move.create([{
                            'product': product.id,
                            'uom': uom.id,
                            'quantity': quantity,
                            'from_location': supplier.id,
                            'to_location': storage.id,
                            'company': company.id,
                            'unit_price': Decimal('1'),
                            'currency': currency.id,
                            }])
           
                for uom, quantity, internal_quantity, ndigits in tests:
                    Move.write([move], {
                        'uom': uom.id,
                        'quantity': quantity,
                        })
                    self.assertEqual(round(move.internal_quantity, ndigits),
                        internal_quantity)