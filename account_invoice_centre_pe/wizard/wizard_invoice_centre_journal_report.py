# -*- coding: utf-8 -*-

from trytond.model import ModelView
from trytond.wizard import Wizard, StateTransition, StateView, Button


__all__ = ['PrintPosJournalReportStart', 'PrintPosJournalReport']


class PrintPosJournalReportStart(ModelView):
    'Print Pos Journal Report'
    __name__ = 'account.invoice.centre.statement.print_report.init'


class PrintPosJournalReport(Wizard):
    'Print Pos Journal Report'
    __name__ = 'account.invoice.centre.statement.print_report'

    start = StateView(
        'account.invoice.centre.statement.print_report.init',
        'account_invoice_centre_pe.print_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Print', 'print_report', 'tryton-print', True),
        ])

    print_report = StateTransition()

    def transition_print_report(self):
        return 'end'
