# -*- coding: utf-8 -*-
"""pending_pay.py.

This file contains all the classes(Models, Wizards and Reports) for
execute and show a report that contains the invoices unpaid o parcial
paid of clients.

:copyright: (c) 2020 by Grupo ConnectTix SAC
:license: see LICENSE for more details.
"""
from decimal import Decimal
from datetime import date, datetime

from trytond.pool import Pool
from trytond.model import ModelView, fields
from trytond.report import Report
from trytond.wizard import Button, StateReport, StateView, Wizard
from trytond.transaction import Transaction


class PendingPayView(ModelView):
    """Pending Pay"""
    __name__ = 'pending.pay'

    party = fields.Many2One('party.party', 'Tercero', required=True)
    start_date = fields.Date('Desde')
    end_date = fields.Date('Hasta')
    invoice_currency = fields.Selection([
        ('PEN', "Soles"),
        ('USD', "Dólar"),
        ('both', "Ambas monedas")
    ], "Moneda")
    invoice_type = fields.Selection([
        ('commercial', "Factura"),
        ('simple', "Boleta"),
        ('commercial_credit', "Nota de crédito de factura"),
        ('simple_credit', "Nota de crédito de boleta"),
        ('commercial_debit', "Nota de débito de factura"),
        ('simple_debit', "Nota de débito de boleta"),
        ('all', "Todos los comprobantes"),
    ], "Comprobante")

    @staticmethod
    def default_invoice_type():
        return 'all'

    @staticmethod
    def default_invoice_currency():
        return 'both'


class PendingPayWizard(Wizard):
    """Pending Pay Wizard"""
    __name__ = 'pending.pay.wizard'

    start = StateView(
        'pending.pay',
        'sale_pe.pending_pay_view_form',
        [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Generar Reporte', 'gen_', 'tryton-ok', default=True),
        ]
    )
    gen_ = StateReport(
        'pending.pay.report',
    )

    def do_gen_(self, action):
        """Calls the report with the input data as paremeters"""

        return action, {
            'id': action['action'],
            'party': self.start.party.id,
            'end_date': self.start.end_date,
            'start_date': self.start.start_date,
            'invoice_type': self.start.invoice_type,
            'invoice_currency': self.start.invoice_currency,
        }


class PendingPayReport(Report):
    """Pending Pay Report"""
    __name__ = 'pending.pay.report'

    @classmethod
    def get_context(cls, records, data):
        """
        Add additional data to the context.
        records: Filtered invoices by client
        company: Current Company
        Also add restrictions
        """

        pool = Pool()
        total_usd = Decimal('0.00')
        pending_usd = Decimal('0.00')
        total_pen = Decimal('0.00')
        pending_pen = Decimal('0.00')
        extra_query = list()
        exchange_rate_dict = dict()
        usd_rate_dict = dict()
        amounts_dict = dict()
        today = datetime.today().strftime('%d/%m/%Y')

        Company = pool.get('company.company')
        company = Company(Transaction().context.get('company'))
        Party = pool.get('party.party')
        party = Party(data['party'])
        Invoice = pool.get('account.invoice')
        Rate = pool.get('currency.currency.rate')

        if data['start_date']:
            extra_query.append(('invoice_date', '>=', data['start_date']))
        if data['end_date']:
            extra_query.append(('invoice_date', '<=', data['end_date']))
        if data['invoice_type']:
            if data['invoice_type'] == 'all':
                pass
            else:
                extra_query.append(('document_type', '=', data['invoice_type']))

        records = Invoice.search([
            ('type', '=', 'out'),
            ('party', '=', party),
            ('state', '=', 'posted'),
            extra_query,
        ], order=[('invoice_date', 'ASC'),
                  ('document_type', 'ASC')])

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
                    exchange_rate = (1/invoice_rate[0].rate).quantize(Decimal('0.000'))
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
                    exchange_rate = (1/invoice_rate[0].rate).quantize(Decimal('0.000'))

            usd_rate = Rate.search([
                ('date', '<=', invoice_datetime),
                ('currency.code', '=', 'USD'),
            ], order=[('date', 'DESC')], limit=1)
            if usd_rate:
                usd_rate = (usd_rate[0].rate)

            amount_invoice_total = Decimal('0')
            amount_invoice_pend = Decimal('0')
            if data['invoice_currency'] == 'both' or not data['invoice_currency']:
                if invoice.currency.code == 'USD':
                    total_usd += invoice.total_amount
                    pending_usd += invoice.amount_to_pay
                if invoice.currency.code == 'PEN':
                    total_pen += invoice.total_amount
                    pending_pen += invoice.amount_to_pay
                amount_invoice_total = invoice.total_amount
                amount_invoice_pend = invoice.amount_to_pay
            elif data['invoice_currency'] == 'USD':
                if invoice.currency.code == 'USD':
                    amount_invoice_total = invoice.total_amount
                    amount_invoice_pend = invoice.amount_to_pay
                    total_usd += amount_invoice_total
                    pending_usd += amount_invoice_pend
                else:
                    amount_invoice_total = invoice.total_amount*usd_rate
                    amount_invoice_pend = invoice.amount_to_pay*usd_rate
                    total_usd += amount_invoice_total
                    pending_usd += amount_invoice_pend
            elif data['invoice_currency'] == 'PEN':
                if invoice.currency.code == 'PEN':
                    amount_invoice_total = invoice.total_amount
                    amount_invoice_pend = invoice.amount_to_pay
                    total_pen += amount_invoice_total
                    pending_pen += amount_invoice_pend
                else:
                    amount_invoice_total = invoice.total_amount*(1/usd_rate)
                    amount_invoice_pend = invoice.amount_to_pay*(1/usd_rate)
                    total_pen += amount_invoice_total
                    pending_pen += amount_invoice_pend
            exchange_rate_dict[invoice.id] = exchange_rate
            amounts_dict[invoice.id] = [
                amount_invoice_total.quantize(Decimal('0.00')),
                amount_invoice_pend.quantize(Decimal('0.00'))
            ]
            usd_rate_dict[invoice.id] = usd_rate

        User = pool.get('res.user')
        user = User(Transaction().user)
        user_report_name = user.name

        context = super(PendingPayReport, cls).get_context(records, data)
        context['exchange_rate'] = exchange_rate_dict
        context['total_amounts'] = amounts_dict
        context['usd_rate'] = usd_rate_dict
        context['records'] = records
        context['company'] = company
        context['party'] = party
        context['today'] = today
        context['user_report'] = user_report_name
        context['total_values'] = [total_pen.quantize(Decimal('0.00')),
                                   total_usd.quantize(Decimal('0.00')),
                                   pending_pen.quantize(Decimal('0.00')),
                                   pending_usd.quantize(Decimal('0.00'))]

        return context

    @classmethod
    def execute(cls, ids, data):
        """Override execute method to update report name"""
        with Transaction().set_context():
            result = super(PendingPayReport, cls).execute(ids, data)
        if len(ids) > 1:
            result = result[:2] + (True,) + result[3:]
        else:
            if data:
                report_code = 'Reporte Detallado Cliente '
                Party = Pool().get('party.party')
                party = Party(data.get('party'))
                party_name = party.name
                report_date = datetime.today().strftime('%d-%m-%Y')
                name = report_code + party_name + ' ' + report_date
                result = result[:3] + (name,)
        return result


class PendingPayAccumulatedView(ModelView):
    '''Pending Pay Accumulated View'''
    __name__ = 'pending.pay.accumulated'

    party = fields.Many2Many('party.party', None, None, string='Terceros')

    start_date = fields.Date('Desde')
    end_date = fields.Date('Hasta')
    invoice_currency = fields.Selection([
        ('PEN', "Soles"),
        ('USD', "Dólares"),
        ('both', "Ambas monedas")
    ],"Moneda")
    invoice_type = fields.Selection([
        ('commercial', "Factura"),
        ('simple', "Boleta"),
        ('commercial_credit', "Nota de crédito de factura"),
        ('simple_credit', "Nota de crédito de boleta"),
        ('commercial_debit', "Nota de débito de factura"),
        ('simple_debit', "Nota de débito de boleta"),
        ('all', "Todos los comprobantes"),
    ],"Comprobante")

    @staticmethod
    def default_invoice_type():
        return 'all'

    @staticmethod
    def default_invoice_currency():
        return 'both'


class PendingPayAccumulatedWizard(Wizard):
    '''Pending Pay Accumulated Wizard'''
    __name__ = 'pending.pay.accumulated.wiz'

    start = StateView(
        'pending.pay.accumulated',
        'sale_pe.pending_pay_accumulated_view_form', 
        [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Generar Reporte', 'gen_', 'tryton-ok', default=True),
        ]
    )
    gen_ = StateReport(
        'pending.pay.accumulated.report',
    )

    def do_gen_(self, action):
        parties_ids_list = list()
        if len(self.start.party) == 0:
            party_ = Pool().get('party.party')
            party_ = party_.search([('active', '=', True)])
            self.start.party = party_
        for par in self.start.party:
            parties_ids_list.append(par.id)
        return action, {
            'id': action['action'],
            'party': parties_ids_list,
            'end_date': self.start.end_date,
            'start_date': self.start.start_date,
            'invoice_type': self.start.invoice_type,
            'invoice_currency': self.start.invoice_currency,
        }


class PendingPayAccumulatedReport(Report):
    '''Pending Pay Accumulated Report'''
    __name__ = 'pending.pay.accumulated.report'

    @classmethod
    def __setup__(cls):
        super(PendingPayAccumulatedReport, cls).__setup__()

    @classmethod
    def filter_invoice(cls, idparty, money, data):
        '''
        conditions are in data except the name of the currency
        1.-data['start_date']=> start date(05/01/2019)
        2.-data['end_date']=>   end date(05/31/2019)
        3.-data['invoice_type'] => document type (commercial,simple ...)
        and so on
        '''
        InvoiceObject = Pool().get('account.invoice')
        currency = Pool().get('currency.currency')
        query = list()
        query.append(('state', '!=', 'draft'))
        if data['start_date']:
            query.append(('invoice_date', '>=', data['start_date']))
        if data['end_date']:
            query.append(('invoice_date', '<=', data['end_date']))
        if (data['invoice_type']==''):
            data['invoice_type']='all'
        if data['invoice_type']:
            if data['invoice_type'] == 'commercial':  # factura
                query.append(('document_type', '=', 'commercial'))

            if data['invoice_type'] == 'simple':  # Boleta
                query.append(('document_type', '=', 'simple'))

            if data['invoice_type'] == 'commercial_credit':  # Nota de credito de factura
                query.append(('document_type', '=', 'commercial_credit'))

            if data['invoice_type'] == 'simple_credit':  # Nota de credito de boleta
                query.append(('document_type', '=', 'simple_credit'))

            if data['invoice_type'] == 'commercial_debit': # Nota de debito de factura
                query.append(('document_type', '=', 'commercial_debit'))

            if data['invoice_type'] == 'simple_debit': # Nota de debito de boleta
                query.append(('document_type', '=', 'simple_debit'))

            if data['invoice_type'] == 'all':
                query.append(('document_type', 'in', [
                             'simple',
                             'commercial',
                             'commercial_credit',
                             'simple_credit',
                             'commercial_debit',
                             'simple_debit']))
        query.append(('party', '=', idparty))
        query.append(('type', '=', 'out'))

        if money != '':
            ''' to return invoices in only soles or dollars '''
            if money == 'PEN':
                soles = currency.search([('code', '=', 'PEN')])
                query.append(('currency', '=', soles[0].id))
            if money == 'USD':
                dollar = currency.search([('code', '=', 'USD')])
                query.append(('currency', '=', dollar[0].id))

        invoices = InvoiceObject.search(query)
        return invoices

    @classmethod
    def exchangeInvoice(cls, invoice):
        Rate = Pool().get('currency.currency.rate')
        exchange_rate = invoice.currency.rate
        if invoice.document_type in ['commercial_credit', 'commercial_debit',
                                     'simple_credit', 'simple_debit']:
            modified_invoice_date = invoice.modified_document_date
            invoice_datetime = datetime(
                modified_invoice_date.year,
                modified_invoice_date.month,
                modified_invoice_date.day)
            if not invoice_datetime:
                invoice_datetime = date.today()
            invoice_rate = Rate.search([
                ('date', '<=', invoice_datetime),
                ('currency.code', '=', 'USD'),
            ], order=[('date', 'DESC')], limit=1)
            if invoice_rate:
                exchange_rate = invoice_rate[0].rate
        else:
            if invoice.invoice_date:
                invoice_datetime = datetime(
                    invoice.invoice_date.year,
                    invoice.invoice_date.month,
                    invoice.invoice_date.day)
            else:
                invoice_datetime = date.today()
            invoice_rate = Rate.search([
                ('date', '<=', invoice_datetime),
                ('currency.code', '=', 'USD'),
            ], order=[('date', 'DESC')], limit=1)
            if invoice_rate:
                exchange_rate = invoice_rate[0].rate
        return exchange_rate

    @classmethod
    def get_context(cls, records, data):
        context = super(PendingPayAccumulatedReport,cls).get_context(records, data)
        Party = Pool().get('party.party')
        today = datetime.today().strftime('%d/%m/%Y')
        User = Pool().get('res.user')
        user = User(Transaction().user)
        user_report_name = ''
        if user:
            user_report_name = user.name

        money = 0
        query = list()
        result_row = list()
        for idparty in data['party']:
            invoicesPEN = cls.filter_invoice(idparty, 'PEN', data)
            invoicesUSD = cls.filter_invoice(idparty, 'USD', data)
            party = Party(idparty)
            invoices = invoicesPEN
            total_amountPEN = Decimal('0.00')
            total_deudePEN = Decimal('0.00')
            total_amountUSD = Decimal('0.00')
            total_deudeUSD = Decimal('0.00')
            result_col = list()
            if invoicesPEN or invoicesUSD:
                if invoicesPEN:
                    for invoice in invoicesPEN:
                        if data['invoice_currency'] == 'USD':
                            exchange_rate = cls.exchangeInvoice(invoice)
                            total_amountPEN += invoice.total_amount * exchange_rate
                            if invoice.state == 'posted':
                               total_deudePEN += invoice.amount_to_pay * exchange_rate
                        else:
                            total_amountPEN += invoice.total_amount
                            if invoice.state == 'posted':
                               total_deudePEN += invoice.amount_to_pay
                if invoicesUSD:
                    for invoice in invoicesUSD:
                        if data['invoice_currency'] == 'PEN':
                            exchange_rate = cls.exchangeInvoice(invoice)
                            exchange_rate = (1/exchange_rate)
                            total_amountUSD += invoice.total_amount * exchange_rate
                            if invoice.state == 'posted':
                                total_deudeUSD += invoice.amount_to_pay * exchange_rate
                        else:
                            total_amountUSD += invoice.total_amount
                            if invoice.state == 'posted':
                                total_deudeUSD += invoice.amount_to_pay
                if data['invoice_currency'] == 'both':
                    total_amountPEN = total_amountPEN.quantize(Decimal('0.00'))
                    total_amountUSD = total_amountUSD.quantize(Decimal('0.00'))
                    result_row.append([
                        party.document_number, party.name, 'PEN', 
                        total_amountPEN, total_deudePEN
                    ])
                    result_row.append([
                        party.document_number, party.name, 'USD', 
                        total_amountUSD, total_deudeUSD
                    ])
                else:
                    total_amout = (total_amountPEN + total_amountUSD).quantize(Decimal('0.00'))
                    total_deude = (total_deudePEN + total_deudeUSD).quantize(Decimal('0.00'))
                    result_row.append([
                        party.document_number, party.name, data['invoice_currency'], 
                        total_amout, total_deude
                    ])

        context['table_rusult'] = result_row
        context['company'] = context['user'].company
        context['dateStar'] = data['start_date']
        context['dateEnd'] = data['end_date']
        context['user'] = user_report_name
        context['today'] = today

        return context
    
    @classmethod
    def execute(cls, ids, data):
        """Override execute method to update report name"""
        with Transaction().set_context():
            result = super(PendingPayAccumulatedReport, cls).execute(ids, data)
        if len(ids) > 1:
            result = result[:2] + (True,) + result[3:]
        else:
            if data:
                name = 'Reporte Acumulado Clientes'
                result = result[:3] + (name,)

        return result

 