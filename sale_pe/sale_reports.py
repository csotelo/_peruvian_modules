# -*- coding: utf-8 -*-
"""
    sale_reports.py

    :copyright: (c) 2019 by Grupo ConnectTix SAC
    :license: see LICENSE for more details.
"""
import os
from datetime import datetime, date
from decimal import Decimal

from trytond.config import config
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, If
from trytond.report import Report
from trytond.transaction import Transaction
from trytond.wizard import Button, StateReport, StateView, Wizard

__all__ = ['SaleDetailed', 'SaleDetailedView',
           'SaleDetailedWizard', 'SaleDetailedReport',
           'SaleReportCondensend']


class SaleDetailed(ModelView, ModelSQL):
    'Sale Detailed Model'

    __name__ = 'sale.detailed'


class SaleDetailedView(SaleDetailed):
    'Base Detailed View for Wizard'

    __name__ = 'sale_pe.ple.sale.detailed.start'

    invoices = fields.Many2Many('account.invoice', None, None,
                                string='Facturas', domain=[('type', '=', 'out')])


class SaleDetailedWizard(Wizard):
    '''Sale Report Detailed Wizard'''
    __name__ = 'sale.detailed.wiz'

    start = StateView(
        'sale_pe.ple.sale.detailed.start',
        'sale_pe.create_detailed_report', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Generar Reporte', 'gen_', 'tryton-ok', default=True),
        ])

    gen_ = StateReport(
        'sale_pe.detailed_report'
    )

    def do_gen_(self, action):
        invoices_ids_list = list()
        for invoice in self.start.invoices:
            invoices_ids_list.append(invoice.id)
        return action, {
            'id': action['action'],
            'invoices': invoices_ids_list,
        }


class SaleReportCondensend(Report):
    'Sale Detailed Report'
    __name__ = 'sale_pe.conde_report'

    @classmethod
    def get_context(cls, records, data, **kwargs):
        '''Add to context
            :param records: selected invoices.
            :param data: context data
        '''
        context = super(SaleReportCondensend, cls).get_context(
            records, data, **kwargs)
        Invoice = Pool().get('account.invoice')
        Rate = Pool().get('currency.currency.rate')
        total_untaxed_amount = Decimal('0')
        total_tax_amount = Decimal('0')
        total_amount = Decimal('0')
        exchange_rate_dict = dict()
        pay_type_dict = dict()
        modified_invoices_dict = dict()
        for invoice in records:
            exchange_rate = invoice.currency.rate
            if invoice.document_type in ['commercial_credit', 'commercial_debit',
                                         'simple_credit', 'simple_debit']:
                modified_invoice_date = invoice.modified_document_date
                invoice_datetime = datetime(
                    modified_invoice_date.year,
                    modified_invoice_date.month,
                    modified_invoice_date.day)
                invoice_rate = Rate.search(
                    [('date', '<=', invoice_datetime),
                     ('currency', '=', invoice.currency),
                     ], order=[('date', 'DESC')], limit=1)
                if invoice_rate:
                    exchange_rate = (
                        1/invoice_rate[0].rate).quantize(Decimal('0.000'))
            else:
                if invoice.invoice_date:
                    invoice_datetime = datetime(
                        invoice.invoice_date.year,
                        invoice.invoice_date.month,
                        invoice.invoice_date.day)
                else:
                    invoice_datetime = date.today()
                invoice_rate = Rate.search(
                    [('date', '<=', invoice_datetime),
                     ('currency', '=', invoice.currency),
                     ], order=[('date', 'DESC')], limit=1)
                if invoice_rate:
                    exchange_rate = (
                        1/invoice_rate[0].rate).quantize(Decimal('0.000'))
            total_untaxed_amount += (invoice.untaxed_amount *
                                     exchange_rate).quantize(Decimal('0.00'))
            total_tax_amount += (invoice.tax_amount *
                                 exchange_rate).quantize(Decimal('0.00'))
            total_amount += (invoice.total_amount *
                             exchange_rate).quantize(Decimal('0.00'))
            exchange_rate_dict[invoice.id] = exchange_rate
            pay_type = ''
            for line in invoice.payment_lines:
                if line.credit > Decimal(0):
                    pay_type = line.journal.name if line.journal else ''
            pay_type_dict[invoice.id] = pay_type
        context['total_untaxed_amount'] = total_untaxed_amount
        context['total_tax_amount'] = total_tax_amount
        context['total_amount'] = total_amount
        context['exchange_rate_dict'] = exchange_rate_dict
        context['pay_type'] = pay_type_dict
        context['company'] = context['user'].company
        context['records'] = records
        return context


class SaleDetailedReport(Report):
    'Sale Detailed Report'
    __name__ = 'sale_pe.detailed_report'

    @classmethod
    def get_context(cls, records, data, **kwargs):
        '''Add to context
            records: selected invoices.
            amount values: total sum of all values
        '''
        def get_modified_invoice_data(invoice):
            '''Return a list of the data for the modified invoice section'''
            data = list()
            mod_invoice = None
            if len(invoice.lines) > 0 and \
                    hasattr(invoice.lines[0].origin, 'invoice'):
                mod_invoice = invoice.lines[0].origin.invoice
            if len(invoice.lines) > 0 and \
                    hasattr(invoice.lines[0].origin, 'sale'):
                if invoice.sales[0].origin:
                    mod_invoice = invoice.sales[0].origin.invoices[0]
            sunat_document_type = mod_invoice.sunat_document_type if mod_invoice \
                and mod_invoice.sunat_document_type else ''
            sunat_serial_prefix = mod_invoice.sunat_serial_prefix if mod_invoice \
                and mod_invoice.sunat_serial_prefix else ''
            sunat_serial_number = mod_invoice.sunat_serial if mod_invoice \
                and mod_invoice.sunat_serial else ''
            sunat_serial = sunat_serial_prefix + sunat_serial_number
            sunat_number = mod_invoice.number if mod_invoice \
                and mod_invoice.number else ''
            invoice_date = mod_invoice.invoice_date.strftime("%d/%m/%Y") if mod_invoice \
                and mod_invoice.invoice_date else ''
            data.extend([sunat_document_type, sunat_serial,
                         sunat_number, invoice_date])
            return data

        context = super(SaleDetailedReport, cls).get_context(
            records, data, **kwargs)
        records = cls._find_records(
            invoices=data['invoices']
        )
        Invoice = Pool().get('account.invoice')
        Rate = Pool().get('currency.currency.rate')
        records = [Invoice(x) for x in data['invoices']]
        total_untaxed_amount = Decimal('0')
        total_tax_amount = Decimal('0')
        total_amount = Decimal('0')
        exchange_rate_dict = dict()
        pay_type_dict = dict()
        modified_invoices_dict = dict()
        for invoice in records:
            exchange_rate = invoice.currency.rate
            if invoice.document_type in ['commercial_credit', 'commercial_debit',
                                         'simple_credit', 'simple_debit']:
                modified_invoice_date = invoice.modified_document_date
                invoice_datetime = datetime(
                    modified_invoice_date.year,
                    modified_invoice_date.month,
                    modified_invoice_date.day)
                invoice_rate = Rate.search(
                    [('date', '<=', invoice_datetime),
                     ('currency', '=', invoice.currency),
                     ], order=[('date', 'DESC')], limit=1)
                if invoice_rate:
                    exchange_rate = (
                        1/invoice_rate[0].rate).quantize(Decimal('0.000'))
            else:
                if invoice.invoice_date:
                    invoice_datetime = datetime(
                        invoice.invoice_date.year,
                        invoice.invoice_date.month,
                        invoice.invoice_date.day)
                else:
                    invoice_datetime = date.today()
                invoice_rate = Rate.search(
                    [('date', '<=', invoice_datetime),
                     ('currency', '=', invoice.currency),
                     ], order=[('date', 'DESC')], limit=1)
                if invoice_rate:
                    exchange_rate = (
                        1/invoice_rate[0].rate).quantize(Decimal('0.000'))
            total_untaxed_amount += (invoice.untaxed_amount *
                                     exchange_rate).quantize(Decimal('0.00'))
            total_tax_amount += (invoice.tax_amount *
                                 exchange_rate).quantize(Decimal('0.00'))
            total_amount += (invoice.total_amount *
                             exchange_rate).quantize(Decimal('0.00'))
            exchange_rate_dict[invoice.id] = exchange_rate
            modified_invoices_dict[invoice.id] = get_modified_invoice_data(
                invoice)
            pay_type = ''
            for line in invoice.payment_lines:
                if line.credit > Decimal(0):
                    pay_type = line.journal.name if line.journal else ''
            pay_type_dict[invoice.id] = pay_type
        context['total_untaxed_amount'] = total_untaxed_amount
        context['total_tax_amount'] = total_tax_amount
        context['total_amount'] = total_amount
        context['exchange_rate_dict'] = exchange_rate_dict
        context['pay_type'] = pay_type_dict
        context['company'] = context['user'].company
        context['records'] = records
        context['modified_invoice'] = modified_invoices_dict
        return context

    @classmethod
    def _find_records(cls, invoices):
        '''return invoices ids'''
        return invoices
