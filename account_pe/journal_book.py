# -*- coding: utf-8 -*-
# This file is part of the account_sunat_pe module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import copy
import os
import sys
from decimal import Decimal

from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool
from trytond.pyson import Eval, If
from trytond.report import Report
from trytond.transaction import Transaction
from trytond.wizard import Button, StateReport, StateView, Wizard

__all__ = [
    'JournalEbook',
    'JournalEbookWizard',
    'JournalEbookReport',
    'JournalEbookReportPLE',
    'JournalEbookReportSpread',
    'JournalEbookReportText',
    'JournalEbookAccounting',
    'MajorEbookWizard',
    'MajorEbookReport',
    'MajorEbookReportSpread',
    'MajorEbookReportText',
]

_DOCUMENT_TYPE = {
    None: '0',
    '': '0',
    'pe_dtn': '0',
    'pe_dni': '1',
    'pe_frg': '4',
    'pe_vat': '6',
    'pe_pas': '7',
    'pe_dip': 'A',
}

_SUNAT_DOCUMENT_TYPE = [
    ('', ''),
    ('01', 'FACTURA ELECTRÓNICA'),
    ('03', 'BOLETA DE VENTA'),
    ('07', 'NOTA DE CRÉDITO'),
    ('08', 'NOTA DE DÉBITO')
]

_MONTHS = {
    "01": 'ENERO',
    "02": 'FEBRERO',
    "03": 'MARZO',
    "04": 'ABRIL',
    "05": 'MAYO',
    "06": 'JUNIO',
    "07": 'JULIO',
    "08": 'AGOSTO',
    "09": 'SEPTIEMBRE',
    "10": 'OCTUBRE',
    "11": 'NOVIEMBRE',
    "12": 'DICIEMBRE',
}

MOVE_NULLED = '00000000'


class JournalEbook(ModelSQL, ModelView):
    """Generic PLE Definition."""

    __name__ = 'journal.ebook'

    fiscalyear = fields.Many2One(
        'account.fiscalyear',
        'Fiscalyear',
        required=True,
        domain=[
            ('company', '=', Eval('company', -1)),
        ],
        depends=['company']
    )
    period = fields.Many2One(
        'account.period',
        'Period',
        required=True,
        domain=[
            ('fiscalyear', '=', Eval('fiscalyear'))
        ],
        depends=['fiscalyear']
    )
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

    @staticmethod
    def default_company():
        return Transaction().context.get('company')


class JournalSunatRow(object):
    """Row implementation for Journal Book."""

    def __init__(self, line):
        self.period = sanitatize(self.get_period(line)),
        self.unique_code_operation = sanitatize(
            self.get_unique_code_operation(line)),
        self.correlative_number = sanitatize(
            self.get_correlative_number(line)),
        self.move_account = sanitatize(self.get_move_account(line)),
        self.unit_code = sanitatize(self.get_unit_code(line)),
        self.center = sanitatize(self.get_center(line)),
        self.type_currency = sanitatize(self.get_type_currency(line)),
        self.type_document = sanitatize(self.get_type_document(line)),
        self.number_document = sanitatize(self.get_number_document(line)),
        self.payment_document = sanitatize(self.get_payment_document(line)),
        self.voucher_serial_number = sanitatize(
            self.get_voucher_serial_number(line)),
        self.voucher_payment_number = sanitatize(
            self.get_voucher_payment_number(line)),
        self.accounting_date = sanitatize(self.get_accounting_date(line)),
        self.expiration_date = sanitatize(self.get_expiration_date(line)),
        self.operation_number = sanitatize(self.get_operation_number(line)),
        self.description = sanitatize(self.get_description(line)),
        self.referential_description = sanitatize(
            self.get_referential_description(line)),
        self.move_debit = sanitatize(self.get_move_debit(line)),
        self.move_credit = sanitatize(self.get_move_credit(line)),
        self.data = sanitatize(self.get_data(line)),
        self.operation_status = sanitatize(self.get_operation_status(line)),

    def get_period(self, line):
        '''Periodo
        Formato: Numérico
        1. Obligatorio
        2. Validar formato AAAAMM00
        3. 01 <= MM <= 12
        4. Menor o igual al periodo informado
        5. Si el periodo es igual a periodo informado, 
        campo 21 es igual a '1' 
        6. Si periodo es menor a periodo informado,
        entonces campo 21 es diferente a '1'
        '''
        if '-' not in line.move.period.name:
            line.raise_user_error(
                'El nombre del periodo debe tener el formato YYYY-mm')
        year, month = line.move.period.name.split('-')
        if not (month.isdigit() and year.isdigit()):
            line.raise_user_error(
                'El nombre del periodo debe tener el formato YYYY-mm'
            )
        if int(month) > 12 or int(month) < 1:
            line.raise_user_error(
                'El nombre del periodo tiene un mes incorrecto')
        period = line.move.period.name.replace('-', '') + '00'
        return period

    def get_unique_code_operation(self, line):
        '''Código único de la operación
        Formato: Texto
        1. Obligatorio
        2. Si el campo 21 es igual a '1', consignar el Código Único de la Operación (CUO) 
        de la operación que se está informando
        3. Si el campo 21 es igual a '8', consignar el Código Único de la Operación (CUO)
        que corresponda al periodo en que se omitió la anotación. 
        Para modificaciones posteriores se hará referencia a este 
        Código Único de la Operación (CUO)
        4. Si el campo 21 es igual a '9', consignar el Código Único de la Operación (CUO) 
        de la operación original que se modifica
        '''
        # Whatever the field 21 is, this always return the correlative.
        correlative = line.move.number
        return correlative

    def get_correlative_number(self, line):
        '''Número correlativo del asiento contable identificado en el campo 2. 
        Formato: Alfanumérico
        1. Obligatorio
        2. El primer dígito debe ser: A, M o C 
        '''
        move_type = "M"
        if line.move.move_type == 'open':
            move_type = "A"
        if line.move.move_type == 'close':
            move_type = "C"
        entry_corr = move_type + line.move.post_number.replace(
            "-", "")[:9] if line.move.post_number else MOVE_NULLED
        return entry_corr

    def get_move_account(self, line):
        '''Código de la cuenta contable desagregado en subcuentas
        al nivel máximo de dígitos utilizado,
        según la estructura 5.3 - Detalle del Plan Contable utilizado
        Formato: Numérico
        1. Obligatorio
        '''
        # The accounting plan is obtained in the accounts, then this
        # field has the internal values, and validation
        line_account_code = line.account.code

        return line_account_code

    def get_unit_code(self, line):
        '''Código de la Unidad de Operación, de la Unidad Económica
        Administrativa, de la Unidad de Negocio, de la Unidad de
        Producción, de la Línea, de la Concesión, del Local o del Lote, 
        de corresponder. 
        Formato: Alfanumérico
        '''
        return ''

    def get_center(self, line):
        '''Código del Centro de Costos, Centro de Utilidades
        o Centro de Inversión, de corresponder 
        Formato: Alfanumérico
        '''
        return ''

    def get_type_currency(self, line):
        '''Tipo de Moneda de origen
        Formato: Alfanumérico
        1. Obligatorio
        2. Validar con parámetro tabla 4
        '''
        # If are not origin invoice or document the currency
        # is the company currency by default
        currency = line.move.origin.currency.code \
            if line.move.origin \
            and line.move.origin.__name__ == 'account.invoice' \
            else line.move.company.currency.code
        return currency

    def get_type_document(self, line):
        '''Tipo de documento de identidad del emisor
        Formato: Alfanumérico
        1. Aplicar Regla general
        '''
        # If doesn't exist a origin document then this field hasn't a
        # value
        document_type = _DOCUMENT_TYPE[line.move.origin.party.document_type] \
            if line.move.origin \
            and line.move.origin.__name__ == 'account.invoice' \
            else ''
        return document_type

    def get_number_document(self, line):
        '''numero de documento de identidad del emisor
        Formato: Alfanumérico
        1. Aplicar Regla general
        '''
        # If doesn't exist a origin document then this field hasn't a
        # value
        document_number = line.move.origin.party.document_number \
            if line.move.origin and \
            line.move.origin.__name__ == 'account.invoice' else ''
        return document_number

    def get_payment_document(self, line):
        '''Tipo de Comprobante de Pago o Documento asociada a la operación,
        de corresponder
        Formato: Numérico 
        1. Obligatorio
        2. Validar con parámetro tabla 10
        '''
        # If doesn't exist a origin document then this field are 00
        invoice_document_type = line.move.origin.sunat_document_type \
            if line.move.origin and \
            line.move.origin.__name__ == 'account.invoice' else '00'
        return invoice_document_type

    def get_voucher_serial_number(self, line):
        '''Número de serie del comprobante de pago o documento 
        asociada a la operación, de corresponder
        Formato: Alfanumérico  
        1. Aplicar Regla General (tipo y nro. doc.)
        '''
        sunat_serial = line.move.origin.sunat_serial \
            if line.move.origin and \
            line.move.origin.__name__ == 'account.invoice' else ''
        return sunat_serial

    def get_voucher_payment_number(self, line):
        '''Número del comprobante de pago o documento asociada a la operación  
        Formato: Alfanumérico
        1. Obligatorio
        2. Aplicar Regla General (por tipo de doc.)
        '''
        # If doesn't exist a origin document then the value of this field is
        # 0000000
        sunat_number = line.move.origin.sunat_number \
            if line.move.origin and \
            line.move.origin.__name__ == 'account.invoice' and \
            line.move.origin.sunat_number != None else MOVE_NULLED
        return sunat_number

    def get_accounting_date(self, line):
        '''Fecha contable
        Formato: DD/MM/AAAA
        1. Menor o igual al periodo informado
        2. Menor o igual al periodo señalado en el campo 1.
        '''
        # All the moves have a date
        move_date = line.move.date.strftime('%d/%m/%Y')
        return move_date

    def get_expiration_date(self, line):
        '''Fecha de vencimiento 
        Formato: DD/MM/AAAA
        '''
        return ''

    def get_operation_number(self, line):
        '''Fecha de la operación o emisión
        Formato: DD/MM/AAAA
        1. Obligatorio
        2. Menor o igual al periodo informado
        3. Menor o igual al periodo señalado en el campo 1.
        '''
        # If the move hasn't a origin document then the date
        # of the move are seted by default
        if line.move.origin and \
                line.move.origin.__name__ == 'account.invoice':
            move_operation_date = \
                line.move.origin.invoice_date.strftime('%d/%m/%Y')
        else:
            move_operation_date = line.move.date.strftime('%d/%m/%Y')
        return move_operation_date

    def get_description(self, line):
        '''Glosa o descripción de la naturaleza de la operación registrada,
        de ser el caso.
        Formato: Texto
        1. Obligatorio
        '''
        # If the line hasn't a description the account name are seted by default
        if line.description:
            line_description = line.description.strip()
        else:
            line_description = line.account.name
        return line_description

    def get_referential_description(self, line):
        '''Glosa referencial, de ser el caso
        Formato: Texto
        '''
        return ''

    def get_move_debit(self, line):
        '''Movimientos del Debe
        Formato: Numérico
        1. Obligatorio
        2. Positivo o '0.00'
        3. Excluyente con campo 19
        4. Campo 18 y 19 pueden ser ambos 0.00
        5. La suma del campo 18 (correspondiente al Estado 1) 
        debe ser igual a la suma del campo 19
        '''
        debit_line = '{0:.2f}'.format(abs(line.debit))
        return debit_line

    def get_move_credit(self, line):
        '''Movimientos del Haber
        Formato: Numérico
        1. Obligatorio
        2. Positivo o '0.00'
        3. Excluyente con campo 18
        4. Campo 18 y 19 pueden ser ambos 0.00
        5. La suma del campo 18 (correspondiente al estado 1) 
        debe ser igual a la suma del campo 19.
        '''
        credit_line = '{0:.2f}'.format(abs(line.credit))
        return credit_line

    def get_data(self, line):
        '''
        Dato Estructurado: Código del libro, campo 1, campo 2 y 
        campo 3 del Registro de Ventas e Ingresos o del Registro de Compras, 
        separados con el carácter "&", de corresponder.
        Formato: Texto
        1. Obligatorio solo si el asiento contable en el Libro Diaro 
        no es consolidado, caso contrario no se consigna nada en este campo. 
        2. Código del Registro de Ventas e Ingresos: 140100
        3. Código del Registro de Compras: 080100 y 080200
        4. Validar estructuras de los campos 1, 2 y 3 del Registro de Ventas e
        Ingresos o del registro de Compras
        '''
        struct_data = ''
        book_type = ''
        # Only for moves in purchase and sales books
        if line.move.origin:
            if line.move.origin.__name__ == 'account.invoice':
                if line.move.origin.type == 'out':
                    book_type = '140100'
                if line.move.origin.type == 'in':
                    book_type = '080100'
                struct_data = '&'.join([book_type,
                                        self.period[0],
                                        self.unique_code_operation[0],
                                        self.correlative_number[0][:9]])
        # Force void for open and close moves, and othe operation types
        if line.move.move_type in ['close', 'open']:
            struct_data = ''
        return struct_data

    def get_operation_status(self, line):
        '''Indica el estado de la operación
        Formato: Numérico
        1. Obligatorio
        2. Registrar '1' cuando la operación corresponde al periodo.
        3. Registrar '8' cuando la operación corresponde a un periodo anterior
        y NO ha sido anotada en dicho periodo.
        4. Registrar '9' cuando la operación corresponde a un periodo anterior
        y SI ha sido anotada en dicho periodo.
        '''
        year, month = line.move.period.name.split('-')
        move_date_month = line.move.date.strftime('%m')
        if month != move_date_month:
            return '8'
        return '1'

    def get_ple_row(self):

        row_data = [
            'period',
            'unique_code_operation',
            'correlative_number',
            'move_account',
            'unit_code',
            'center',
            'type_currency',
            'type_document',
            'number_document',
            'payment_document',
            'voucher_serial_number',
            'voucher_payment_number',
            'accounting_date',
            'expiration_date',
            'operation_number',
            'description',
            'referential_description',
            'move_debit',
            'move_credit',
            'data',
            'operation_status',
        ]
        data = list()
        for attr in row_data:
            data.append(getattr(self, attr)[0])
        return '|'.join(data)


class AccountPlan(object):
    """Returns a clean list of the accounting plan."""

    def __init__(self, line, child, period):
        self.period = sanitatize(self.get_period(line, child, period))
        self.account_code = sanitatize(
            self.get_account_code(line, child, period)),
        self.account_description = sanitatize(
            self.get_account_description(line, child, period)),
        self.account_plan_code = sanitatize(
            self.get_account_plan_code(line, child, period)),
        self.account_plan_desc = sanitatize(
            self.get_account_plan_desc(line, child, period)),
        self.account_child_code = sanitatize(
            self.get_account_child_code(line, child, period)),
        self.account_child_desc = sanitatize(
            self.get_account_child_desc(line, child, period)),
        self.operation_status = sanitatize(
            self.get_operation_status(line, child, period)),

    def get_period(self, account, child, period):
        '''Periodo
        Formato: Numérico
        1. Obligatorio
        2. Validar formato AAAAMMDD
        3. 01 <= MM <= 12
        4. Menor o igual al periodo informado
        5. Si el periodo es igual a periodo informado, campo 8 es igual a '1'.
        6. Si periodo es menor a periodo informado, entonces campo 8 es
        diferente a '1'
        '''
        Period = Pool().get('account.period')
        actual_period = Period(period)
        actual_period = actual_period.name.replace('-', '') + '00'
        return period

    def get_account_code(self, account, child, period):
        '''Código de la Cuenta Contable desagregada hasta el nivel máximo de
        dígitos utilizado
        Formato: Numérico
        1. Obligatorio
        2. Desde tres dígitos hasta el nivel el nivel máximo de dígitos
        utilizado por cuenta contable.
        '''
        return account.code

    def get_account_description(self, account, child, period):
        '''Descripción de la Cuenta Contable desagregada al nivel máximo
        de dígitos utilizado
        Formato: Texto
        1. Obligatorio
        '''
        return account.name

    def get_account_plan_code(self, account, child, period):
        '''Código del Plan de Cuentas utilizado por el deudor tributario
        Formato: Numérico
        1. Obligatorio
        2. Validar con parámetro tabla 17
        '''
        return '01'

    def get_account_plan_desc(self, account, child, period):
        '''Descripción del Plan de Cuentas utilizado por el deudor tributario
        Formato: Texto
        1. Obligatorio si campo 4 = 99
        '''
        return 'PLAN CONTABLE GENERAL EMPRESARIAL'

    def get_account_child_code(self, account, child, period):
        '''Código de la Cuenta Contable Corporativa desagregada hasta el nivel
        máximo de dígitos utilizado, cuando deban consolidar sus estados
        financieros según la Superintendencia del Mercado de Valores o sean
        Sucursales de una empresa no domiciliada o pertenezca a un Grupo
        Económico que consolida los estados financieros.
        Formato: Numérico
        '''
        return child.code

    def get_account_child_desc(self, account, child, period):
        '''Descripción de la Cuenta Contable Corporativa desagregada al nivel
        máximo de dígitos utilizado
        Formato: Texto
        1. Obligatorio si existe dato en el campo 6
        '''
        return child.name

    def get_operation_status(self, account, child, period):
        '''Indica el estado de la operación
        Formato: Numérico
        1. Obligatorio
        2. Registrar '1' cuando la Cuenta Contable se informa en el periodo.
        3. Registrar '8' cuando la Cuenta Contable se debió informar en un
        periodo anterior y NO se informó en dicho periodo.
        4. Registrar '9' cuando la Cuenta Contable se informó en un periodo
        anterior y se desea corregir.
        '''
        return '1'

    def get_ple_row(self):

        row_data = [
            'period',
            'account_code',
            'account_description',
            'account_plan_code',
            'account_plan_desc',
            'account_child_code',
            'account_child_desc',
            'operation_status',
        ]
        data = list()
        for attr in row_data:
            data.append(getattr(self, attr)[0])
        return '|'.join(data)


class JournalEbookWizard(Wizard):
    """Wizard Journal Book."""
    __name__ = 'journal.ebook.wizard'

    start = StateView(
        'journal.ebook',
        'account_pe.journal_ebook_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('PLE', 'ple_',
                   'tryton-ok', default=True),
            Button('Excel', 'spread_',
                   'tryton-ok'),
            Button('Texto', 'text_',
                   'tryton-ok'),
            Button('Plan de cuentas', 'accounting_',
                   'tryton-ok')
        ])

    ple_ = StateReport(
        'journal.ebook.report.ple'
    )
    plain_ = StateReport(
        'journal.ebook.report.plain'
    )
    text_ = StateReport(
        'journal.ebook.report.text'
    )
    spread_ = StateReport(
        'journal.ebook.report.spread'
    )
    accounting_ = StateReport(
        'journal.ebook.report.accounting'
    )

    def do_ple_(self, action):
        return action, {
            'id': action['action'],
            'company': self.start.company.id,
            'fiscalyear': self.start.fiscalyear.id,
            'period': self.start.period.id,
        }

    def do_plain_(self, action):
        return action, {
            'id': action['action'],
            'company': self.start.company.id,
            'fiscalyear': self.start.fiscalyear.id,
            'period': self.start.period.id,
        }

    def do_spread_(self, action):
        return action, {
            'id': action['action'],
            'company': self.start.company.id,
            'fiscalyear': self.start.fiscalyear.id,
            'period': self.start.period.id,
        }
    def do_text_(self, action):
        return action, {
            'id': action['action'],
            'company': self.start.company.id,
            'fiscalyear': self.start.fiscalyear.id,
            'period': self.start.period.id,
        }
    def do_accounting_(self, action):
        return action, {
            'id': action['action'],
            'company': self.start.company.id,
            'fiscalyear': self.start.fiscalyear.id,
            'period': self.start.period.id,
        }


class MajorEbookWizard(Wizard):
    """Wizard Journal Book."""
    __name__ = 'major.ebook.wizard'

    start = StateView(
        'journal.ebook',
        'account_pe.major_ebook_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('PLE', 'ple_',
                   'tryton-ok', default=True),
            Button('Excel', 'spread_',
                   'tryton-ok'),
            Button('Texto', 'text_',
                   'tryton-ok'),
        ])

    ple_ = StateReport(
        'major.ebook.report'
    )
    spread_ = StateReport(
        'major.ebook.report.spread'
    )
    text_ = StateReport(
        'major.ebook.report.text'
    )

    def do_ple_(self, action):
        return action, {
            'id': action['action'],
            'company': self.start.company.id,
            'fiscalyear': self.start.fiscalyear.id,
            'period': self.start.period.id,
        }

    def do_spread_(self, action):
        return action, {
            'id': action['action'],
            'company': self.start.company.id,
            'fiscalyear': self.start.fiscalyear.id,
            'period': self.start.period.id,
        }
    
    def do_text_(self, action):
        return action, {
            'id': action['action'],
            'company': self.start.company.id,
            'fiscalyear': self.start.fiscalyear.id,
            'period': self.start.period.id,
        }


class MajorEbookReport(Report):
    """Report Journal Book."""
    __name__ = 'major.ebook.report'

    @classmethod
    def __setup__(cls):
        super(MajorEbookReport, cls).__setup__()

    @classmethod
    def get_context(cls, records, data):
        AccountObject = Pool().get('account.move')
        Company = Pool().get('company.company')
        period_id = str(data['period'])
        Period = Pool().get('account.period')
        period = Period(period_id)
        year, month = period.name.split('-')
        records = AccountObject.search([
            ('company', '=', data['company']),
            ('period.fiscalyear', '=', data['fiscalyear']),
            ('state', '=', 'posted'),
        ],
            order=[('date', 'ASC')])
        context = super(MajorEbookReport, cls).get_context(
            records,
            data)
        move_dict = dict()
        for move in records:
            total_credit = Decimal('0.00')
            total_debit = Decimal('0.00')
            for line in move.lines:
                total_credit += line.credit
                total_debit += line.debit
            move_dict[move.id] = [total_credit, total_debit]
        context['lines'] = cls._prepare_lines(records, data)
        context['rows'] = cls._prepare_rows(records, data)
        context['move_dict'] = move_dict
        context['company'] = Company(Transaction().context.get('company'))
        context['month'] = _MONTHS[str(month)]
        context['year'] = year
        context['book_type'] = 'MAYOR'

        return context

    @classmethod
    def _prepare_rows(cls, records, data):
        rows = list()
        for move in records:
            for move_line in move.lines:
                report_line = JournalSunatRow(move_line)
                ple_row = report_line.get_ple_row()
                rows.append(ple_row)
        return rows

    @classmethod
    def _prepare_lines(cls, records, data):
        lines = list()
        for move in records:
            move_number = move.number
            for move_line in move.lines:
                report_line = JournalSunatRow(move_line)
                lines.append(report_line)
        return lines

    @classmethod
    def execute(cls, ids, data):
        """Override execute method to update report name."""
        Company = Pool().get('company.company')
        Period = Pool().get('account.period')
        with Transaction().set_context():
            result = super(MajorEbookReport, cls).execute(ids, data)
        company = Company(data.get('company'))
        period = Period(data.get('period'))
        if len(ids) > 1:
            result = result[:2] + (True,) + result[3:]
        else:
            if data:
                identifier = 'LE'  # Unique identifier for electronic books
                ruc = company.ruc  # Company RUC
                period = period.name  # Period
                year, month = period.split('-')  # Year and month
                day = '00'  # No day in journal book
                book_id = '060100'  # Journal Book identifier
                cc = '00'  # No applied
                OIM = '111'  # For Journal book
                G = '1'  # PLE generated
                name = identifier + ruc + year + month + day + book_id + cc + OIM + G

                oim = '111'
                result = result[:3] + (name,)
                result = ('txt',  result[1].strip(),) + result[2:]
        return result


class MajorEbookReportSpread(MajorEbookReport):
    """Report Major Book."""
    __name__ = 'major.ebook.report.spread'

    @classmethod
    def execute(cls, ids, data):
        """Override execute method to update the file extension."""
        result = super(MajorEbookReportSpread, cls).execute(ids, data)
        result = ('ods',) + result[1:]
        return result

class MajorEbookReportText(MajorEbookReport):
    """Report Major Book."""
    __name__ = 'major.ebook.report.text'

    @classmethod
    def execute(cls, ids, data):
        """Override execute method to update the file extension."""
        result = super(MajorEbookReportText, cls).execute(ids, data)
        result = ('txt',) + result[1:]
        return result


class JournalEbookReport(Report):
    """Report Journal Book."""
    __name__ = 'journal.ebook.report'

    @classmethod
    def __setup__(cls):
        super(JournalEbookReport, cls).__setup__()

    @classmethod
    def get_context(cls, records, data):
        AccountObject = Pool().get('account.move')
        Company = Pool().get('company.company')
        records = AccountObject.search([
            ('company', '=', data['company']),
            ('period', '=', data['period']),
            ('state', '=', 'posted'),
        ],
            order=[('date', 'ASC')])
        context = super(JournalEbookReport, cls).get_context(
            records,
            data)
        move_dict = dict()
        for move in records:
            total_credit = Decimal('0.00')
            total_debit = Decimal('0.00')
            for line in move.lines:
                total_credit += line.credit
                total_debit += line.debit
            move_dict[move.id] = [total_credit, total_debit]
        context['lines'] = cls._prepare_lines(records, data)
        context['rows'] = cls._prepare_rows(records, data)
        context['move_dict'] = move_dict
        context['company'] = Company(Transaction().context.get('company'))
        context['book_type'] = 'DIARIO'

        return context

    @classmethod
    def _prepare_rows(cls, records, data):
        rows = list()
        for move in records:
            for move_line in move.lines:
                report_line = JournalSunatRow(move_line)
                ple_row = report_line.get_ple_row()
                rows.append(ple_row)
        return rows

    @classmethod
    def _prepare_lines(cls, records, data):
        lines = list()
        for move in records:
            move_number = move.number
            for move_line in move.lines:
                report_line = JournalSunatRow(move_line)
                lines.append(report_line)
        return lines

    @classmethod
    def execute(cls, ids, data):
        """Override execute method to update report name."""
        Company = Pool().get('company.company')
        Period = Pool().get('account.period')
        with Transaction().set_context():
            result = super(JournalEbookReport, cls).execute(ids, data)
        company = Company(data.get('company'))
        period = Period(data.get('period'))
        if len(ids) > 1:
            result = result[:2] + (True,) + result[3:]
        else:
            if data:
                identifier = 'LE'  # Unique identifier for electronic books
                ruc = company.ruc  # Company RUC
                period = period.name  # Period
                year, month = period.split('-')  # Year and month
                day = '00'  # No day in journal book
                book_id = '050200'  # Journal Book identifier
                cc = '00'  # No applied
                OIM = '111'  # For Journal book
                G = '1'  # PLE generated
                name = identifier + ruc + year + month + day + book_id + cc + OIM + G

                oim = '111'
                result = result[:3] + (name,)
                result = ('txt',  result[1].strip(),) + result[2:]
        return result


class JournalEbookReportPLE(JournalEbookReport):
    """Report Journal Book."""
    __name__ = 'journal.ebook.report.ple'

    @classmethod
    def execute(cls, ids, data):
        """Override execute method to update report name."""
        result = super(JournalEbookReportPLE, cls).execute(ids, data)
        result = ('txt',  result[1].strip(),) + result[2:]
        return result

class JournalEbookReportSpread(JournalEbookReport):
    """Report Journal Book."""
    __name__ = 'journal.ebook.report.spread'

    @classmethod
    def execute(cls, ids, data):
        """Override execute method to update the file extension."""
        result = super(JournalEbookReportSpread, cls).execute(ids, data)
        result = ('ods',) + result[1:]
        return result

class JournalEbookReportText(JournalEbookReport):
    """Report Journal Book."""
    __name__ = 'journal.ebook.report.text'

    @classmethod
    def execute(cls, ids, data):
        """Override execute method to update the file extension."""
        result = super(JournalEbookReportText, cls).execute(ids, data)
        result = ('txt',) + result[1:]
        return result

class JournalEbookAccounting(Report):
    """Report Journal Book."""
    __name__ = 'journal.ebook.report.accounting'

    @classmethod
    def __setup__(cls):
        super(JournalEbookAccounting, cls).__setup__()

    @classmethod
    def get_context(cls, records, data):
        AccountPlan = Pool().get('account.account')
        records = AccountPlan.search([
            ('company', '=', data['company']),
            ('name', '=', 'Plan General Contable General Peruano 2016'),
            ('active', '=', True),
        ])
        context = super(JournalEbookAccounting, cls).get_context(
            records,
            data)
        context['lines'] = cls._prepare_accounting_plan(records, data)

        return context

    @classmethod
    def _prepare_accounting_plan(cls, records, data):
        """Return the list of accounts."""
        lines = list()
        period = data['period']
        for account in records:
            for child in account.childs:
                report_line = AccountPlan(account, child, period)
                if child.childs:
                    cls._prepare_accounting_plan([child], data)
                ple_row = report_line.get_ple_row()
                lines.append(ple_row)
        return lines

    @classmethod
    def execute(cls, ids, data):
        """Override execute method to update report name."""
        Company = Pool().get('company.company')
        Period = Pool().get('account.period')
        with Transaction().set_context():
            result = super(JournalEbookAccounting, cls).execute(ids, data)
        company = Company(data.get('company'))
        period = Period(data.get('fiscalyear'))
        if len(ids) > 1:
            result = result[:2] + (True,) + result[3:]
        else:
            if data:
                identifier = 'LE'  # Unique identifier for electronic books
                ruc = company.ruc  # Company RUC
                period = period.name  # Period
                year, month = period.split('-')  # Year and month
                day = '00'  # No day in journal book
                book_id = '050300'  # Journal Book identifier
                cc = '00'  # No applied
                OIM = '111'  # For Journal book
                G = '1'  # PLE generated
                name = identifier + ruc + year + month + day + book_id + cc + OIM + G

                oim = '111'
                result = result[:3] + (name,)
                result = ('txt',  result[1].strip(),) + result[2:]
        return result


def sanitatize(value):
    if type(value) not in (str, str) and value is not None:
        value = str(value)
        sanitatize(value)
    if value is None:
        value = ''
    value = value.strip()
    value = value.replace("\n", "")
    return value
