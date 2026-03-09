# -*- coding: utf-8 -*-
""".. module:: account.py.

    :plataform: Independent
    :synopsis: Accountant module for tryton
.. moduleauthor: Carlos Eduardo Sotelo Pinto <carlos.sotelo@connecttix.pe>
.. copyright: (c) 2017 - 2018
.. organization: Tryton - PE
.. license: GPL v3.
"""
import os
import copy
from datetime import datetime


from trytond.report import Report
from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import Pool
from trytond.config import config
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateView, Button, StateReport
from trytond.pyson import If, Eval

__all__ = ['PLEReport']
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


class SunatPLEJournal(ModelView, ModelSQL):
    """Define date range for the report."""
    __name__ = 'account_pe.ple.journal.model'


class SunatPLEMajor(ModelView, ModelSQL):
    """Define date range for the report."""
    __name__ = 'account_pe.ple.major.model'


class SunatPLEMainView(ModelView):
    """Base view for the report creation wizards."""
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

    posted = fields.Boolean('Posted Move', help='Show only posted move')

    @staticmethod
    def default_posted():
        return False

    @staticmethod
    def default_company():
        return Transaction().context.get('company')


class SunatPLEJournalView(SunatPLEMainView):
    """View for the journal report wizard."""
    __name__ = 'account_pe.ple.journal.start'

    posted = fields.Boolean('Posted Move', help='Show only posted move')

    @staticmethod
    def default_posted():
        return False


class SunatPLEMajorView(SunatPLEMainView):
    """View for the journal report wizard."""
    __name__ = 'account_pe.ple.major.start'


class SunatPLEJournalWizard(Wizard):
    """Libro diario SUNAT."""
    __name__ = 'account_pe.ple.journal'

    start = StateView(
        'account_pe.ple.journal.start',
        'account_pe.create_ple_journal_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('PLE', 'ple_',
                   'tryton-ok', default=True),
            Button('Excel', 'spread_',
                   'tryton-ok'),
            Button('Texto Plano', 'plain_',
                   'tryton-ok')
        ])

    ple_ = StateReport(
        'account_pe.reporting.sunat_journal_ple'
    )
    plain_ = StateReport(
        'account_pe.reporting.sunat_journal_plain'
    )
    spread_ = StateReport(
        'account_pe.reporting.sunat_journal_spread'
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


class SunatPLEMajorWizard(Wizard):
    """Libro mayor SUNAT."""
    __name__ = 'account_pe.ple.major'

    start = StateView(
        'account_pe.ple.major.start',
        'account_pe.create_ple_major_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('PLE', 'plain_',
                   'tryton-ok', default=True),
            Button('Excel', 'spread_',
                   'tryton-ok')
        ])

    plain_ = StateReport(
        'account_pe.reporting.sunat_major_ple'
    )
    spread_ = StateReport(
        'account_pe.reporting.sunat_major_spread'
    )

    def do_plain_(self, action):
        return action, {
            'id': action['action'],
            'company': self.start.company.id,
            'fiscalyear': self.start.fiscalyear.id,
        }

    def do_spread_(self, action):
        return action, {
            'id': action['action'],
            'company': self.start.company.id,
            'fiscalyear': self.start.fiscalyear.id,
        }


class PLEReportLine(object):
    def __init__(self, invoice, serial_number=None):
        self.C01 = ''
        self.C02 = MOVE_NULLED,
        self.C03 = MOVE_NULLED,
        self.C04 = '',
        self.C05 = '',
        self.C06 = 0,
        self.C071 = 0,
        self.C072 = 0,
        self.C08 = 0,
        self.C09 = '',
        self.C10 = '',
        self.C11 = '',
        self.C12 = '',
        self.C13 = 0,
        self.C14 = 0,
        self.C15 = 0,
        self.C16 = 0,
        self.C17 = 0,
        self.C18 = 0,
        self.C19 = 0,
        self.C20 = 0,
        self.C21 = 0,
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
        context['months'] = _MONTHS[str(month)]

        context['lines'] = cls._prepare_lines(records, data)
        return context

    @classmethod
    def _find_records(cls, from_date=None, to_date=None, ActiveRecord=None):
        raise NotImplementedError(
            'PLEReport#_get_invoice_records should be overriden')


class PLEReportMajorTemplate(Report):
    @classmethod
    def get_context(cls, records, data, **kwargs):
        context = super(PLEReportMajorTemplate, cls).get_context(records, data)
        fiscalyear_id = str(data['fiscalyear'])
        FiscalYear = Pool().get('account.fiscalyear')
        fiscalyear = FiscalYear(fiscalyear_id)
        records = cls._find_records(
            from_date=fiscalyear.start_date,
            to_date=fiscalyear.end_date,
            ActiveRecord=kwargs['ActiveRecord']
        )
        context['lines'] = cls._prepare_lines(records, data)
        return context

    @classmethod
    def _find_records(cls, from_date=None, to_date=None, ActiveRecord=None):
        raise NotImplementedError(
            'PLEReport#_get_invoice_records should be overriden')


class PLEReportJournal(PLEReport):
    __name__ = 'account_pe.reporting.sunat_journal_ple'
    name = 'SUNAT PLE Journal'

    @classmethod
    def __setup__(cls):
        super(PLEReportJournal, cls).__setup__()

    @classmethod
    def _find_records(cls, from_date=None, to_date=None, ActiveRecord=None):
        if not ActiveRecord or not from_date or not to_date:
            raise AttributeError(
                'Neither from_date, to_date nor ActiveRecord can be None')

        start_date = from_date
        end_date = to_date
        accounts = ActiveRecord.search([
            ('date', '>=', start_date),
            ('date', '<=', end_date),
            ('state', '=', 'posted'),
        ],
            order=[('number', 'ASC')])

        return accounts

    @classmethod
    def _prepare_lines(cls, records, data):
        # last_serie = None
        # last_invoice_number = None
        lines = list()
        # end_date = data['end_date']
        # latest_series_dict = cls.get_last_series(end_date)

        # find non correlative serial numbers
        for invoice in records:
            line_list = None
            line_list = cls._prepare_line(invoice)
            for l in line_list:
                lines.append(l)
        return lines

    @classmethod
    def get_context(cls, records, data):
        InvoicesObject = Pool().get('account.invoice')
        AccountObject = Pool().get('account.move')
        context = super(PLEReportJournal, cls).get_context(
            records,
            data,
            ActiveRecord=AccountObject
        )
        return context

    # Functions to fix correlative invoice numbers
    @classmethod
    def get_last_series(cls, until_date):
        """Return a dictionary which contains series and final invoice
        numbersof the last month.

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
                  type='in' AND
                  state in ('draft', 'posted', 'paid') AND
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
    def _prepare_empty_line(cls, invoice, serie, start, end):
        lines = list()
        for serial_number in range(start, end):
            c07 = invoice.sunat_serial_prefix or ''
            c07 += invoice.sunat_serial
            report_line = PLEReportLine(invoice, serial_number=serial_number)
            report_line.C01 = invoice.invoice_date.strftime('%Y%m00')
            report_line.C02 = MOVE_NULLED,
            report_line.C03 = MOVE_NULLED,
            report_line.C04 = invoice.invoice_date.strftime('%d/%m/%Y'),
            report_line.C05 = '',
            report_line.C06 = '',
            report_line.C07 = '',
            report_line.C08 = '',
            report_line.C09 = '',
            report_line.C10 = '0',
            report_line.C11 = '99999999',
            report_line.C12 = 'ANULADO',
            report_line.C13 = 0,
            report_line.C14 = 0,
            report_line.C15 = 0,
            report_line.C16 = 0,
            report_line.C17 = 0,
            report_line.C18 = 0,
            report_line.C19 = 0,
            report_line.C20 = 0,
            report_line.C21 = 0,
            report_line.LS0 = os.linesep
            lines.append(report_line)

        return lines

    @classmethod
    def _prepare_line(cls, invoice):

        report_line = PLEReportLine(invoice)
        lines = list()
        period = invoice.period.name.replace('-', '') + '00'
        correlative = invoice.number or MOVE_NULLED if invoice else ''
        entry_corr = invoice.post_number.replace(
            "-", "") if invoice.post_number else MOVE_NULLED
        document_type = _DOCUMENT_TYPE[invoice.origin.party.document_type] if invoice.origin and invoice.origin.__name__ == 'account.invoice' else ''
        document_number = invoice.origin.party.document_number if invoice.origin and invoice.origin.__name__ == 'account.invoice' else ''
        invoice_document_type = invoice.origin.sunat_document_type if invoice.origin and invoice.origin.__name__ == 'account.invoice' else '0'
        currency = invoice.origin.currency.code if invoice.origin and invoice.origin.__name__ == 'account.invoice' else ''
        sunat_serial = invoice.origin.sunat_serial if invoice.origin and invoice.origin.__name__ == 'account.invoice' else ''
        sunat_number = invoice.origin.sunat_number if invoice.origin and invoice.origin.__name__ == 'account.invoice' and invoice.origin.sunat_number != None else ''

        report_line_list = list()
        r_line = dict()

        for line in invoice.lines:
            r_line['C01'] = period,  # Period
            r_line['C02'] = correlative,  # Correlative
            r_line['C03'] = 'M' + entry_corr[-9:],  # Entry correlative
            # codigo de la cuenta contable
            r_line['C04'] = line.account.code if line.account else "",
            # codigo de la unidad de operacion de la unidad economica administrativa
            r_line['C05'] = '',
            r_line['C06'] = '',  # Codigo del centro de costos
            r_line['C07'] = currency,  # Tipo de moneda de origen
            # Tipo de document de identidad del emisor
            r_line['C08'] = document_type,
            # numero de documento de identidad del emisor
            r_line['C09'] = document_number.strip() or '',
            # Tipo de comprobante de pago
            r_line['C10'] = invoice_document_type,
            # Numero de serie del comprobante del pago
            r_line['C11'] = sunat_serial,
            # Numerro del comprobante de pago
            r_line['C12'] = sunat_number[-20:],
            r_line['C13'] = invoice.date.strftime(
                '%d/%m/%Y'),  # Fecha contable
            r_line['C14'] = '',  # Fecha de vencimiento
            r_line['C15'] = invoice.origin.invoice_date.strftime(
                '%d/%m/%Y') if invoice.origin and invoice.origin.__name__ == 'account.invoice' else '',  # Fecha de la operación o de la emisión
            # Glosa o descripción de la operacion
            r_line['C16'] = line.description.strip(
            ) if line.description else '',
            r_line['C17'] = '',  # Glosa referencial de ser el caso
            r_line['C18'] = '{0:.2f}'.format(line.debit),  # Movimientos del debe
            r_line['C19'] = '{0:.2f}'.format(line.credit),  # Movimientos del haber
            # Dato estructurado (solo si no es consolidado)
            r_line['C20'] = '',
            r_line['C21'] = '1',  # Estado de la opearación
            r_line['LS0'] = os.linesep
            lines.append(r_line)
            report_line.C01 = r_line['C01']
            report_line.C02 = r_line['C02']
            report_line.C03 = r_line['C03']
            report_line.C04 = r_line['C04']
            report_line.C05 = r_line['C05']
            report_line.C06 = r_line['C06']
            report_line.C07 = r_line['C07']
            report_line.C08 = r_line['C08']
            report_line.C09 = r_line['C09']
            report_line.C10 = r_line['C10']
            report_line.C11 = r_line['C11']
            report_line.C12 = r_line['C12']
            report_line.C13 = r_line['C13']
            report_line.C14 = r_line['C14']
            report_line.C15 = r_line['C15']
            report_line.C16 = r_line['C16']
            report_line.C17 = r_line['C17']
            report_line.C18 = r_line['C18']
            report_line.C19 = r_line['C19']
            report_line.C20 = r_line['C20']
            report_line.C21 = r_line['C21']
            report_line_data = [a for a in dir(
                report_line) if a.startswith('C')]

            for l in report_line_data:
                clean_line = sanitatize(getattr(report_line, l)[0])
                setattr(report_line, l, (clean_line,))
            report_line_list.append(copy.copy(report_line))
        return report_line_list

    @classmethod
    def execute(cls, ids, data):
        """Override execute method to update report name."""
        Company = Pool().get('company.company')
        Period = Pool().get('account.period')
        with Transaction().set_context():
            result = super(PLEReportJournal, cls).execute(ids, data)
        company = Company(data.get('company'))
        period = Period(data.get('period'))
        if len(ids) > 1:
            result = result[:2] + (True,) + result[3:]
        else:
            if data:
                oim = '111'
                result = result[:3] + ('' + 'LE' + company.ruc +
                                       period.name.replace('-', '') + '0005010000' + oim + '1',)
                result = ('txt',  result[1].strip(),) + result[2:]
        return result

class PLEReportJournalSpread(PLEReportJournal):
    __name__ = 'account_pe.reporting.sunat_journal_spread'

    @classmethod
    def execute(cls, ids, data):
        """Override execute method to update the file extension."""
        with Transaction().set_context():
            result = super(PLEReportJournal, cls).execute(ids, data)
        if len(ids) > 1:
            result = result[:2] + (True,) + result[3:]
        else:
            if data:
                result = ('ods',) + result[1:]
        return result


class PLEReportJournalPlain(PLEReportJournal):
    __name__ = 'account_pe.reporting.sunat_journal_plain'


class PLEReportMajor(PLEReportMajorTemplate):
    __name__ = 'account_pe.reporting.sunat_major_ple'

    @classmethod
    def _find_records(cls, from_date=None, to_date=None, ActiveRecord=None):
        if not ActiveRecord or not from_date or not to_date:
            raise AttributeError(
                'Neither from_date, to_date nor ActiveRecord can be None')

        start_date = from_date
        end_date = to_date
        accounts = ActiveRecord.search([
            ('date', '>=', start_date),
            ('date', '<=', end_date),
            ('state', '=', 'posted'),
        ],
            order=[('date', 'ASC')])

        return accounts

    @classmethod
    def _prepare_lines(cls, records, data):
        # last_serie = None
        # last_invoice_number = None
        lines = list()
        # end_date = data['end_date']
        # latest_series_dict = cls.get_last_series(end_date)

        # find non correlative serial numbers
        for invoice in records:
            line_list = None
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

            line_list = cls._prepare_line(invoice)
            for l in line_list:
                lines.append(l)
        return lines

    @classmethod
    def get_context(cls, records, data):
        AccountObject = Pool().get('account.move')
        context = super(PLEReportMajor, cls).get_context(
            records,
            data,
            ActiveRecord=AccountObject
        )
        return context

    # Functions to fix correlative invoice numbers
    @classmethod
    def get_last_series(cls, until_date):
        """Return a dictionary which contains series and final invoice
        numbersof the last month.

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
                  type='in' AND
                  state in ('draft', 'posted', 'paid') AND
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
    def _prepare_empty_line(cls, invoice, serie, start, end):
        lines = list()
        for serial_number in range(start, end):
            c07 = invoice.sunat_serial_prefix or ''
            c07 += invoice.sunat_serial
            report_line = PLEReportLine(invoice, serial_number=serial_number)
            report_line.C01 = invoice.invoice_date.strftime('%Y%m00')
            report_line.C02 = MOVE_NULLED,
            report_line.C03 = MOVE_NULLED,
            report_line.C04 = invoice.invoice_date.strftime('%d/%m/%Y'),
            report_line.C05 = '',
            report_line.C06 = invoice.sunat_document_type,
            report_line.C07 = c07,
            report_line.C08 = serial_number,
            report_line.C09 = '',
            report_line.C10 = '0',
            report_line.C11 = '99999999',
            report_line.C12 = 'ANULADO',
            report_line.C13 = 0,
            report_line.C14 = 0,
            report_line.C15 = 0,
            report_line.C16 = 0,
            report_line.C17 = 0,
            report_line.C18 = 0,
            report_line.C19 = 0,
            report_line.C20 = 0,
            report_line.C21 = 0,
            report_line.LS0 = os.linesep
            lines.append(report_line)

        return lines

    @classmethod
    def _prepare_line(cls, invoice):
        report_line = PLEReportLine(invoice)

        lines = list()
        period = invoice.period.name.replace('-', '') + '00'
        correlative = invoice.number or MOVE_NULLED if invoice else ''
        entry_corr = invoice.post_number.replace(
            "-", "") if invoice.post_number else MOVE_NULLED
        document_type = _DOCUMENT_TYPE[invoice.origin.party.document_type] if invoice.origin and invoice.origin.__name__ == 'account.invoice' else ''
        document_number = invoice.origin.party.document_number if invoice.origin and invoice.origin.__name__ == 'account.invoice' else ''
        invoice_document_type = invoice.origin.sunat_document_type if invoice.origin and invoice.origin.__name__ == 'account.invoice' else '0'
        currency = invoice.origin.currency.code if invoice.origin and invoice.origin.__name__ == 'account.invoice' else ''
        sunat_serial = invoice.origin.sunat_serial if invoice.origin and invoice.origin.__name__ == 'account.invoice' else ''
        sunat_number = invoice.origin.sunat_number if invoice.origin and invoice.origin.__name__ == 'account.invoice' and invoice.origin.sunat_number != None else ''

        report_line_list = list()
        r_line = dict()

        for line in invoice.lines:
            r_line['C01'] = period,  # Period
            r_line['C02'] = correlative,  # Correlative
            r_line['C03'] = 'M' + entry_corr[-9:],  # Entry correlative
            # codigo de la cuenta contable
            r_line['C04'] = line.account.code if line.account else "",
            # codigo de la unidad de operacion de la unidad economica administrativa
            r_line['C05'] = '',
            r_line['C06'] = '',  # Codigo del centro de costos
            r_line['C07'] = currency,  # Tipo de moneda de origen
            # Tipo de document de identidad del emisor
            r_line['C08'] = document_type,
            # numero de documento de identidad del emisor
            r_line['C09'] = document_number.strip() or '',
            # Tipo de comprobante de pago
            r_line['C10'] = invoice_document_type,
            # Numero de serie del comprobante del pago
            r_line['C11'] = sunat_serial,
            # Numerro del comprobante de pago
            r_line['C12'] = sunat_number[-20:],
            r_line['C13'] = invoice.date.strftime(
                '%d/%m/%Y'),  # Fecha contable
            r_line['C14'] = '',  # Fecha de vencimiento
            r_line['C15'] = invoice.origin.invoice_date.strftime(
                '%d/%m/%Y') if invoice.origin and invoice.origin.__name__ == 'account.invoice' else '',  # Fecha de la operación o de la emisión
            # Glosa o descripción de la operacion
            r_line['C16'] = line.description.strip(
            ) if line.description else '',
            r_line['C17'] = '',  # Glosa referencial de ser el caso
            r_line['C18'] = '{0:.2f}'.format(line.debit),  # Movimientos del debe
            r_line['C19'] = '{0:.2f}'.format(line.credit),  # Movimientos del haber
            # Dato estructurado (solo si no es consolidado)
            r_line['C20'] = '',
            r_line['C21'] = '1',  # Estado de la opearación
            r_line['LS0'] = os.linesep
            lines.append(r_line)
            report_line.C01 = r_line['C01']
            report_line.C02 = r_line['C02']
            report_line.C03 = r_line['C03']
            report_line.C04 = r_line['C04']
            report_line.C05 = r_line['C05']
            report_line.C06 = r_line['C06']
            report_line.C07 = r_line['C07']
            report_line.C08 = r_line['C08']
            report_line.C09 = r_line['C09']
            report_line.C10 = r_line['C10']
            report_line.C11 = r_line['C11']
            report_line.C12 = r_line['C12']
            report_line.C13 = r_line['C13']
            report_line.C14 = r_line['C14']
            report_line.C15 = r_line['C15']
            report_line.C16 = r_line['C16']
            report_line.C17 = r_line['C17']
            report_line.C18 = r_line['C18']
            report_line.C19 = r_line['C19']
            report_line.C20 = r_line['C20']
            report_line.C21 = r_line['C21']
            report_line_data = [a for a in dir(
                report_line) if a.startswith('C')]

            for l in report_line_data:
                clean_line = sanitatize(getattr(report_line, l)[0])
                setattr(report_line, l, (clean_line,))
            report_line_list.append(copy.copy(report_line))
        return report_line_list

    @classmethod
    def execute(cls, ids, data):
        """Override execute method to update report name."""
        Company = Pool().get('company.company')
        Period = Pool().get('account.period')
        with Transaction().set_context():
            result = super(PLEReportMajor, cls).execute(ids, data)
        company = Company(data.get('company'))
        period = Period(data.get('fiscalyear'))
        if len(ids) > 1:
            result = result[:2] + (True,) + result[3:]
        else:
            if data:
                oim = '111'
                result = result[:3] + ('' + 'LE' + company.ruc +
                                       str(period.name.replace('-', '')) + '0006010000' + oim + '1',)
                result = ('txt',  result[1].strip(),) + result[2:]
        return result

class PLEReportMajorSpread(PLEReportMajor):
    __name__ = 'account_pe.reporting.sunat_major_spread'

    @classmethod
    def execute(cls, ids, data):
        """Override execute method to update the file extension."""
        with Transaction().set_context():
            result = super(PLEReportMajor, cls).execute(ids, data)
        if len(ids) > 1:
            result = result[:2] + (True,) + result[3:]
        else:
            if data:
                result = ('ods',) + result[1:]
        return result


def sanitatize(value):
    if type(value) in (str, str) and value is not None:
        value = value.strip()
        value = value.replace("\n", "")
    if value is None:
        value = ''
    return value
