# -*- coding: utf-8 -*-
"""
    sale_reports.py

    :copyright: (c) 2019 by Grupo ConnectTix SAC
    :license: see LICENSE for more details.
"""
import os
from datetime import datetime
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
           'DetailsReport']


class SaleDetailed(ModelView, ModelSQL):
    'Sale Detailed Model'

    __name__ = 'sale.detailed'


class SaleDetailedView(SaleDetailed):
    'Base Detailed View for Wizard'

    __name__ = 'sale_pe.ple.sale.detailed.start'

    company = fields.Many2One(
        'company.company',
        'Company',
        required=True,
        domain=[
            ('id', If(Eval('context', {}).contains('company'), '=', '!='),
                Eval('context', {}).get('company', -1)),
        ],
        select=True
    )

    start_date = fields.Date(
        'Desde'
    )
    end_date = fields.Date(
        'Hasta'
    )


class SaleDetailedWizard(Wizard):
    '''Sale Report Detailed Wizard'''
    __name__ = 'sale.detailed.wiz'

    start = StateView(
        'sale_pe.ple.sale.detailed.start',
        'account_invoice_pe.create_detailed_report', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Generar Reporte', 'gen_', 'tryton-ok', default=True),
        ])

    gen_ = StateReport(
        'sale_pe.detailed_report'
    )

    def do_gen_(self, action):
        party_id = None
        currency_id = None
        if self.start.party:
            party_id = self.start.party.id
        if self.start.currency:
            currency_id = self.start.currency.id
        return action, {
            'id': action['action'],
            'company': self.start.company.id,
            'start_date': self.start.start_date,
            'end_date': self.start.end_date,
        }


class SaleDetailedReport(Report):
    'Sale Detailed Report'
    __name__ = 'sale_pe.detailed_report'

    @classmethod
    def get_context(cls, records, data, **kwargs):
        InvoiceObject = Pool().get('account.invoice')
        context = super(SaleDetailedReport, cls).get_context(
            records, data, **kwargs)
        records = cls._find_records(
            from_date=data['start_date'],
            to_date=data['end_date'],
            ActiveRecord=InvoiceObject
        )
        context['invoices'] = records
        context['company'] = context['user'].company
        return context

    @classmethod
    def _find_records(cls, from_date, to_date, ActiveRecord=None):
        clause = [
            ('type', '=', 'out'),
            ('state', 'in', ('draft', 'posted', 'paid')),
            ('number', '!=', None), ]
        invoices = ActiveRecord.search(clause,
                                       order=[('sunat_document_type', 'ASC'),
                                              ('sunat_serial', 'ASC'),
                                              ('sunat_number', 'ASC')])

        return invoices


class DetailsReport(Report):
    'detaile report'
    __name__ = 'account.invoice'

    @classmethod
    def __setup__(cls):
        super(DetailsReport, cls).__setup__()

    @classmethod
    def get_context(cls, records, data):
        context = super(DetailsReport, cls).get_context(records, data)
        Invoice = Pool().get('account.invoice')
        general_dict = dict()
        records = list()
        if data:
            for id in data['ids']:
                records.append(Invoice(id))
            for record in records:
                item_number = 0
                for line in record.lines:
                    line_id = line.id
                    line_list = list()
                    item_number += 1
                    line_list.append(item_number)
                    general_dict[line_id] = line_list
            Invoice.write(records, {
                'invoice_report_format': None,
                'invoice_report_cache': None,
            })
            total_untaxed_amount = Decimal('0.00')
            total_amount = Decimal('0.00')
            for invoice in records:
                with Transaction().set_context(date=invoice.invoice_date):
                    total_untaxed_amount += invoice.currency.compute(
                        invoice.currency, invoice.untaxed_amount, invoice.company.currency)
                    total_amount += invoice.currency.compute(
                        invoice.currency, invoice.total_amount, invoice.company.currency)
            context['total_untaxed_amount'] = total_untaxed_amount
            context['total_amount'] = total_amount
            context['company'] = context['user'].company
            context['general'] = general_dict
            context['records'] = records
        return context
