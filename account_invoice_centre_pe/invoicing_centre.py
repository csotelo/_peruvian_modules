# -*- coding: utf-8 -*-
"""
.. module:: account_invoicing_centre_pe.invoicing_centre
    :plataform: Independent
    :synopsis: Invoice centre module models
.. moduleauthor: Connecttix <development@connecttix.pe>
.. copyright: (c) 2018
.. organization: Connecttix - PE
.. license: GPL v3.
"""


from collections import OrderedDict
from datetime import datetime
from decimal import Decimal

from trytond.exceptions import UserWarning
from trytond.model import ModelSingleton, ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, If
from trytond.report import Report
from trytond.rpc import RPC
from trytond.transaction import Transaction

__all__ = [
    'InvoicingCentre',
    'InvoicingCentreStatement',
    'InvoicingCentreStatementLine',
    'InvoicingCentreStatementOut',
    'InvoicingCentreStatementOutSequences',
    'InvoiceCentreInvoiceSequence'
]

__metaclass__ = PoolMeta

_STATES = {
    'readonly': Eval('state') != 'draft',
}

_DEPENDS = ['state']

_ZERO = Decimal('0.0')


class InvoicingCentre(ModelSQL, ModelView):
    'Invoicing Centre'
    __name__ = 'account.invoice.centre'

    name = fields.Char(
        'Centro de facturación',
        required=True
    )
    description = fields.Text(
        "Descripción"
    )
    statements = fields.One2Many(
        'account.invoice.centre.statement',
        'invoicing_centre',
        "Procesos"
    )
    invoice_sequences = fields.Many2Many(
        'account.invoice.centre-account.invoice.sequence',
        'centre',
        'sequence',
        "Secuencias",
    )
    can_post = fields.Boolean(
        "Puede contabilizar",
    )
    can_pay = fields.Boolean(
        "Puede registrar pagos",
    )
    active = fields.Boolean('Activo')

    @staticmethod
    def default_active():
        return True

    @staticmethod
    def default_can_post():
        return True

    @staticmethod
    def default_can_pay():
        return True

    @classmethod
    def __setup__(cls):
        super(InvoicingCentre, cls).__setup__()


class InvoicingCentreStatement(ModelSQL, ModelView):
    "Diario de centro de facturación"
    __name__ = 'account.invoice.centre.statement'

    invoicing_centre = fields.Many2One(
        'account.invoice.centre',
        "Centro de facturación",
        states={
            'readonly': Eval('state').in_(['draft', 'validated', 'posted'])
        },
        depends=['state'],
        required=True
    )
    invoices = fields.One2Many(
        'account.invoice',
        'invoicing_centre_statement',
        'Comprobantes de pago',
        states={
            'readonly': Eval('state').in_(['validated', 'posted', 'paid'])
        },
        depends=['state'],
    )
    invoices_paid = fields.Function(
        fields.One2Many('account.invoice',
                        None,
                        'Facturas Pagadas'),
        'get_invoices_paid'
    )

    currency = fields.Many2One('currency.currency', 'Moneda')
    currency_rate = fields.Numeric('Tipo de cambio',  digits=(20, 3))
    second_currency = fields.Many2One('currency.currency', 'Segunda Moneda')
    second_currency_rate = fields.Function(fields.Numeric(
        'Tipo de cambio Segunda Moneda'), 'get_second_currency_rate')
    invoicing_centre_statement_date = fields.Date(
        "Fecha",
        readonly=True,
        required=True
    )
    opening_datetime = fields.DateTime(
        "Apertura",
        readonly=True,
        required=True,
    )
    closing_datetime = fields.DateTime(
        "Cierre",
        readonly=True,
    )
    opening_balance = fields.Numeric(
        "Caja Chica - Saldo Inicial",
        states={
            'readonly': Eval('state').in_(['draft', 'validated', 'posted'])
        },
        depends=['state'],
    )
    closing_balance = fields.Function(
        fields.Numeric(
            "Caja Chica - Saldo Final",
            readonly=True
        ),
        'get_closing_balance'
    )
    invoiced_amount = fields.Function(
        fields.Numeric(
            "Monto facturado"
        ),
        'get_invoiced_amount'
    )
    paid_amount = fields.Function(
        fields.Numeric(
            "Monto pagado"
        ),
        'get_paid_amount'
    )

    supplier_paid_amount = fields.Function(
        fields.Numeric(
            "Monto pagado a proveedores"
        ),
        'get_supplier_paid_amount'
    )

    supplier_invoiced_amount = fields.Function(
        fields.Numeric(
            'Monto Facturado a proveedores'
        ),
        'get_supplier_invoiced_amount'
    )
    final_amount = fields.Function(
        fields.Numeric(
            'Saldo Final',
        ),
        'get_final_amount'
    )

    statement_lines_amount = fields.Function(
        fields.Numeric(
            "Extracto monetario",
            digits=(16, 2)
        ),
        'get_statement_lines_amount'
    )
    statement_outs_amount = fields.Function(
        fields.Numeric(
            "Salidas"
        ),
        'get_statement_outs_amount'
    )
    state = fields.Selection(
        [
            ('new', 'Nueva'),
            ('draft', 'Borrador'),
            ('validated', 'Validada'),
            ('posted', 'Cerrada')
        ],
        'Estado',
        required=True,
        readonly=True
    )
    statement_outs = fields.One2Many(
        'centre.out',
        'invoicing_centre_statement',
        'Salida de Caja',
        states={
            'readonly': Eval('state').in_(['validated', 'posted'])
        },
        depends=['state'],
    )
    statement_lines = fields.One2Many(
        'centre.line',
        'invoicing_centre_statement',
        'Detalle monetario',
        states={
            'readonly': Eval('state').in_(['validated', 'posted'])
        },
        depends=['state'],

    )
    payment_lines = fields.Many2Many(
        'account.invoice-account.move.line',
        'invoice_centre_statement',
        'line',
        string="Factura - Líneas de pago",
    )
    active = fields.Boolean(
        'Active',
        select=True
    )

    @staticmethod
    def default_currency():
        Company = Pool().get('company.company')
        if Transaction().context.get('company'):
            company = Company(Transaction().context['company'])
            return company.currency.id

    @staticmethod
    def default_currency_rate():
        Company = Pool().get('company.company')
        if Transaction().context.get('company'):
            company = Company(Transaction().context['company'])
            return company.currency.round(1/company.currency.rate)

    @staticmethod
    def default_second_currency():
        Company = Pool().get('company.company')
        if Transaction().context.get('company'):
            company = Company(Transaction().context['company'])
            return company.second_currency.id

    @staticmethod
    def default_second_currency_rate():
        Company = Pool().get('company.company')
        if Transaction().context.get('company'):
            company = Company(Transaction().context['company'])
            return company.second_currency.round(1/company.second_currency.rate)

    @classmethod
    def default_state(cls):
        return 'new'

    @classmethod
    def default_invoicing_centre_statement_date(cls):
        Date = Pool().get('ir.date')
        return Date.today()

    @classmethod
    def default_opening_datetime(cls):
        return datetime.now()

    @classmethod
    def default_opening_balance(cls):
        return Decimal('0.0')

    @classmethod
    def default_final_sald(cls):
        return 0

    @staticmethod
    def default_active():
        return True

    @classmethod
    def __setup__(cls):
        super(InvoicingCentreStatement, cls).__setup__()

        cls._buttons.update({
            'open_invoicing_centre_statement': {
                'invisible': Eval('state') != 'new',
            },

            'draft_invoicing_centre_statement': {
                'invisible': (
                    ~Eval('state').in_(['validated']) | (
                        (Eval('state') == 'cancel')
                    )
                ),
                'icon': If(
                    Eval('state') == 'cancel',
                    'tryton-clear',
                    'tryton-back'
                ),
            },
            'validate_invoicing_centre_statement': {
                'invisible': Eval('state') != 'draft',
            },
            'post_invoicing_centre_statement': {
                'invisible': ~Eval('state').in_(['draft', 'validated']),
            },
        })

    def get_closing_balance(self, name=None):
        '''Returns the closing balance of the current invoicing centre.
           This cannot be negative.'''
        balance = self.opening_balance
        if self.opening_balance and self.statement_outs_amount:
            balance = self.opening_balance - self.statement_outs_amount
        return balance

    def get_invoiced_amount(self, name=None):
        Company = Pool().get('company.company')
        currency = None
        if Transaction().context.get('company'):
            company = Company(Transaction().context['company'])
            currency = company.currency
        if not currency:
            return None
        amount = Decimal('0.0')
        for invoice in self.invoices:
            if invoice.type == 'out':
                amount += currency.compute(
                    invoice.currency,
                    invoice.total_amount,
                    currency,
                    round=True
                )
        return amount

    def get_paid_amount(self, name=None):
        result = 0
        for payment_line in self.payment_lines:
            result += payment_line.credit
        return result
        Company = Pool().get('company.company')
        Invoices = Pool().get('account.invoice')
        currency = None
        if Transaction().context.get('company'):
            company = Company(Transaction().context['company'])
            currency = company.currency
        if not currency:
            return None
        amount = Decimal('0.0')
        for payment_line in self.payment_lines:
            if payment_line.credit != 0:
                document_type = ['commercial', 'simple']
            else:
                document_type = ['commercial_credit', 'simple_credit']
            invoice = Invoices.search(
                [('account', '=', payment_line.account),
                 ('type', '=', 'out'),
                 ('document_type', 'in', document_type),
                 ])
            invoice_exist = False
            for inv in invoice:
                if payment_line in inv.payment_lines:
                    invoice_exist = True
            # if invoice:
            #    if invoice[0].payment_lines:
            #        if invoice[0].payment_lines[0] == payment_line:
            #            invoice_exist = True
            if invoice_exist:
                amount += (currency.compute(
                    currency,
                    payment_line.credit,
                    currency,
                    round=True
                ) - currency.compute(
                    currency,
                    payment_line.debit,
                    currency,
                    round=True
                ))
        return amount

    def get_supplier_paid_amount(self, name=None):
        result = 0
        for payment_line in self.payment_lines:
            result += payment_line.debit
        return result
        Company = Pool().get('company.company')
        Invoices = Pool().get('account.invoice')
        currency = None
        if Transaction().context.get('company'):
            company = Company(Transaction().context['company'])
            currency = company.currency
        if not currency:
            return None
        amount = Decimal('0.0')
        for payment_line in self.payment_lines:
            if payment_line.debit != 0:
                document_type = ['commercial', 'simple']
            else:
                document_type = ['commercial_credit', 'simple_credit']
            invoice = Invoices.search(
                [('account', '=', payment_line.account),
                 ('type', '=', 'in'),
                 ('document_type', 'in', document_type),
                 ])
            invoice_exist = False
            for inv in invoice:
                if payment_line in inv.payment_lines:
                    invoice_exist = True

            # if invoice:
            #    if invoice[0].payment_lines:
            #        if invoice[0].payment_lines[0] == payment_line:
            #            invoice_exist = True
            if invoice_exist:
                factor = 1
                amount += (currency.compute(
                    currency,
                    payment_line.debit,
                    currency,
                    round=True
                ) - currency.compute(
                    currency,
                    payment_line.credit,
                    currency,
                    round=True
                ))
        return amount

    def get_supplier_invoiced_amount(self, name=None):
        Company = Pool().get('company.company')
        currency = None
        if Transaction().context.get('company'):
            company = Company(Transaction().context['company'])
            currency = company.currency
        if not currency:
            return None
        amount = Decimal('0.0')
        for invoice in self.invoices:
            if invoice.type == 'in':
                amount += currency.compute(
                    invoice.currency,
                    invoice.total_amount,
                    currency,
                    round=True
                )
        return amount

    def get_statement_lines_amount(self, name=None):
        Company = Pool().get('company.company')
        currency = None
        if Transaction().context.get('company'):
            company = Company(Transaction().context['company'])
            currency = company.currency
        if not currency:
            return None
        amount = Decimal('0.0')
        for statement_line in self.statement_lines:
            amount += currency.round(
                statement_line.amount *
                statement_line.currency_rate)
        return amount

    def get_statement_outs_amount(self, name=None):
        '''Returns the total amount from all outs in the invoicing centre.
           This value cannot exceeds the opening balance'''
        amount = Decimal('0.0')
        StatementOut = Pool().get('centre.out')
        for statement_out in self.statement_outs:
            amount += statement_out.final_amount
        return amount

    def get_invoices_paid(self, name=None):
        '''Returns all invoices in lines'''
        invoice_list = tuple()
        for line in self.payment_lines:
            Invoice = Pool().get('account.invoice')
            line_account = line.account
            current_invoice = (
                Invoice.search(
                    [('account', '=', line_account)]
                )
            )
            for inv in current_invoice:
                if line in inv.payment_lines and not inv in self.invoices:
                    invoice_list += ((inv,),)
        return invoice_list

    def get_final_amount(self, name):
        '''Returns the difference betwenn out and in invoices'''
        return self.paid_amount - self.supplier_paid_amount

    def get_second_currency_rate(self, name):
        """Return the currency rate in the invoice centre date"""
        CurrencyRates = Pool().get('currency.currency.rate')
        if self.second_currency:
            currency_rate = CurrencyRates.search(
                [
                    ('date', '<=', self.invoicing_centre_statement_date),
                    ('currency', '=', self.second_currency),
                ],
                order=[('date', 'DESC')],
                limit=1
            )
            # If not exist a currency in the date or previosly then use the next
            if not currency_rate:
                next_currency_rate = CurrencyRates.search(
                    [
                        ('date', '>=', self.invoicing_centre_statement_date),
                        ('currency', '=', self.second_currency),
                    ],
                    order=[('date', 'ASC')],
                    limit=1
                )
                a = 1/next_currency_rate[0].rate
            else:
                a = 1/currency_rate[0].rate
            round_currency = a.quantize(Decimal('1.000'))
            return round_currency

    @classmethod
    @ModelView.button
    def draft_invoicing_centre_statement(cls, records):
        cls.write(records, {
            'state': 'draft'
        })

    @classmethod
    @ModelView.button
    def post_invoicing_centre_statement(cls, records):
        for record in records:
            if record.statement_lines_amount >= record.final_amount:
                cls.validate_invoicing_centre_statement(records)
                cls.write(records, {
                    'state': 'posted',
                    'closing_datetime': datetime.now()
                })
            else:
                cls.raise_user_error(
                    'No puede cerrar caja, el extracto es menor al saldo total'
                )

    @classmethod
    @ModelView.button
    def validate_invoicing_centre_statement(cls, records):
        for record in records:
            cls.write(records, {
                'state': 'validated',
            })

    @classmethod
    @ModelView.button
    def open_invoicing_centre_statement(cls, records):
        for record in records:
            cls.write(records, {
                'state': 'draft',
            })

    @classmethod
    def get_current_process(cls):
        Date = Pool().get('ir.date')

        invoicing_centre_statements = cls.search([
            ('state', '=', 'draft'),
            ('create_uid', '=', Transaction().user),
            ('invoicing_centre_statement_date', '=', Date.today()),
        ])

        if len(invoicing_centre_statements) > 1:
            cls.raise_user_error(
                'Hay más de una proceso de venta abierto'
            )
        if len(invoicing_centre_statements) < 1:
            cls.raise_user_error(
                'No se ha encontrado procesos de venta para este usuario'
            )
        return invoicing_centre_statements[0]

    @classmethod
    def create(cls, vlist):
        invoicing_centre_statement_ids = None
        Date = Pool().get('ir.date')
        CurrencyRates = Pool().get('currency.currency.rate')
        invoicing_centre_statements = cls.search([
            ('state', '=', 'draft'),
            ('create_uid', '=', Transaction().user),
            ('invoicing_centre_statement_date', '=', Date.today()),
        ])
        invoicing_centre_statements = cls.search([
            ('state', '=', 'draft'),
            ('create_uid', '=', Transaction().user),
            ('invoicing_centre_statement_date', '=', Date.today()),
        ])
        vlist = [x.copy() for x in vlist]
        for values in vlist:
            invoicing_centre = values.get('invoicing_centre')
            second_currency = values.get('second_currency')
        invoicing_centre_statement_ids = cls.search([
            ('state', '=', 'draft'),
            ('invoicing_centre_statement_date', '=', Date.today()),
            ('invoicing_centre', '=', invoicing_centre),
        ])
        invoice_rate = CurrencyRates.search(
            [('date', '=', Date.today()),
             ('currency', '=', second_currency),
             ], order=[('date', 'DESC')], limit=1)
        if not invoice_rate:
            cls.raise_user_error(
                'No puede abrir caja. Debe haber tipo de cambio de dólar para hoy'
            )
        if invoicing_centre_statement_ids:
            cls.raise_user_error(
                'No se puede crear. Ya hay un proceso de venta con el mismo centro de facturación abierto'
            )

        if len(invoicing_centre_statements) > 0:
            cls.raise_user_error(
                'No se puede crear. Ya hay un proceso de venta abierto para este usuario'
            )
        return super(InvoicingCentreStatement, cls).create(vlist)


class InvoicingCentreStatementLine(ModelSQL, ModelView):
    'Extracto monetario de centro de facturación'
    __name__ = 'centre.line'

    invoicing_centre_statement = fields.Many2One(
        'account.invoice.centre.statement',
        'Estado de cuenta'
    )
    entry_type = fields.Selection(
        [
            ('cash', 'Efectivo'),
            ('card', 'Tarjeta de débito / crédito'),
        ],
        'Tipo de entrada'
    )
    entry_type_string = entry_type.translated('entry_type')
    currency = fields.Many2One('currency.currency', 'Moneda')
    currency_rate = fields.Numeric('Tipo de cambio',
                                   digits=(20, 3))
    denomination = fields.Numeric('Denominación')
    quantity = fields.Integer('Cantidad')
    amount = fields.Function(
        fields.Numeric('Monto'),
        'on_change_with_amount'
    )
    @staticmethod
    def default_currency():
        Company = Pool().get('company.company')
        if Transaction().context.get('company'):
            company = Company(Transaction().context['company'])
            return company.currency.id

    @staticmethod
    def default_currency_rate():
        Company = Pool().get('company.company')
        if Transaction().context.get('company'):
            company = Company(Transaction().context['company'])
            return company.currency.rate

    @classmethod
    def default_entry_type(cls):
        return 'cash'

    @classmethod
    def default_denomination(cls):
        return 0

    @classmethod
    def default_quantity(cls):
        return 0

    @classmethod
    def default_amount(cls):
        return 0

    @classmethod
    def default_subtotal(cls):
        return 0

    @fields.depends('final_amount')
    def on_change_amount(self, name=None):
        pass

    @fields.depends('denomination', 'quantity', 'currency')
    def on_change_with_amount(self, name=None):
        if not self.currency:
            self.raise_user_error("No currency was choosen!")
        currency = self.currency
        amount = (
            Decimal(str(self.denomination or '0.0')) * (
                self.quantity or Decimal(0.0)
            )
        )
        return currency.round(amount)

    @fields.depends('denomination', 'quantity', 'currency_rate', 'currency')
    def on_change_with_subtotal(self, name=None):
        if not self.currency:
            self.raise_user_error("No currency was choosen!")
        currency = self.currency
        subtotal = (
            Decimal(str(self.denomination or '0.0')) * (
                self.quantity or Decimal(0.0)
            ) * (self.currency_rate or Decimal(0.0))
        )
        return currency.round(subtotal)

    @fields.depends('currency')
    def on_change_with_currency_rate(self, name=None):
        try:
            Currency = Pool().get('currency.currency')
            currencies = Currency.search([
                ('id', '=', self.currency.id)
            ])
            return 1/currencies[0].rate
        except Exception:
            pass


class InvoicingCentreStatementOutSequences(ModelSingleton, ModelSQL, ModelView):
    'Standard Sequences for Invoicing Centre'
    __name__ = 'centre.out.sequences'

    account_invoicing_centre_statement_out_sequence = fields.Many2One(
        'ir.sequence',
        'POS Egress Sequence',
        required=True,
        domain=[('code', '=', 'centre.out')]
    )


class InvoicingCentreStatementOut(ModelSQL, ModelView):
    'Salidas de dentro de facturación'
    __name__ = 'centre.out'

    invoicing_centre_statement = fields.Many2One(
        'account.invoice.centre.statement',
        'Estado de cuenta'
    )
    number = fields.Numeric(
        'Número',
        readonly=True
    )
    statement_date = fields.Date(
        'Fecha',
        readonly=True,
    )
    reason = fields.Char('Motivo')
    description = fields.Text(
        'Descripción'
    )
    currency = fields.Many2One(
        'currency.currency',
        'Moneda',
        required=True,
    )
    currency_rate = fields.Function(
        fields.Numeric('Tipo de cambio'),
        'get_currency_rate'
    )
    final_amount = fields.Function(
        fields.Numeric(
            'Monto Final'
        ),
        'get_final_amount'
    )
    amount = fields.Numeric(
        'Monto',
        required=True
    )
    employee = fields.Many2One(
        'company.employee',
        'Empleado',
        required=True
    )
    authorized_by = fields.Many2One(
        'company.employee',
        'Autorizado por',
        required=True
    )
    authorized_date = fields.Date(
        'Fecha autorización',
        readonly=True
    )
    remain_amount = fields.Function(
        fields.Numeric('Saldo restante en la caja chica',
                       readonly=True),
        'get_remain_amount'
    )

    """@classmethod
    def create(cls, vlist):
        Sequence = Pool().get('ir.sequence')
        Config = Pool().get('centre.out.sequences')

        vlist = [x.copy() for x in vlist]
        for values in vlist:
            if not values.get('number'):
                config = Config(1)
                values['number'] = Sequence.get_id(
                    config.account_invoicing_centre_statement_out_sequence.id
                )

        return super(InvoicingCentreStatementOut, cls).create(vlist)"""

    @classmethod
    def default_statement_date(cls):
        Date = Pool().get('ir.date')
        return Date.today()

    @staticmethod
    def default_currency():
        Company = Pool().get('company.company')
        if Transaction().context.get('company'):
            company = Company(Transaction().context['company'])
            return company.currency.id

    @classmethod
    def default_currency_rate(cls):
        return 1

    @classmethod
    def default_invoicing_centre_statement(cls):
        InvoicingCentreStatement = Pool().get('account.invoice.centre.statement')
        Date = Pool().get('ir.date')

        invoicing_centre_statements = InvoicingCentreStatement.search([
            ('state', '=', 'draft'),
            ('create_uid', '=', Transaction().user),
            ('invoicing_centre_statement_date', '=', Date.today()),
        ])

        if len(invoicing_centre_statements) > 1:
            cls.raise_user_error(
                'Hay más de una proceso de venta abierto en esta caja'
            )
        if len(invoicing_centre_statements) < 1:
            cls.raise_user_error(
                'No se ha encontrado procesos de venta'
            )

        return invoicing_centre_statements[0]

    @fields.depends('final_amount', 'amount', 'currency_rate')
    def on_change_amount(self, name=None):
        if self.currency_rate:
            self.final_amount = self.amount*self.currency_rate

    @fields.depends('currency')
    def on_change_with_currency_rate(self, name=None):
        try:
            Currency = Pool().get('currency.currency')
            currencies = Currency.search([
                ('id', '=', self.currency.id)
            ])
            return currencies[0].rate
        except Exception:
            pass

    def get_currency_rate(self, name=None):
        if self.currency.code == 'USD':
            return self.invoicing_centre_statement.second_currency_rate
        return 1

    def get_final_amount(self, name=None):
        return self.amount*Decimal(self.currency_rate)

    @fields.depends('amount', 'currency_rate')
    def on_change_with_subtotal(self, name=None):
        subtotal = (Decimal(str(self.amount or '0.0')) * (
            self.currency_rate or Decimal(0.0))
        )
        return subtotal

    def get_remain_amount(self, name):
        return self.invoicing_centre_statement.closing_balance

    @classmethod
    def create(cls, vlist):
        """Overwrite this method to avoid save when the amount is major than the open balance"""
        invoicing_centre_statement = Pool().get('account.invoice.centre.statement')
        i = invoicing_centre_statement.get_current_process()
        vlist = [x.copy() for x in vlist]
        for values in vlist:
            currency_rate = i.currency.rate if i.currency.id == values.get(
                'currency') else i.second_currency_rate
            if i.closing_balance - values.get('amount')*currency_rate < Decimal('0'):
                cls.raise_user_error(
                    'El monto de la salida es mayor al restante en la caja chica: %d' % i.closing_balance)
        return super(InvoicingCentreStatementOut, cls).create(vlist)

    @classmethod
    def write(cls, *args):
        """Overwrite this method to avoid save when the amount is major than the open balance"""
        invoicing_centre_statement = Pool().get('account.invoice.centre.statement')
        i = invoicing_centre_statement.get_current_process()
        actions = iter(args)
        for invoice_centre_out, values in zip(actions, actions):
            i_centre_out = invoice_centre_out[0]
            statement_out_target = ''
            for statement_out in i.statement_outs:
                if i_centre_out.id == statement_out.id:
                    statement_out_target = statement_out
                    currency_id = values.get('currency') if values.get(
                        'currency') else i_centre_out.currency.id
                    currency_rate = 1/i.currency.rate if i.currency.id == currency_id else 1 / \
                        i.second_currency.rate
                else:
                    continue
                if values.get('amount'):
                    if i.closing_balance + (statement_out_target.amount*currency_rate) - (values.get('amount')*currency_rate) < 0:
                        amount = i.closing_balance + \
                            (statement_out_target.amount*currency_rate)
                        cls.raise_user_error(
                            'El monto de la salida es mayor al restante en la caja chica: %d' % amount)
        return super(InvoicingCentreStatementOut, cls).write(*args)


class InvoicingCentreStatementReport(Report):
    __name__ = 'account.invoice.centre.statement'

    @classmethod
    def __setup__(cls):
        super(InvoicingCentreStatementReport, cls).__setup__()
        cls.__rpc__['execute'] = RPC(False)

    @classmethod
    def execute(cls, ids, data):
        return super(InvoicingCentreStatementReport, cls).execute(ids, data)

    @classmethod
    def _get_records(cls, ids, model, data):
        with Transaction().set_context(language=False):
            return super(
                InvoicingCentreStatementReport, cls
            )._get_records(ids[:1], model, data)

    @classmethod
    def format_dict_to_list(cls, invoicing_dict):
        """
        format a list in grid format, requires a dictionary of invoices

        :return: formated list
        """

        wide_size = 5
        height_size = 10
        # group must be a multiple of wide_size
        group_size = wide_size * height_size

        ordered_invoicing_dict = OrderedDict(sorted(invoicing_dict.items()))

        invoices_list = [v for k, v in list(ordered_invoicing_dict.items())]
        invoices_fixed_list = list()
        list_size = len(invoices_list)

        if list_size == 0:
            return list()

        for i in range(0, int(list_size / group_size) + 1):
            for j in range(0, height_size):
                row = list()
                for k in range(0, wide_size):
                    index = i * group_size + k * height_size + j
                    if index < list_size:
                        row.append({
                            'number': invoices_list[index]['number'],
                            'amount': invoices_list[index]['amount'],
                            'total_discount': invoices_list[index]['total_discount'],
                            'i': index + 1
                        })
                    else:
                        row.append({
                            'number': '', 'amount': 0.00, 'i': index + 1, 'total_discount': 0.00
                        })
                invoices_fixed_list.append(list(row))

        return invoices_fixed_list

    @classmethod
    def get_sumaries(cls, invoicing_dict, invoicing_name):
        total_docs = len(invoicing_dict)
        total_amount = 0.0
        total_invalid = 0
        total_paid = 0
        for k, v in list(invoicing_dict.items()):
            total_amount += v['amount']
            if v['status'] == 'draft':
                total_invalid += 1
            else:
                total_paid += 1
        return {
            'invoicing_name': invoicing_name,
            'total_docs': total_docs,
            'total_amount': total_amount,
            'total_invalid': total_invalid,
            'total_paid': total_paid
        }

    # @classmethod
    # def get_missed_invoices(cls, invoicing_centre_statement, journal_invoicing_documents):
    #     Invoice = Pool().get('account.invoice')

    #     invoicing_list = {}

    #     for payment_line in invoicing_centre_statement.payment_lines:
    #         line_desc = dict(
    #             item.split(
    #                 ":"
    #             ) for item in payment_line.description.split("|")
    #         )
    #         invoicing_document_number = '%s-%s' % (
    #             line_desc['DocumentType'],
    #             line_desc['InvoiceNumber']
    #         )
    #         if invoicing_document_number in journal_invoicing_documents:
    #             journal_invoicing_documents[invoicing_document_number][
    #                 'AmountPaid'] += float(line_desc['AmountPaid'])
    #             journal_invoicing_documents[invoicing_document_number][
    #                 'AmountRegistered'] += float(line_desc['AmountRegistered'])
    #             continue

    #         invoice = Invoice.search([
    #             ('document_type', '=', line_desc['DocumentType']),
    #             ('number', '=', line_desc['InvoiceNumber']),
    #         ])[0]
    #         if invoicing_document_number not in invoicing_list:
    #             invoicing_list[invoicing_document_number] = {
    #                 'InvoiceNumber': '{number}(NP)'.format(
    #                     number=invoice.number),
    #                 'AmountPaid': Decimal(0),  # 0
    #                 'CurrencyRatePaid': 1,  # TODO hot fix
    #                 'DocumentType': invoice.document_type,
    #                 'Journal': invoice.payment_types_string,
    #                 'CurrencyPaid': invoice.currency.code,
    #                 'AmountChange': 0.00,  # TODO hot fix
    #                 'AmountRegistered':  Decimal(0),  # 0
    #                 'status': invoice.state,
    #             }
    #         if invoice.state == 'paid':
    #             invoicing_list[invoicing_document_number]['InvoiceNumber'] =\
    #                 '{number}(N)'.format(number=invoice.number)
    #         invoicing_list[invoicing_document_number]['AmountPaid'] +=\
    #             Decimal(line_desc['AmountPaid'])
    #         invoicing_list[invoicing_document_number]['AmountRegistered'] +=\
    #             Decimal(line_desc['AmountRegistered'])

    #     return invoicing_list

    @classmethod
    def get_context(cls, records, data):
        """
           => Posted and paid
        A  => Nulled
        C  => Posted on this invoicing_centre journal
        P  => Posted on this invoicing_centre journal and no full paid on
              this invoicing_centre journal
        N  => Posted on other invoicing_centre journal and full paid on
              this invoicing_centre journal
        NP => Posted on other invoicing_centre journal and no full paid on this
              invoicing_centre journal

        :param records:
        :param data:
        :return:
        """

        User = Pool().get('res.user')
        Currency = Pool().get('currency.currency')
        InvoicingCentreStatement = Pool().get('account.invoice.centre.statement')

        user = User(Transaction().user)

        report_context = super(InvoicingCentreStatementReport, cls).get_context(records, data)

        report_context['company'] = user.company

        # Obtain all invoices paid in this centre but post in other
        for record in records:
            invoicing_centre_statement = InvoicingCentreStatement(record.id)
            missed_invoices = invoicing_centre_statement.get_invoices_paid()
            # report_context['missed_invoices'] = missed_invoices

        invoices_list = []

        simple_invoices = {}
        comercial_invoices = {}
        simple_credit_invoices = {}
        comercial_credit_invoices = {}
        simple_debit_invoices = {}
        comercial_debit_invoices = {}
        payments_types = {}

        # Total invoiced amount customer invoices

        c_t_simple_invoice = Decimal('0.0')
        c_t_commercial_invoice = Decimal('0.0')
        c_t_simple_credit_invoice = Decimal('0.0')
        c_t_commercial_credit_invoice = Decimal('0.0')
        c_t_simple_debit_invoice = Decimal('0.0')
        c_t_commercial_debit_invoice = Decimal('0.0')

        c_t_simple_paid = Decimal('0.0')
        c_t_commercial_paid = Decimal('0.0')
        c_t_simple_credit_paid = Decimal('0.0')
        c_t_commercial_credit_paid = Decimal('0.0')
        c_t_simple_debit_paid = Decimal('0.0')
        c_t_commercial_debit_paid = Decimal('0.0')

        # Total invoiced amount supplier invoices

        s_t_simple_invoice = Decimal('0.0')
        s_t_commercial_invoice = Decimal('0.0')
        s_t_simple_credit_invoice = Decimal('0.0')
        s_t_commercial_credit_invoice = Decimal('0.0')
        s_t_simple_debit_invoice = Decimal('0.0')
        s_t_commercial_debit_invoice = Decimal('0.0')

        s_t_simple_paid = Decimal('0.0')
        s_t_commercial_paid = Decimal('0.0')
        s_t_simple_credit_paid = Decimal('0.0')
        s_t_commercial_credit_paid = Decimal('0.0')
        s_t_simple_debit_paid = Decimal('0.0')
        s_t_commercial_debit_paid = Decimal('0.0')

        report_context['commercial_out_exist'] = 0
        report_context['simple_out_exist'] = 0
        report_context['commercial_credit_out_exist'] = 0
        report_context['simple_credit_out_exist'] = 0
        report_context['simple_debit_out_exist'] = 0
        report_context['commercial_debit_out_exist'] = 0
        report_context['commercial_in_exist'] = 0
        report_context['simple_in_exist'] = 0
        report_context['commercial_credit_in_exist'] = 0
        report_context['simple_credit_in_exist'] = 0
        report_context['simple_debit_in_exist'] = 0
        report_context['commercial_debit_in_exist'] = 0

        all_invoices_list = list()
        pay_types = dict()

        for record in records:
            invoicing_centre_statement = InvoicingCentreStatement(record.id)
            for miss_invoice in missed_invoices:
                all_invoices_list += miss_invoice
            all_invoices_list += invoicing_centre_statement.invoices
            report_context['all_invoices'] = all_invoices_list

            for payment_line in record.payment_lines:
                currency = Currency(
                    payment_line.get_amount_currency('amount_currency'))
                payment_type = payment_line.journal.name
                if payment_type not in pay_types:
                    pay_types[payment_type] = {
                        'amount': 0,
                        'amount_second_currency': 0
                    }
                pay_types[payment_type] = {
                    'payment_type':   payment_line.journal.name,
                    'amount': pay_types[payment_type][
                        'amount'
                    ] + (float(payment_line.credit))
                    - (float(payment_line.debit)),
                    'amount_second_currency': pay_types[payment_type][
                        'amount_second_currency']+(payment_line.amount_second_currency*-1)
                    if currency.code == 'USD'
                    else pay_types[payment_type]['amount_second_currency'],
                }

            for invoice in all_invoices_list:
                if invoice.document_type == 'commercial' and invoice.type == 'out':
                    if invoice:
                        report_context['commercial_out_exist'] = 1
                    for line in invoicing_centre_statement.payment_lines:
                        # if line.description == invoice.number:
                        if line in invoice.payment_lines:
                            c_t_commercial_paid += line.credit
                    c_t_commercial_invoice += invoice.currency.compute(
                        invoice.currency, invoice.total_amount, invoice.company.currency)
                # Add to the invoice amount to the total of the type of document
                if invoice.document_type == 'simple' and invoice.type == 'out':
                    if invoice:
                        report_context['simple_out_exist'] = 1
                    for line in invoicing_centre_statement.payment_lines:
                        # if line.description == invoice.number:
                        if line in invoice.payment_lines:
                            c_t_simple_paid += line.credit
                    c_t_simple_invoice += invoice.currency.compute(
                        invoice.currency, invoice.total_amount, invoice.company.currency)

                if invoice.document_type == 'commercial_credit' and invoice.type == 'out':
                    if invoice:
                        report_context['commercial_credit_out_exist'] = 1
                    for line in invoicing_centre_statement.payment_lines:
                        # if line.description == invoice.number:
                        if line in invoice.payment_lines:
                            c_t_commercial_credit_paid += line.debit
                    c_t_commercial_credit_invoice += invoice.currency.compute(
                        invoice.currency, invoice.total_amount, invoice.company.currency)

                if invoice.document_type == 'simple_credit' and invoice.type == 'out':
                    if invoice:
                        report_context['simple_credit_out_exist'] = 1
                    for line in invoicing_centre_statement.payment_lines:
                        # if line.description == invoice.number:
                        if line in invoice.payment_lines:
                            c_t_simple_credit_paid += line.debit
                    c_t_simple_credit_invoice += invoice.currency.compute(
                        invoice.currency, invoice.total_amount, invoice.company.currency)

                if invoice.document_type == 'commercial' and invoice.type == 'in':
                    if invoice:
                        report_context['commercial_in_exist'] = 1
                    for line in invoicing_centre_statement.payment_lines:
                        # if line.description == invoice.number:
                        if line in invoice.payment_lines:
                            s_t_commercial_paid += line.debit
                    s_t_commercial_invoice += invoice.currency.compute(
                        invoice.currency, invoice.total_amount, invoice.company.currency)

                if invoice.document_type == 'simple' and invoice.type == 'in':
                    if invoice:
                        report_context['simple_in_exist'] = 1
                    for line in invoicing_centre_statement.payment_lines:
                        # if line.description == invoice.number:
                        if line in invoice.payment_lines:
                            s_t_simple_paid += line.debit
                    s_t_simple_invoice += invoice.currency.compute(
                        invoice.currency, invoice.total_amount, invoice.company.currency)

                if invoice.document_type == 'commercial_credit' and invoice.type == 'in':
                    if invoice:
                        report_context['commercial_credit_in_exist'] = 1
                    for line in invoicing_centre_statement.payment_lines:
                        # if line.description == invoice.number:
                        if line in invoice.payment_lines:
                            s_t_commercial_credit_paid += line.credit
                    s_t_commercial_credit_invoice += invoice.currency.compute(
                        invoice.currency, invoice.total_amount, invoice.company.currency)

                if invoice.document_type == 'simple_credit' and invoice.type == 'in':
                    if invoice:
                        report_context['simple_credit_in_exist'] = 1
                    for line in invoicing_centre_statement.payment_lines:
                        # if line.description == invoice.number:
                        if line in invoice.payment_lines:
                            s_t_simple_credit_paid += line.credit
                    s_t_simple_credit_invoice += invoice.currency.compute(
                        invoice.currency, invoice.total_amount, invoice.company.currency)

                if invoice.document_type == 'simple_debit' and invoice.type == 'out':
                    if invoice:
                        report_context['simple_debit_out_exist'] = 1
                    for line in invoicing_centre_statement.payment_lines:
                        # if line.description == invoice.number:
                        if line in invoice.payment_lines:
                            c_t_simple_debit_paid += line.debit
                    c_t_simple_debit_invoice += invoice.currency.compute(
                        invoice.currency, invoice.total_amount, invoice.company.currency)

                if invoice.document_type == 'commercial_debit' and invoice.type == 'out':
                    if invoice:
                        report_context['commercial_debit_out_exist'] = 1
                    for line in invoicing_centre_statement.payment_lines:
                        # if line.description == invoice.number:
                        if line in invoice.payment_lines:
                            c_t_commercial_debit_paid += line.debit
                    c_t_commercial_debit_invoice += invoice.currency.compute(
                        invoice.currency, invoice.total_amount, invoice.company.currency)

                if invoice.document_type == 'simple_debit' and invoice.type == 'in':
                    if invoice:
                        report_context['simple_debit_in_exist'] = 1
                    for line in invoicing_centre_statement.payment_lines:
                        # if line.description == invoice.number:
                        if line in invoice.payment_lines:
                            s_t_simple_debit_paid += line.credit
                    s_t_simple_debit_invoice += invoice.currency.compute(
                        invoice.currency, invoice.total_amount, invoice.company.currency)

                if invoice.document_type == 'commercial_debit' and invoice.type == 'in':
                    if invoice:
                        report_context['commercial_debit_out_exist'] = 1
                    for line in invoicing_centre_statement.payment_lines:
                        # if line.description == invoice.number:
                        if line in invoice.payment_lines:
                            s_t_commercial_debit_paid += line.credit
                    s_t_commercial_debit_invoice += invoice.currency.compute(
                        invoice.currency, invoice.total_amount, invoice.company.currency)

        cashier_user = None

        journal_invoicing_documents = {}
        invoicing_record = None
        for record in records:
            if record.state != 'posted':
                continue
            invoicing_centre_statement = InvoicingCentreStatement(record.id)

            for invoice in invoicing_centre_statement.invoices:
                if cashier_user is None:
                    cashier_user = invoice.posted_by or invoice.posted_by_user
                    if invoice.posted_by:
                        cashier_user = '{name}'.format(
                            name=invoice.posted_by.party.name,
                            # last_name=invoice.posted_by.party.lastname
                        )
                    if invoice.posted_by_user:
                        cashier_user = invoice.posted_by_user.name

                if invoice.state == 'draft':
                    invoicing_record = {
                        'InvoiceNumber': '{number}(A)'.format(
                            number=invoice.number),
                        'AmountPaid': 0,
                        'CurrencyRatePaid': 1,  # TODO hot fix
                        'DocumentType': invoice.document_type,
                        'CurrencyPaid': invoice.currency.code,
                        'AmountChange': 0.00,  # TODO hot fix
                        'AmountRegistered': 0,
                        'status': invoice.state,
                        'TotalAmount': invoice.total_amount,
                        'TotalDiscount': invoice.total_discount
                    }
                elif invoice.state == 'posted' and\
                        invoice.total_amount == invoice.amount_to_pay:
                    invoicing_record = {
                        'InvoiceNumber': '{number}(C)'.format(
                            number=invoice.number),
                        'AmountPaid': 0,
                        'CurrencyRatePaid': 1,  # TODO hot fix
                        'DocumentType': invoice.document_type,
                        'CurrencyPaid': invoice.currency.code,
                        'AmountChange': 0.00,  # TODO hot fix
                        'AmountRegistered': 0,
                        'status': invoice.state,
                        'TotalAmount': invoice.total_amount,
                        'TotalDiscount': invoice.total_discount
                    }
                elif invoice.state == 'posted' and\
                        invoice.total_amount != invoice.amount_to_pay:
                    invoicing_record = {
                        'InvoiceNumber': '{number}(P)'.format(
                            number=invoice.number),
                        'AmountPaid': 0,
                        'CurrencyRatePaid': 1,  # TODO hot fix
                        'DocumentType': invoice.document_type,
                        'CurrencyPaid': invoice.currency.code,
                        'AmountChange': 0.00,  # TODO hot fix
                        'AmountRegistered': 0,
                        'status': invoice.state,
                        'TotalAmount': invoice.total_amount,
                        'TotalDiscount': invoice.total_discount
                    }
                elif invoice.state == 'paid':
                    invoicing_record = {
                        'InvoiceNumber': '{number}'.format(
                            number=invoice.number),
                        'AmountPaid': 0,
                        'CurrencyRatePaid': 1,  # TODO hot fix
                        'DocumentType': invoice.document_type,
                        'CurrencyPaid': invoice.currency.code,
                        'AmountChange': 0.00,  # TODO hot fix
                        'AmountRegistered': 0,
                        'status': invoice.state,
                        'TotalAmount': invoice.total_amount,
                        'TotalDiscount': invoice.total_discount
                    }

                if invoicing_record:
                    invoices_list.append(invoicing_record)
                journal_invoicing_documents['%s-%s' % (
                    invoice.document_type, invoice.number
                )] = invoicing_record

            # Full invoices list

            full_list = invoices_list
            """+ list(
                cls.get_missed_invoices(
                    invoicing_centre_statement,
                    journal_invoicing_documents).values()
            )"""
            for invoice in full_list:
                invoicing_dict = {
                    'number': invoice['InvoiceNumber'],
                    'amount': 0,
                    'total_amount': invoice['TotalAmount'],
                    'total_discount': invoice['TotalDiscount']
                }
                """invoicing_amount = float(
                    invoice['AmountRegistered']
                ) * float(
                    invoice['CurrencyRatePaid']
                )"""
                invoicing_amount = float(invoice['TotalAmount'])

                if invoice['DocumentType'] == 'simple':
                    if invoice['InvoiceNumber'] not in simple_invoices:
                        simple_invoices[
                            invoice['InvoiceNumber']] = invoicing_dict
                    simple_invoices[invoice['InvoiceNumber']][
                        'amount'] += invoicing_amount
                    simple_invoices[invoice['InvoiceNumber']][
                        'total_amount'] = invoice['TotalAmount']
                    simple_invoices[invoice['InvoiceNumber']]['status'] = (
                        invoice['status']
                    )
                elif invoice['DocumentType'] == 'commercial':
                    if invoice['InvoiceNumber'] not in comercial_invoices:
                        comercial_invoices[
                            invoice['InvoiceNumber']] = invoicing_dict
                    comercial_invoices[invoice['InvoiceNumber']][
                        'amount'] += invoicing_amount
                    comercial_invoices[invoice['InvoiceNumber']][
                        'total_amount'] = invoice['TotalAmount']
                    comercial_invoices[invoice['InvoiceNumber']]['status'] = (
                        invoice['status']
                    )
                elif invoice['DocumentType'] == 'simple_credit':
                    if invoice['InvoiceNumber'] not in simple_credit_invoices:
                        simple_credit_invoices[
                            invoice['InvoiceNumber']] = invoicing_dict
                    simple_credit_invoices[invoice['InvoiceNumber']][
                        'amount'] += invoicing_amount
                    simple_credit_invoices[invoice['InvoiceNumber']][
                        'total_amount'] = invoice['TotalAmount']
                    simple_credit_invoices[invoice['InvoiceNumber']][
                        'status'] = (
                        invoice['status']
                    )
                elif invoice['DocumentType'] == 'commercial_credit':
                    actual_invoice = invoice['InvoiceNumber']
                    if actual_invoice not in comercial_credit_invoices:
                        comercial_credit_invoices[
                            invoice['InvoiceNumber']] = invoicing_dict
                    comercial_credit_invoices[invoice['InvoiceNumber']][
                        'amount'] += invoicing_amount
                    comercial_credit_invoices[invoice['InvoiceNumber']][
                        'total_amount'] = invoice['TotalAmount']
                    comercial_credit_invoices[invoice['InvoiceNumber']][
                        'status'] = (
                        invoice['status']
                    )
            for invoice in all_invoices_list:
                if invoice.state not in ['posted', 'paid']:
                    continue
                for payment_line in invoice.payment_lines:
                    payment_type = payment_line.journal.name
                    if payment_type not in payments_types:
                        payments_types[payment_type] = {
                            'amount': 0,
                            'currency_rate': '',
                            'amount_second_currency': 0
                        }
                    payments_types[payment_type] = {
                        # line_desc['Journal'],
                        'payment_type':   payment_line.journal.name,
                        'amount': payments_types[payment_type][
                            'amount'
                        ] + (float(payment_line.credit)),
                        'amount_currency': payment_line.amount_currency,
                        'amount_second_currency': payments_types[payment_type][
                            'amount_second_currency'
                        ] + (float(payment_line.amount_second_currency or 0.0) * -1),

                    }

        sumaries = list()
        if simple_invoices:
            sumaries.append(cls.get_sumaries(simple_invoices, 'BOLETAS'))
        if comercial_invoices:
            sumaries.append(cls.get_sumaries(comercial_invoices, 'FACTURAS'))
        if simple_credit_invoices:
            sumaries.append(
                cls.get_sumaries(
                    simple_credit_invoices, 'NOTA DE CREDITO BOLETA'
                )
            )
        if comercial_credit_invoices:
            sumaries.append(
                cls.get_sumaries(
                    comercial_credit_invoices,
                    'NOTA DE CREDITO FACTURA'
                )
            )

        # data for 'RESUMEN DE DOCUMENTOS DE VENTA' table
        total_docs = 0
        total_amount = 0.0
        total_invalid = 0
        total_paid = 0
        for sumary in sumaries:
            total_docs += sumary['total_docs']
            total_amount += sumary['total_amount']
            total_invalid += sumary['total_invalid']
            total_paid += sumary['total_paid']

        general_totals = {
            'total_docs': total_docs,
            'total_amount': total_amount,
            'total_invalid': total_invalid,
            'total_paid': total_paid
        }

        simple_invoices_fixed_list = cls.format_dict_to_list(simple_invoices)
        comercial_invoices_fixed_list = cls.format_dict_to_list(comercial_invoices)
        simple_credit_invoices_fixed_list = cls.format_dict_to_list(simple_credit_invoices)
        comercial_credit_invoices_fixed_list = cls.format_dict_to_list(comercial_credit_invoices)

        # totals for 'FORMA DE PAGO' table
        total_payments = 0.0

        payments_types_list = list(pay_types.values())
        for payment_type in payments_types_list:
            total_payments += payment_type['amount']
        report_context['simple_invoices'] = simple_invoices_fixed_list
        report_context['comercial_invoices'] = comercial_invoices_fixed_list

        report_context[
            'simple_credit_invoices'] = simple_credit_invoices_fixed_list
        report_context[
            'comercial_credit_invoices'] = comercial_credit_invoices_fixed_list

        report_context['payments_types'] = payments_types_list

        report_context['sumaries'] = sumaries
        report_context['totals'] = general_totals

        report_context['total_payments'] = total_payments
        # report_context['total_importe'] = total_importe
        # report_context['total_change'] = total_change
        # report_context['total_registered'] = total_registered

        report_context['cashier_user'] = cashier_user
        report_context['c_t_simple_invoice'] = c_t_simple_invoice
        report_context['c_t_simple_paid'] = c_t_simple_paid
        report_context['c_t_commercial_invoice'] = c_t_commercial_invoice
        report_context['c_t_commercial_paid'] = c_t_commercial_paid
        report_context['c_t_simple_credit_invoice'] = c_t_simple_credit_invoice
        report_context['c_t_simple_credit_paid'] = c_t_simple_credit_paid
        report_context['c_t_commercial_credit_invoice'] = c_t_commercial_credit_invoice
        report_context['c_t_commercial_credit_paid'] = c_t_commercial_credit_paid
        report_context['c_t_simple_debit_invoice'] = c_t_simple_debit_invoice
        report_context['c_t_simple_debit_paid'] = c_t_simple_debit_paid
        report_context['c_t_commercial_debit_invoice'] = c_t_commercial_debit_invoice
        report_context['c_t_commercial_debit_paid'] = c_t_commercial_debit_paid
        report_context['s_t_simple_invoice'] = s_t_simple_invoice
        report_context['s_t_simple_paid'] = s_t_simple_paid
        report_context['s_t_commercial_invoice'] = s_t_commercial_invoice
        report_context['s_t_commercial_paid'] = s_t_commercial_paid
        report_context['s_t_simple_credit_invoice'] = s_t_simple_credit_invoice
        report_context['s_t_simple_credit_paid'] = s_t_simple_credit_paid
        report_context['s_t_commercial_credit_invoice'] = s_t_commercial_credit_invoice
        report_context['s_t_commercial_credit_paid'] = s_t_commercial_credit_paid
        report_context['s_t_simple_debit_invoice'] = s_t_simple_debit_invoice
        report_context['s_t_simple_debit_paid'] = s_t_simple_debit_paid
        report_context['s_t_commercial_debit_invoice'] = s_t_commercial_debit_invoice
        report_context['s_t_commercial_debit_paid'] = s_t_commercial_debit_paid

        pens = payments_types[
            'Efectivo Soles|PEN']['amount'] if payments_types.get(
            'Efectivo Soles|PEN', False) else 0.0
        usds = payments_types[
            'Efectivo Dolares|USD']['amount'] if payments_types.get(
            'Efectivo Dolares|USD', False) else 0.0

        report_context['cash_payment'] = Decimal(pens + usds)

        return report_context


class InvoiceCentreInvoiceSequence(ModelSQL):
    'Invoice Centre - Invoice Sequence'
    __name__ = 'account.invoice.centre-account.invoice.sequence'

    centre = fields.Many2One(
        'account.invoice.centre',
        "Invoice Centre",
        ondelete='CASCADE',
        select=True,
        required=True
    )
    sequence = fields.Many2One(
        'account.invoice.sequence',
        "Invoice Sequence",
        ondelete='RESTRICT',
        required=True
    )
