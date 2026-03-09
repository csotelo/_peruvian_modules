# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
import unittest
import doctest
from trytond.pool import Pool
import trytond.tests.test_tryton
from trytond.tests.test_tryton import ModuleTestCase, with_transaction
from trytond.tests.test_tryton import doctest_teardown
from trytond.tests.test_tryton import doctest_checker
from trytond.modules.account_pe.journal_book import JournalSunatRow

class JournalBookTest(ModuleTestCase):
    module = 'account_pe'
    
    @with_transaction()
    def test_get_period(self):
        Line = Pool().get('account.move.line')
        line, = Line.create([{
            'period' : '2019-05'
        }])
        journalsunatrow = JournalSunatRow(line)
        self.assertIsNotNone(journalsunatrow.get_period())

def suite():
    suite = trytond.tests.test_tryton.suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
        JournalBookTest))
    suite.addTests(doctest.DocFileSuite(
        'scenario.rst',
        tearDown=doctest_teardown, encoding='utf-8',
        checker=doctest_checker,
        optionflags=doctest.REPORT_ONLY_FIRST_FAILURE))
    return suite