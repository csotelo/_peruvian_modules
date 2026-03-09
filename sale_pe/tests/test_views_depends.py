# -*- coding: utf-8 -*-
"""
    tests/test_views_depends.py

    :copyright: (C) 2018 by Grupo ConnectTix SAC
    :license: see LICENSE for more details.
"""
import unittest

import trytond.tests.test_tryton
from trytond.tests.test_tryton import ModuleTestCase
from trytond.tests.test_tryton import doctest_teardown, doctest_checker, doctest


class TestViewsDepends(ModuleTestCase):
    """Test View Depends."""
    module = 'sale_pe'


def suite():
    """
    Define suite
    """
    test_suite = trytond.tests.test_tryton.suite()
    test_suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestViewsDepends)
    )
    test_suite.addTests(doctest.DocFileSuite('scenario_sale.rst',
                                        tearDown=doctest_teardown, encoding='utf-8',
                                        optionflags=doctest.REPORT_ONLY_FIRST_FAILURE,
                                        checker=doctest_checker))
    return test_suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
