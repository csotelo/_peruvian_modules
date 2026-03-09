# -*- coding: utf-8 -*-
"""
    sale_pe.py

    :copyright: (c) 2018 by Grupo ConnectTix SAC
    :license: see LICENSE for more details.
"""
import os
from datetime import datetime
from decimal import Decimal

from trytond.config import config
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, If, Bool, Not, Less
from trytond.report import Report
from trytond.transaction import Transaction
from trytond.wizard import Button, StateReport, StateView, Wizard

__all__ = ['PLEReport',
           'Sale',
           'SaleLine',
           'SunatPLESales',
           'SunatPLEMainView',
           'PLEReportSales',
           'PLEReportSalesSpread',
           'SunatPLESalesView',
           'SunatPLESalesWizard',
           'PLEReportSalesPlain',
           'PLEReportLine'
           ]

_MODIFIED_DOCUMENT_TYPE_CREDIT = [
    ('', ''),
    ('01', 'ANULACIÓN DE LA OPERACIÓN'),
    ('02', 'ANULACIÓN POR ERROR EN EL RUC'),
    ('03', 'CORRECCIÓN POR ERROR EN LA DESCRIPCIÓN'),
    ('04', 'DESCUENTO GLOBAL'),
    ('05', 'DESCUENTO POR ITEM'),
    ('06', 'DEVOLUCIÓN TOTAL'),
    ('07', 'DEVOLUCIÓN POR ITEM'),
    ('08', 'BONIFICACIÓN'),
    ('09', 'DISMINUCIÓN EN EL VALOR'),
    ('10', 'OTROS CONCEPTOS'),
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

sunat_ebooks = config.get('account', 'sunat_ebooks')


class SunatPLESales(ModelView, ModelSQL):
    '''Define date range for the report.'''
    __name__ = 'account_pe.ple.sale.model'


class SunatPLEMainView(ModelView):
    '''Base view for the report creation wizards'''
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


class SunatPLESalesView(SunatPLEMainView):
    '''View for the sale report wizard'''
    __name__ = 'account_pe.ple.sale.start'


class SunatPLESalesWizard(Wizard):
    '''Libro de ventas SUNAT'''
    __name__ = 'account_pe.ple.sale'

    start = StateView(
        'account_pe.ple.sale.start',
        'sale_pe.create_ple_sale_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Texto', 'plain_', 'tryton-ok', default=True),
            Button('PLE', 'ple_', 'tryton-ok'),
            Button('Excel', 'spread_', 'tryton-ok'),
        ])

    plain_ = StateReport(
        'account_pe.reporting.sunat_sale_plain'
    )
    ple_ = StateReport(
        'account_pe.reporting.sunat_sale_ple'
    )
    spread_ = StateReport(
        'account_pe.reporting.sunat_sale_spread'
    )

    def do_plain_(self, action):
        return action, {
            'id': action['action'],
            'company': self.start.company.id,
            'fiscalyear': self.start.fiscalyear.id,
            'period': self.start.period.id
        }

    def do_ple_(self, action):
        return action,  {
            'id': action['action'],
            'company': self.start.company.id,
            'fiscalyear': self.start.fiscalyear.id,
            'period': self.start.period.id
        }

    def do_spread_(self, action):
        return action,  {
            'id': action['action'],
            'company': self.start.company.id,
            'fiscalyear': self.start.fiscalyear.id,
            'period': self.start.period.id
        }

class PLEReportLine(object):
    def __init__(self, invoice, serial_number=None):
        serial_number = serial_number if serial_number\
            else invoice.sunat_serial
        self.C01 = invoice.invoice_date.strftime('%Y%m00')
        self.C02 = MOVE_NULLED,
        self.C03 = MOVE_NULLED,
        self.C04 = invoice.invoice_date.strftime('%d/%m/%Y'),
        self.C05 = '',
        self.C06 = invoice.sunat_document_type,
        self.C071 = invoice.sunat_serial_prefix or '',
        self.C072 = invoice.sunat_serial,
        self.C08 = serial_number,
        self.C09 = '',
        self.C10 = '0',
        self.C11 = '99999999',
        self.C12 = 'ANULADO',
        self.C13 = 0,
        self.C14 = 0,
        self.C15 = 0,
        self.C16 = 0,
        self.C17 = 0,
        self.C18 = 0,
        self.C19 = 0,
        self.C20 = 0,
        self.C21 = 0,
        self.C22 = 0,
        self.C23 = 0,
        self.C24 = 0,
        self.C25 = 'PEN',
        self.C26 = '0.309',
        self.C27 = '',
        self.C28 = '',
        self.C29 = '',
        self.C30 = '',
        self.C31 = '',
        self.C32 = '',
        self.C33 = '',
        self.C34 = '1',
        self.LS0 = os.linesep


class PLEReport(Report):
    @classmethod
    def get_context(cls, records, data, **kwargs):
        context = super(PLEReport, cls).get_context(records, data)
        period_id = str(data['period'])
        Period = Pool().get('account.period')
        period = Period(period_id)
        year, month = period.name.split('-')
        records = cls._find_records(
            from_date=period.start_date,
            to_date=period.end_date,
            ActiveRecord=kwargs['ActiveRecord']
        )
        context['lines'] = cls._prepare_lines(records, data)
        context['month'] = _MONTHS[str(month)]
        context['year'] = year
        total_untaxed_amount = Decimal('0')
        total_tax_amount = Decimal('0')
        total_amount = Decimal('0')
        for line in context['lines']:
            line_untaxed_amount = Decimal(line.C14[0].strip('"'))
            line_tax_amount = Decimal(line.C16[0].strip('"'))
            line_total_amount = Decimal(line.C24[0].strip('"'))
            total_untaxed_amount += line_untaxed_amount
            total_tax_amount += line_tax_amount
            total_amount += line_total_amount
        context['total_untaxed_amount'] = "{0:.2f}".format(total_untaxed_amount)
        context['total_tax_amount'] = "{0:.2f}".format(total_tax_amount)
        context['total_amount'] = "{0:.2f}".format(total_amount)
        context['company'] = context['user'].company
        return context

    @classmethod
    def _find_records(cls, from_date=None, to_date=None, ActiveRecord=None):
        raise NotImplementedError(
            'PLEReport#_get_invoice_records should be overriden')


class PLEReportSales(PLEReport):
    __name__ = 'account_pe.reporting.sunat_sale_ple'

    name = 'SUNAT PLE Ventas'

    @classmethod
    def __setup__(cls):
        super(PLEReportSales, cls).__setup__()

    @classmethod
    def _find_records(cls, from_date=None, to_date=None, ActiveRecord=None):
        if not ActiveRecord or not from_date or not to_date:
            raise AttributeError(
                'Neither from_date, to_date nor ActiveRecord can be None')

        start_date = from_date
        end_date = to_date
        invoices = ActiveRecord.search([
            ('type', '=', 'out'),
            ('state', 'in', ('draft', 'posted', 'paid', 'anulado', 'voided')),
            ('number', '!=', None),
            ('move.date', '>=', start_date),
            ('move.date', '<=', end_date), ],
            order=[('sunat_document_type', 'ASC'),
                   ('sunat_serial', 'ASC'),
                   ('sunat_number', 'ASC')])

        return invoices

    @classmethod
    def _prepare_lines(cls, records, data):
        # last_serie = None
        # last_invoice_number = None
        lines = list()
        #end_date = data['end_date']
        #latest_series_dict = cls.get_last_series(end_date)

        # find non correlative serial numbers
        for invoice in records:
            line = None
            """current_serie = '{prefix}{serie}'.format(
                prefix=invoice.sunat_serial_prefix or '',
                serie=invoice.sunat_serial)"""
            # try:
            #     invoice_number = int(invoice.sunat_number)
            # except:
            #     continue
            """
            if last_serie != current_serie:
                last_invoice_number = int(
                    latest_series_dict.get(current_serie, 0))
            if last_invoice_number + 1 != invoice_number:
                lines = cls._prepare_empty_line(
                    invoice, current_serie, last_invoice_number + 1,
                    invoice_number)
            """
            line = cls._prepare_line(invoice)
            #last_invoice_number = invoice_number
            #last_serie = current_serie
            lines.append(line)

        return lines

    @classmethod
    def get_context(cls, records, data):
        InvoicesObject = Pool().get('account.invoice')
        context = super(PLEReportSales, cls).get_context(
            records,
            data,
            ActiveRecord=InvoicesObject
        )
        return context

    # Functions to fix correlative invoice numbers
    @classmethod
    def get_last_series(cls, until_date):
        """
        Return a dictionary which contains series and final invoice numbersof
        the last month

        :param until_date:
        :return: a dictionary with the series and the last invoice number of
        the month before current_date
        """
        period = datetime.strptime(str(until_date), "%Y-%m-%d").date()

        year = period.year
        month = period.month

        if year == 2018 and month == 1:
            return {}
        else:
            cursor = Transaction().connection.cursor()
            cursor.execute("""
                SELECT
                  distinct sunat_document_type,
                  sunat_serial_prefix,
                  sunat_serial,
                  max(sunat_number) as latest_sunat_number
                FROM
                  account_invoice
                WHERE
                  type='out' AND
                  state in ('draft', 'posted', 'paid', 'voided') AND
                  number <> '' AND
                  invoice_date < '{start_date}'
                GROUP BY
                  sunat_document_type,
                  sunat_serial_prefix,
                  sunat_serial
                ORDER BY
                  sunat_document_type ASC,
                  sunat_serial ASC,
                  latest_sunat_number ASC;
                """.format(start_date=until_date))
            latest_series_dict = {}
            for record in cursor:
                latest_series_dict['{prefix}{serie}'.format(
                    prefix=record[1], serie=record[2])] = record[3]
            return latest_series_dict

    @classmethod
    def _prepare_line(cls, invoice):
        '''The Journal contains informations abouts the account moves of the
           specific period. The descriptions are in spanish, gived by SUNAT
           :C01*: Periodo. Format: AAAAMM00. Related fields: C21. Length: 8
           :C02*: Código único de operación. Related fields: C21. Length: 1-40
           :C03*: Número correlativo del asiento contable del campo C02
                  Debe empezar por A, M o C. Related fields: C2. Length: 2-10
           :C04: Fecha de emisión del comprobante de pago. Format: DD/MM/AAAA
           :C05: Fecha de vencimiento. Format: DD/MM/AA. Related fields: C6, C34
           :C06*: Tipo de comprobante de pago. Length: 2
           :C07*: Número de serie de comprobante de pago. Length: 1-20
           :C08*: Número de comprobante de pago. Length: 1-20
           :C09: Para efectos de registros de tickets. Length: 1-20
           :C10: Tipo de documento de indentidad del cliente: Length: 1
           :C11: Número de documento de indentidad del cliente. Length: <15
           :C12: Apellidos, nombres o denominación del cliente. Length <100
           :C13: Valor facturado de exportación. Format: ####.##
           :C14: Base imponible de la operación gravada. Format: ####.##
           :C15: Descuento de la base imponible. Format: ####.##
           :C16: Impuesto general a las ventas, o municipal. Format ####.##
           :C17: Descuento al IGV o impuesto municipal. Format ####.##
           :C18: Importe total de la operación exonerada. Format ####.##
           :C19: Importe total de la operación inafecta. Format ####.##
           :C20: Impuesto selectivo al consumo. Format ####.##
           :C21: Base imponible de la operación gravada con impuesto a la venta
                 del arroz pilado. Format ####.##. Related fields: C06, C34
           :C22: Impuesto del arroz pilado. Format ####.##. Related fields: C06, C34
           :C23: Otros conceptos que no aparecen en la base imponible. Format ####.##
           :C24: Importe total del comprobante de pago. Format ####.##
           :C25: Código de la moneda. Usually: PEN
           :C26: Tipo de cambio. Format #.###. Related fields: C25
           :C27: Fecha de emisión del comprobante de pago o documento original que se modifica o
                 documento referencial al documento que sustenta el crédito fiscal. Length <20
           :C28: Tipo de comprobante de pago que se modifica. Length <20
           :C29: Número de serie del comprobante de pago que se modifica.
           :C30: Número del comprobante de pago que se modifica.
           :C31: Identificador de sociedades irregulares.
           :C32: Error tipo 1. Inconsistencia en el tipo de cambio
           :C33: Indicador de Comprobantes de pago cancelados con medios de pago.
           :C34*: Identificador de operación.
           :C35-68: Free

            *: Required
        '''
        InvoiceObject = Pool().get('account.invoice')
        CurrencyRates = Pool().get('currency.currency.rate')

        invoice_untaxed_amount = 0
        invoice_total_amount = 0
        invoice_tax_amount = 0
        invoice_move_number = '0'
        invoice_document_type = invoice.sunat_document_type or ''
        move_status = '1'

        modified_document_date = ''
        modified_document_type = ''
        modified_document_serie = ''
        modified_document_number = ''

        document_type = _DOCUMENT_TYPE[invoice.party.document_type or '']
        document_number = invoice.party.document_number or '0'
        exchange_rate = invoice.currency.rate

        # if document type is a credit note, name should appear as 'ANULADO'
        if invoice.state != 'draft':
            invoice_untaxed_amount = invoice.untaxed_amount
            invoice_tax_amount = invoice.tax_amount
            invoice_total_amount = invoice.total_amount
            invoice_move_number = invoice.move.number if invoice.move else ''
            invoice_datetime = datetime(
                invoice.invoice_date.year, invoice.invoice_date.month, invoice.invoice_date.day)
            invoice_rate = CurrencyRates.search(
                [('date', '<=', invoice_datetime),
                 ('currency', '=', invoice.currency),
                 ], order=[('date', 'DESC')], limit=1)
            if invoice_rate:
                exchange_rate = invoice_rate[0].rate

        if invoice.document_type in ['commercial_credit', 'simple_credit', 'simple_debit', 'commercial_debit']:
            if invoice.type == 'out':
                modified_invoice_list = InvoiceObject.search(
                    [('document_type', '=', invoice.document_type.split('_')[0]),
                     ('number', '=', invoice.modified_document),
                     ('type', '=', 'out')
                     ])
                if len(modified_invoice_list) == 1 and modified_invoice_list[0].invoice_date:
                    modified_invoice = modified_invoice_list[0]

                    modified_document_date =\
                        modified_invoice.invoice_date.strftime(
                            '%d/%m/%Y') if modified_invoice.invoice_date else ''
                    modified_document_type = modified_invoice.sunat_document_type if modified_invoice else ''
                    modified_document_serie = '{prefix}{serie}'.format(
                        prefix=modified_invoice.sunat_serial_prefix or '',
                        serie=modified_invoice.sunat_serial) if modified_invoice else ''
                    modified_document_number = modified_invoice.sunat_number if modified_invoice else ''
                    invoice_datetime = datetime(
                        modified_invoice.invoice_date.year, modified_invoice.invoice_date.month, modified_invoice.invoice_date.day)
                    invoice_rate = CurrencyRates.search(
                        [('date', '<=', invoice_datetime),
                         ('currency', '=', invoice.currency),
                         ], order=[('date', 'DESC')], limit=1)
                    if invoice_rate:
                        exchange_rate = invoice_rate[0].rate
                    if modified_invoice.invoice_type != 'mechanized':
                        if modified_invoice.document_type == 'simple':
                            modified_document_serie = '{prefix}{serie}'.format(
                                prefix='B',
                                serie=modified_invoice.sunat_serial) if modified_invoice else ''
                        if modified_invoice.document_type == 'commercial':
                            modified_document_serie = '{prefix}{serie}'.format(
                                prefix='F',
                                serie=modified_invoice.sunat_serial) if modified_invoice else ''
                    if modified_invoice.invoice_type == 'mechanized':
                        modified_document_serie = '{prefix}{serie}'.format(
                            prefix='0',
                            serie=modified_invoice.sunat_serial) if modified_invoice else ''

        if invoice.state in ['draft', 'anulado', 'voided']:
            name = invoice.party.name if invoice.state == 'voided' else "ANULADO"
            last_name = getattr(invoice.party, 'lastname', '') if invoice.state == 'voided' else ""
            invoice_total_amount = 0
            document_type = "0"
            document_number = "0"
            invoice_tax_amount = 0
            invoice_untaxed_amount = 0
            invoice_move_number =\
                invoice.move.number if invoice.move else MOVE_NULLED
            exchange_rate = 1.000
            move_status = "2"
        if invoice.state in ['voided']:
            name = invoice.party.name or ''
            last_name = getattr(invoice.party, 'lastname', '')
            invoice_total_amount = 0
            document_type = "0"
            document_number = "0"
            invoice_tax_amount = 0
            invoice_untaxed_amount = 0
            invoice_move_number =\
                invoice.move.number if invoice.move else MOVE_NULLED
            exchange_rate = 1.000
            move_status = "2"
        else:
            name = invoice.party.name or ''
            last_name = getattr(invoice.party, 'lastname', '')
        c07 = invoice.sunat_serial
        if invoice.invoice_type != 'mechanized':
            c07 = '%s%s' % (invoice.sunat_serial_prefix or '0',
                            invoice.sunat_serial or '')
        if invoice.invoice_type == 'mechanized':
            c07 = '%s%s' % ('0',
                            invoice.sunat_serial or '')
        #c07 = invoice.sunat_serial_prefix or ''
        #c07 += invoice.sunat_serial
        # TODO: asiento contable por defecto en M -> movimiento
        c03 = str(invoice.move.post_number).replace(
            '-', '') if invoice.move else MOVE_NULLED

        party_identity = (last_name + '' + name)[:100]
        issue_date = invoice.invoice_date.strftime('%d/%m/%Y')
        expiration_date = invoice.invoice_duedate.strftime(
            '%d/%m/%Y') if invoice.invoice_duedate else ''

        report_line = PLEReportLine(invoice)
        report_line.C01 = invoice.invoice_date.strftime('%Y%m00'),
        report_line.C02 = invoice_move_number or MOVE_NULLED,
        report_line.C03 = "M" + c03[-9:],
        report_line.C04 = issue_date,
        report_line.C05 = expiration_date,  # mandatory when C06 is 14 and C34 is 2
        report_line.C06 = invoice_document_type,
        report_line.C07 = c07,
        report_line.C08 = invoice.sunat_number or '',
        report_line.C09 = '',  # Only if C06 is 0, 03, 12, 13, 87
        report_line.C10 = document_type,
        report_line.C11 = document_number,
        report_line.C12 = party_identity,
        report_line.C13 = '0.00',
        report_line.C14 = "{0:.2f}".format(round(invoice_untaxed_amount *
                                                 (1/exchange_rate), 2)),
        report_line.C15 = '0.00',
        report_line.C16 = "{0:.2f}".format(round(
            (invoice_tax_amount) * (1/exchange_rate), 2)),
        report_line.C17 = '0.00',
        report_line.C18 = '0.00',
        report_line.C19 = '0.00',
        report_line.C20 = '0.00',
        report_line.C21 = '0.00',
        report_line.C22 = '0.00',
        report_line.C23 = '0.00',
        report_line.C24 = "{0:.2f}".format(round(invoice_total_amount *
                                                 (1/exchange_rate), 2)),
        report_line.C25 = 'PEN',  # currency code
        # currency conversion #.###
        report_line.C26 = "{0:.3f}".format(1/exchange_rate),
        report_line.C27 = str(
            modified_document_date) if modified_document_date else '',
        report_line.C28 = str(
            modified_document_type) if modified_document_type else '',
        report_line.C29 = str(
            modified_document_serie) if modified_document_serie else '',
        report_line.C30 = str(
            modified_document_number) if modified_document_number else '',
        report_line.C31 = '',
        report_line.C32 = '',  # currency conversion inconsistency ->
        report_line.C33 = '',  # payment_method -> 1 if listed in table1
        report_line.C34 = move_status,  # invoice_status
        report_line.LS0 = os.linesep

        report_line_data = [a for a in dir(
            report_line) if a.startswith('C')]
        for l in report_line_data:
            clean_line = sanitatize(getattr(report_line, l)[0])
            setattr(report_line, l, (clean_line,))

        return report_line

    @classmethod
    def execute(cls, ids, data):
        '''Override execute method to update report name and remove LF'''
        Company = Pool().get('company.company')
        Period = Pool().get('account.period')
        with Transaction().set_context():
            result = super(PLEReportSales, cls).execute(ids, data)
        company = Company(data.get('company'))
        period = Period(data.get('period'))
        if len(ids) > 1:
            result = result[:2] + (True,) + result[3:]
        else:
            if data:
                report_content = (result[1].strip())

                oim = '111'
                result = result[:3] + (('' + 'LE' + company.ruc +
                                        period.name.replace('-', '') + '0014010000' + oim + '1'),)
                result = ('txt',  report_content,) + result[2:]

        return result


class PLEReportSalesPlain(PLEReportSales):
    __name__ = 'account_pe.reporting.sunat_sale_plain'

class PLEReportSalesSpread(PLEReportSales):
    __name__ = 'account_pe.reporting.sunat_sale_spread'

    @classmethod
    def execute(cls, ids, data):
        '''Override execute method to update the file extension'''
        with Transaction().set_context():
            result = super(PLEReportSales, cls).execute(ids, data)
        if len(ids) > 1:
            result = result[:2] + (True,) + result[3:]
        else:
            if data:
                result = ('ods',) + result[1:]
        return result


class Sale(metaclass=PoolMeta):
    __name__ = 'sale.sale'

    modified_document_reason = fields.Selection(
        _MODIFIED_DOCUMENT_TYPE_CREDIT,
        'Motivo de la nota de crédito',
        select=True,
        states={
            'invisible': (
                Not(Bool(Eval('origin'))) |
                (Eval('invoice_method') == 'manual')
            ),
            'required': (
                Bool(Eval('origin')) &
                (Eval('invoice_method') != 'manual') &
                Less(Eval('total_amount', 0), 0)
            ),
            'readonly': Eval('state').in_(['done', 'cancel', 'processing'])
        },
    )

    def _get_invoice_sale(self):
        Invoice = Pool().get('account.invoice')
        ZeroDivisionError
        invoice = Invoice(
            company=self.company,
            type='out',
            party=self.party,
            invoice_address=self.invoice_address,
            currency=self.currency,
            account=self.party.account_receivable,
            reference=self.reference,
        )

        invoice.document_type = 'commercial'

        # Cuando el atributo document_type del party no sea un RUC,
        # Se considerará como boleta sin importar que otro tipo sea
        if invoice.party.document_type != 'pe_vat':
            invoice.document_type = 'simple'

        lines_negative = 0
        for line in self.lines:
            if line.amount < 0:
                lines_negative += 1

        if len(self.lines) == lines_negative:
            if invoice.document_type == 'commercial':
                invoice.document_type = 'commercial_credit'
            if invoice.document_type == 'simple':
                invoice.document_type = 'simple_credit'
            if self.modified_document_reason:
                invoice.modified_document_reason = self.modified_document_reason
        invoice.on_change_type()
        invoice.payment_term = self.payment_term
        return invoice


class SaleLine(metaclass=PoolMeta):
    'Sale Line'

    __name__ = 'sale.line'

    def on_change_product(self):
        super(SaleLine, self).on_change_product()
        self.description = ''
        if self.product:
            if self.product:
                description = self.sanitatize(self.product.name)
            self.description = description

    def sanitatize(self, desc):
        """Remove leading, trailing spaces and new line

        Arguments:
            desc {str, unicode} -- The string to sanitatize

        Returns:
            str, unicode -- A clean string
        """
        if type(desc) in [str, str]:
            desc = desc.strip()
            desc = desc.replace('\n', '')
            desc = " ".join(desc.split())
            return desc

def sanitatize(value):
    if value is not None:
        value = value.strip()
        value = value.replace("\n", "")
    if value == 'None' or None:
        value = ''
    return value
