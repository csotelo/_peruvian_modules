# -*- coding: utf-8 -*-
""".. module:: account_pe.

    :plataform: Independent
    :synopsis: Invoice module locale
.. moduleauthor: Carlos Eduardo Sotelo Pinto <carlos.sotelo.pinto@gmail.com>
.. copyright: (c) 2017
.. organization: Tryton - PE
.. license: GPL v2.
"""



from trytond.pool import Pool

from .account import *
from .journal_book import *
from .sheet_balance import (BalanceSheet, BalanceSheetReport,
                            BalanceSheetWizard, BalanceSumsReport,
                            BalanceSumsWizard)
from .sunat_ple import (PLEReportJournal,
                        PLEReportJournalPlain, PLEReportJournalSpread,
                        PLEReportMajor,
                        PLEReportMajorSpread, PLEReportMajorTemplate,
                        SunatPLEJournal, SunatPLEJournalView,
                        SunatPLEJournalWizard, SunatPLEMainView, SunatPLEMajor,
                        SunatPLEMajorView, SunatPLEMajorWizard)


def register():
    Pool.register(
        Account,
        Move,
        SunatPLEJournal,
        SunatPLEMajor,
        SunatPLEMainView,
        SunatPLEJournalView,
        SunatPLEMajorView,
        JournalEbook,
        BalanceSheet,
        module='account_pe', type_='model')
    Pool.register(
        PLEReportJournal,
        PLEReportJournalSpread,
        PLEReportJournalPlain,
        PLEReportMajor,
        PLEReportMajorSpread,
        JournalEbookReport,
        JournalEbookReportPLE,
        JournalEbookReportSpread,
        JournalEbookReportText,
        JournalEbookAccounting,
        MajorEbookReport,
        MajorEbookReportSpread,
        MajorEbookReportText,
        BalanceSheetReport,
        BalanceSumsReport,
        module='account_pe', type_='report')
    Pool.register(
        SunatPLEJournalWizard,
        SunatPLEMajorWizard,
        JournalEbookWizard,
        MajorEbookWizard,
        BalanceSheetWizard,
        BalanceSumsWizard,
        module='account_pe', type_='wizard')
