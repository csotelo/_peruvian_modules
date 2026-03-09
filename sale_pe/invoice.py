# -*- coding: utf-8 -*-
"""
    invoice.py

    :copyright: (c) 2019 by Grupo ConnectTix SAC
    :license: see LICENSE for more details.
"""
import itertools

from trytond.pool import PoolMeta
from trytond.pyson import Eval

__all__ = [
    'Invoice'
]


class Invoice(metaclass=PoolMeta):
    'Invoice'
    __name__ = 'account.invoice'

    @classmethod
    def get_modified_document(cls, invoices, name):
        """
        Method to get the modified document in credit note documents

        :param invoices: Invoice Objects
        :param name: Name

        :return: Invoices dictionary
        """
        invoices_list = {}
        for invoice in invoices:
            invoices_list[invoice.id] = None
            if len(invoice.lines) > 0 and \
                    hasattr(invoice.lines[0].origin, 'invoice'):
                invoices_list[
                    invoice.id
                ] = invoice.lines[0].origin.invoice.number
            if len(invoice.lines) > 0 and \
                    hasattr(invoice.lines[0].origin, 'sale'):
                if invoice.sales[0].origin:
                    try:
                        invoices_list[
                            invoice.id
                        ] = invoice.sales[0].origin.invoices[0].number
                    except:
                        continue
        return invoices_list

    @classmethod
    def get_modified_document_date(cls, invoices, name):
        """
        Method to get modified document date in credit note documents

        :param invoices: Iinvoice Objects
        :param name: Name

        :return: Invoices dictionary
        """

        invoices_list = {}
        for invoice in invoices:
            invoices_list[invoice.id] = None
            if len(invoice.lines) > 0 and \
                    hasattr(invoice.lines[0].origin, 'invoice'):
                invoices_list[
                    invoice.id
                ] = invoice.lines[0].origin.invoice.invoice_date
            try:
                if len(invoice.lines) > 0 and \
                        hasattr(invoice.lines[0].origin, 'sale'):
                    if invoice.sales[0].origin:
                        invoices_list[
                            invoice.id
                        ] = invoice.sales[0].origin.invoices[0].invoice_date
            except:
                continue
        return invoices_list

    def get_origins(self, name):
        """Added a sale like a origin

        Arguments:
            name {str} -- field name

        Returns:
            str -- sale line origin
        """
        # if self.lines and hasattr(self.lines[0].origin, 'sale'):
        #     if self.sales and self.sales[0].origin:
        #         return self.sales[0].origin.invoices[0].number
        return ', '.join(set(filter(None,(l.origin_name for l in self.lines))))

    @classmethod
    def __setup__(cls):
        super(Invoice, cls).__setup__()
        cls.modified_document_reason.states['readonly'] = \
            ~(Eval('state') == 'draft')
