# -*- coding: utf-8 -*-
"""
.. module:: account_invoice_centre_pe
    :plataform: Independent
    :synopsis: Invoice centre module
.. moduleauthor: Carlos Eduardo Sotelo Pinto <carlos.sotelo.pinto@gmail.com>
.. copyright: (c) 2017
.. organization: Tryton - PE
.. license: GPL v3.
"""


from trytond.pool import Pool
from .invoice import (
    InvoiceSequence,
    Invoice,
    InvoicePaymentLine,
    CancelMoves,
    NullifyMoves
)
from .invoicing_centre import (
    InvoicingCentre,
    InvoicingCentreStatement,
    InvoicingCentreStatementLine,
    InvoicingCentreStatementOut,
    InvoicingCentreStatementReport,
    InvoicingCentreStatementOutSequences,
    InvoiceCentreInvoiceSequence
)


def register():
    Pool.register(
        InvoicingCentre,
        InvoicingCentreStatement,
        InvoicingCentreStatementLine,
        InvoicingCentreStatementOut,
        InvoicingCentreStatementOutSequences,
        InvoiceCentreInvoiceSequence,
        Invoice,
        InvoiceSequence,
        InvoicePaymentLine,
        module='account_invoice_centre_pe', type_='model')
    Pool.register(
        InvoicingCentreStatementReport,
        module='account_invoice_centre_pe', type_='report')
    Pool.register(
        CancelMoves,
        NullifyMoves,
        module='account_invoice_centre_pe', type_='wizard')

