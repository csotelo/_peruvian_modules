# -*- coding: utf-8 -*-
"""
.. module:: account_invoice_pe
    :plataform: Independent
    :synopsis: Invoice module locale
.. moduleauthor: Carlos Eduardo Sotelo Pinto <carlos.sotelo.pinto@gmail.com>
.. copyright: (c) 2018
.. organization: Grupo ConnectTix SAC
.. license: GPL v3.
"""

from trytond.pool import Pool

from .company import Company
from .invoice import (CreditInvoice, CreditInvoiceStart, DebitInvoice,
                      DebitInvoiceStart, FiscalYear, Invoice, InvoiceLine,
                      InvoiceReport, InvoiceSequence, InvoiceTax, Move, MoveLine,
                      PayInvoice, PayInvoiceStart, SunatDocumentObservation,
                      VoidedDocument, VoidedDocumentStart, CanceledDocument, CanceledDocument, CanceledDocumentStart)
from .party import Party
from .payment_term import PaymentTerm
from .invoice_xml import InvoiceXMLModel, InvoiceXMLWizard
from .invoice_debug import InvoiceDebug

def register():
    Pool.register(
        FiscalYear,
        InvoiceSequence,
        Invoice,
        InvoiceLine,
        InvoiceTax,
        Company,
        Move,
        Party,
        PaymentTerm,
        SunatDocumentObservation,
        CreditInvoiceStart,
        PayInvoiceStart,
        MoveLine,
        DebitInvoiceStart,
        VoidedDocumentStart,
        CanceledDocumentStart,
        InvoiceXMLModel,
        InvoiceDebug,
        module='account_invoice_pe', type_='model')
    Pool.register(
        PayInvoice,
        CreditInvoice,
        DebitInvoice,
        VoidedDocument,
        CanceledDocument,
        InvoiceXMLWizard,
        module='account_invoice_pe', type_='wizard')
    Pool.register(
        InvoiceReport,
        module='account_invoice_pe', type_='report'
    )
