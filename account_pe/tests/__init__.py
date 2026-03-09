# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

try:
    from trytond.modules.account_pe.tests.test_journal_book import (
        suite)
except ImportError:
    from .test_journal_book import suite

__all__ = ['suite']
