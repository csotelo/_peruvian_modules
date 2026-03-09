# -*- coding: utf-8 -*-
# This file is part of the account_invoice_pe module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

import base64
import functools
import io
import itertools
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from smtplib import SMTP

import smtplib
import email.utils
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urlparse

import treepoem
from dateutil.relativedelta import relativedelta
from genshi.template import MarkupTemplate
from trytond.config import config
from trytond.model import ModelSQL, ModelView, Unique, Workflow, fields
from trytond.modules.account_invoice_pe.sunat.documents import (
    DocumentFactory, DocumentSigner)
from trytond.modules.account_invoice_pe.sunat.ebilling import (SoapClient,
                                                               UsernameToken)
from trytond.modules.account_invoice_pe.utils.number_to_letter import to_word
from trytond.modules.product import price_digits
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Bool, Equal, Eval, If, Not
from trytond.report import Report
from trytond.tools import grouped_slice
from trytond.transaction import Transaction
from trytond.wizard import (Button, StateAction, StateReport, StateTransition,
                            StateView, Wizard)

from .invoice_email import default_email_template_string

logger = logging.getLogger(__name__)

sunat_invoicing_path = config.get('account_invoice', 'sunat_invoicing')
if not sunat_invoicing_path or len(sunat_invoicing_path) == 0:
    sunat_invoicing_path = '.'

sunat_ebilling_endpoint = config.get('account_invoice',
                                     'sunat_ebilling_endpoint')

discount_digits = (16, config.getint('product', 'discount_decimal', default=4))

__all__ = ['FiscalYear', 'InvoiceSequence',
           'Invoice', 'InvoiceLine', 'InvoiceTax', 'Move']

_STATES = {
    'readonly': Eval('state') != 'draft',
}

_DEPENDS = ['state']

_ZERO = Decimal('0.0')

_CURRENCY = [('USD', 'Dólares estaunidenses'), ('PEN', 'Soles'),
             ('EUR', 'Euros'), ('', 'Otros')]

_TYPE_INVOICE = [
    ('out_invoice', "Comprobante de pago de cliente"),
    ('in_invoice', "Comprobante de pago de proveedor"),
    ('out_credit_note', "Nota de crédito de cliente"),
    ('in_credit_note', "Nota de crédito de proveedor"),
    ('out_debit_note', "Nota de débito de cliente"),
    ('in_debit_note', "Nota de débito de proveedor"),
]

_GENERATED_STATUS = [('', ''), ('generatederror', 'Generada con errores'),
                     ('generatedok', 'Generada correctamente'),
                     ('signederror', 'Firmada con errores'),
                     ('signedok', 'Firmada correctamente'),
                     ('senterror', 'No pudo ser enviada a SUNAT '),
                     ('sentok', 'Enviada a SUNAT correctamente')]

_CODE_STATUS = [
    ('', ''),
    ('0', 'Procesó correctamente'),
    ('98', 'En proceso'),
    ('99', 'Proceso con errores')
]

_DOCUMENT_TYPE = [
    ('', ''),
    ('commercial', 'FACTURA'),
    ('simple', 'BOLETA DE VENTA'),
    ('commercial_credit', 'NOTA DE CRÉDITO DE FACTURA'),
    ('simple_credit', 'NOTA DE CRÉDITO DE BOLETA DE VENTA'),
    ('commercial_debit', 'NOTA DE DÉBITO DE FACTURA'),
    ('simple_debit', 'NOTA DE DÉBITO DE BOLETA DE VENTA'),
    ('other', 'OTROS')
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

_MODIFIED_DOCUMENT_TYPE_DEBIT = [
    ('', ''),
    ('01', 'INTERESES POR MORA'),
    ('02', 'AUMENTO EN EL VALOR'),
    ('03', 'PENALIDADES / OTROS CONCEPTOS')]

_SUNAT_DOCUMENT_TYPE = [
    ('', ''),
    ('00', "00 - Otros"),
    ('01', "01 - Factura"),
    ('02', "02 - Recibo por honorarios"),
    ('03', "03 - Boleta de venta"),
    ('04', "04 - Liquidación de compra"),
    ('05', "05 - Boletos de Transporte Aéreo."),
    ('06', "06 - Carta de porte aéreo por el serv. de transporte de carga aérea."),
    ('07', "07 - Nota de crédito"),
    ('08', "08 - Nota de débito"),
    ('09', "09 - Guías de remisión - Remitente"),
    ('10', "10 - Recibo por arrendamiento"),
    ('11', "11 - Póliza emitida por las Bolsas de Valores, Productos."),
    ('12', "12 - Ticket "),
    ('13', "13 - Documentos emitidos por entidades financieras y seguros"),
    ('14', "14 - Recibo por servicios públicos "),
    ('15', "15 - Boletos emitidos por el servicio de transporte terrestre"),
    ('16', "16 - Boletos de viaje emitidos por las empresas de transporte nacional."),
    ('17', "17 - Emitido por la Ig Cat por el arrendamiento de bienes inmuebles."),
    ('18', "18 - Documentos emitidos por las AFP "),
    ('19', "19 - Boleto o entrada por atracciones y espectáculos públicos."),
    ('20', "20 - Comprobante de Retención."),
    ('21', "21 - Servicio de transporte de carga marítima."),
    ('22', "22 - Comprobante por Operaciones No Habituales."),
    ('23', "23 - Subastas"),
    ('24', "24 - Certificado de pago de regalías emitidas por PERUPETRO S.A."),
    ('25', "25 - Impuesto General a las Ventas"),
    ('26', "26 - Emitido por la Asamblea General de la Comisión de Regantes."),
    ('27', "27 - Seguro Complementario de Trabajo de Riesgo."),
    ('28', "28 - Etiquetas autoadhesivas cobradas por CORPAC S.A."),
    ('29', "29 - Documentos emitidos por la COFOPRI."),
    ('30', "30 - Emitidos por instituciones financieras, crédito y débito"),
    ('31', "31 - Guía de Remisión – Transportista."),
    ('32', "32 - Ley de Promoción del Desarrollo de la Industria del Gas Natural."),
    ('33', "33 - Manifiesto de Pasajeros."),
    ('34', "34 - Documento del Operador. "),
    ('35', "35 - Documento del Partícipe."),
    ('36', "36 - Recibo de Distribución de Gas Natural."),
    ('37', "37 - Revision Tecnica Vehicular"),
    ('40', "40 - Comprobante de Percepción."),
    ('41', "41 - Comprobante de Percepción - Venta Interna."),
    ('42', "42 - Documentos tarjeta de credito,debito emitidas por ella mismas."),
    ('43', "43 - Boletos Aéreo privados o especiales."),
    ('44', "44 - Billetes de lotería, rifas y apuestas."),
    ('45', "45 - Documentos por tributos no gravados por instituciones educativos"),
    ('46', "46 - Formulario de Declaración"),
    ('49', "49 - Constancia de Depósito - IVAP (Ley 28211)."),
    ('50', "50 - DUA/DAM."),
    ('51', "51 - Póliza o DUI Fraccionada."),
    ('52', "52 - Despacho Simplificado - Importación Simplificada."),
    ('53', "53 - Declaración de Mensajería o Courier."),
    ('54', "54 - Liquidación de Cobranza."),
    ('55', "55 - BVME para transporte ferroviario de pasajeros."),
    ('56', "56 - Comprobante de pago SEAE."),
    ('87', "87 - Nota de Crédito Especial - Documentos Autorizados."),
    ('88', "88 - Nota de Débito Especial - Documentos Autorizados."),
    ('91', "91 - Comprobante de No Domiciliado."),
    ('96', "96 - Exceso de crédito fiscal por retiro de bienes."),
    ('97', "97 - Nota de Crédito - No Domiciliado. "),
    ('98', "98 - Nota de Débito - No Domiciliado.")
]


def set_employee(field):
    """
    Decorator that set the employee to invoice in variable *posted_by*

    :param field: field of model

    :retun: decorator
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(cls, shipments, *args, **kwargs):
            pool = Pool()
            User = pool.get('res.user')
            user = User(Transaction().user)
            result = func(cls, shipments, *args, **kwargs)
            employee = user.employee

            if employee:
                company = employee.company
                cls.write([
                    s for s in shipments
                    if not getattr(s, field) and s.company == company
                ], {field: employee.id})
            else:
                company = user.company
                cls.write([
                    s for s in shipments if not getattr(s, "posted_by_user")
                    and s.company == company
                ], {"posted_by_user": user.id})

            return result

        return wrapper

    return decorator


def employee_field(string):
    """
    Function that create relation along invoice and employee

    :param field: field of model
    """

    return fields.Many2One(
        'company.employee',
        string,
        domain=[('company', '=', Eval('company', -1))],
        states={'readonly': Eval('state').in_(['posted', 'paid'])},
        depends=['company', 'state'])


def user_field(string):
    """
    Function that create relation along invoice and employee

    :param field: field of model
    """

    return fields.Many2One('res.user', string)


class Invoice(metaclass=PoolMeta):
    'Invoice'
    __name__ = 'account.invoice'
    invoice_type = fields.Selection(
        [
            ('mechanized', "Mecanizada"),
            ('electronic', "Electrónica")
        ],
        "Facturación",
        states={
            'readonly': Eval('state').in_(['validated', 'posted', 'paid', 'cancel', 'anulado', 'voided']),
        },
        depends=['state']

    )
    invoice_time = fields.Time(
        "Hora de Factura",
        states={
            'readonly': Eval('state').in_(['validated', 'posted', 'paid', 'cancel', 'anulado', 'voided']),
            'required': Eval('state').in_(
                If(Eval('type') == 'in',
                    ['validated', 'posted', 'paid'],
                    ['posted', 'paid'])),
        },
        depends=['state']
    )
    invoice_duedate = fields.Date(
        "Fecha de Expiración",
        states={
            'readonly': Eval('state').in_(['validated', 'posted', 'paid', 'cancel', 'anulado', 'voided']),
            'required': Eval('state').in_(
                If(Eval('type') == 'in',
                    ['validated', 'posted', 'paid'],
                    ['posted', 'paid'])),
        },
        depends=['state']
    )
    document_type = fields.Selection(
        _DOCUMENT_TYPE,
        'Comprobante de pago',
        states={
            'readonly': Eval('state').in_(['validated', 'posted', 'paid', 'anulado', 'voided'])
        }
    )
    modified_document = fields.Function(
        fields.Char(
            'Documento modificado',
            states={
                'invisible':
                ~Eval('document_type').in_(
                    ['commercial_credit', 'simple_credit',
                     'commercial_debit', 'simple_debit']),
            },
        ),
        'get_modified_document',
    )
    modified_document_date = fields.Function(
        fields.Date(
            'Fecha de documento modificado',
            states={
                'invisible':
                ~Eval('document_type').in_(
                    ['commercial_credit', 'simple_credit',
                     'commercial_debit', 'simple_debit']),
            },
        ),
        'get_modified_document_date',
    )
    sunat_document_type = fields.Selection(
        _SUNAT_DOCUMENT_TYPE,
        'Tipo de documento SUNAT',
        states={
            'readonly': (
                (Eval('document_type') != 'other') |
                (Eval('state').in_(['posted', 'paid', 'anulado', 'voided']))
            )
        }
    )
    sunat_serial_prefix = fields.Text('Prefijo SUNAT')
    sunat_serial = fields.Text('Número de serie SUNAT')
    sunat_number = fields.Text('Numero de documento SUNAT')
    sunat_generated_status = fields.Selection(
        _GENERATED_STATUS, 'Estado de factura electrónica generada')
    sunat_date_generated = fields.DateTime('Fecha de generación electrónica')
    sunat_invoice_status = fields.Function(
        fields.Selection(
            [
                ('', ''),
                ('rejected', 'Rechazada'),
                ('accepted', 'Aceptada'),
                ('error', 'Error')
            ],
            'Comprobante SUNAT',
            states={
                'invisible': Not(Bool(Eval('number')))
            }),
        'get_sunat_invoice_status',
    )
    sunat_sent_status = fields.Selection(
        _CODE_STATUS,
        'Estado de envío SUNAT'
    )
    sunat_sent_error = fields.Text('Error en el envío')
    sunat_date_sent = fields.DateTime('Fecha de envío SUNAT')
    sunat_response_code = fields.Char(string='Código respuesta SUNAT')
    sunat_response_message = fields.Text('Mensaje de respuesta')
    sunat_sent_observation = fields.One2Many('sunat.observation', 'document',
                                             'Observaciones SUNAT')
    sunat_digest = fields.Char('Digest SUNAT')
    sunat_invoice_related = fields.Many2One(
        'account.invoice',
        'Documento relacionado',
        required=False,
        domain=[
            ('sunat_invoice_status', '=', 'rejected'),
        ],
        states={
            'readonly': Eval('state').in_(['validated', 'posted', 'paid', 'cancel', 'anulado', 'voided']),
        },
        depends=['state']

    )
    global_discount = fields.Numeric(
        "Descuento Global",
        digits=(16, Eval('currency_digits', 2)),
        depends=['currency_digits', 'lines', 'untaxed_amount'])
    total_discount = fields.Function(
        fields.Numeric(
            "Descuento Total",
            digits=(16, Eval('currency_digits', 2)),
            depends=['currency_digits', 'lines', 'untaxed_amount']),
        'get_total_discount')
    total_inafected = fields.Function(
        fields.Numeric(
            "Operaciones inafectas",
            digits=(16, Eval('currency_digits', 2)),
            depends=['currency_digits', 'lines', 'untaxed_amount']),
        'get_inafected')
    total_exonerated = fields.Function(
        fields.Numeric(
            "Operaciones exoneradas",
            digits=(16, Eval('currency_digits', 2)),
            depends=['currency_digits', 'lines', 'untaxed_amount']),
        'get_exonerated')
    expiration_date = fields.Function(
        fields.Date("Fecha de vencimiento de la factura"),
        'get_remainder_time')
    amount_in_letters = fields.Function(
        fields.Char('Monto en letras', depends=['total_amount']),
        'get_amount_in_letters')

    posted_by = employee_field("Posted By")
    posted_by_user = user_field('Posted By')
    sunat_qr = fields.Function(fields.Binary('Código QR'), 'get_qr_code')

    debit_modified_document_reason = fields.Selection(
        _MODIFIED_DOCUMENT_TYPE_DEBIT,
        string='Razón de la nota de débito',
        select=True,
        states={
            'invisible': Not(
                Eval('document_type').in_(
                    ['simple_debit', 'commercial_debit']),
            )})

    modified_document_reason = fields.Selection(
        _MODIFIED_DOCUMENT_TYPE_CREDIT
        if Eval('document_type').in_(['simple_credit', 'commercial_credit'])
        else _MODIFIED_DOCUMENT_TYPE_DEBIT
        if Eval('document_type').in_(['simple_debit', 'commercial_debit'])
        else [('', '')],
        'Motivo',
        select=True,
        states={
            'invisible': Not(
                Eval('document_type').in_(
                    ['simple_credit', 'commercial_credit']),
            ),
            'required':
                Eval('document_type').in_(
                    ['simple_credit', 'commercial_credit']), })

    debit_note_reason = fields.Text('Razón de la Nota de Débito',
                                    states={
                                        'invisible': Not(
                                            Eval('document_type').in_(
                                                ['simple_debit', 'commercial_debit']),
                                        ),
                                        'readonly': Not(Eval('state') == 'draft'),
                                        'required': Eval('document_type').in_(
                                            ['simple_debit', 'commercial_debit']), })

    void_reason = fields.Char(
        'Razón de Baja',
        states = {
            'invisible': (Eval('state').in_(['draft', 'validated', 'posted', 'paid', 'cancel', 'anulado']))
        }
    )
    void_status = fields.Boolean(
        'Factura en Baja',
        states = {
            'invisible': (Eval('state').in_(['draft', 'validated', 'posted', 'paid', 'cancel', 'anulado']))
        }
    )
    void_ticket = fields.Char(
        'Ticket de Baja',
        states = {
            'invisible': (Eval('state').in_(['draft', 'validated', 'posted', 'paid', 'cancel', 'anulado']))
        }
    )


    @property
    def modified_document_reason_description(self):
        if self.modified_document_reason:
            for pair in _MODIFIED_DOCUMENT_TYPE_CREDIT:
                if pair[0] == self.modified_document_reason:
                    return pair[1]
            for pair in _MODIFIED_DOCUMENT_TYPE_DEBIT:
                if pair[0] == self.modified_document_reason:
                    return pair[1]
        return ''

    @staticmethod
    def default_invoice_type():
        return 'electronic'

    @staticmethod
    def default_sunat_invoice_status():
        return ''

    @staticmethod
    def default_void_status():
        return False

    @staticmethod
    def default_global_discount():
        return Decimal(0.0)

    @classmethod
    def default_payment_term(cls):
        payment_term = super(Invoice, cls).default_payment_term()
        if payment_term:
            return payment_term
        PaymentTerm = Pool().get('account.invoice.payment_term')
        payment_terms = PaymentTerm.search(
            [('active', '=', True),
             ('is_customer_payment_term_default', '=', True)])
        if len(payment_terms) == 1:
            return payment_terms[0].id

    def get_exonerated(self, name):
        return Decimal(0.0)

    def get_inafected(self, name):
        return Decimal(0.0)

    # La función extrae los tiempos de terminación de pagos de la base
    # de datos y los procesa para calcular
    # La fecha exacta de vencimiento de la factura.
    def get_remainder_time(self, invoices):
        term_date = ''
        term = self.payment_term
        if term and term.lines:
            for line in term.lines:
                if not line.relativedeltas or len(line.relativedeltas) == 0:
                    break

                _days = line.relativedeltas[0].days
                _weeks = line.relativedeltas[0].weeks
                _months = line.relativedeltas[0].months
                term_date = self.invoice_date + relativedelta(
                    months=+_months, weeks=+_weeks, days=+_days)
                break
        return term_date

    def get_qr_code(self, invoices, **kwargs):
        """
        Generates the qr code of the invoice, taking as data those requested by SUNAT

        :param invoices: current invoice, invoices.
        :param name: **kwargs

        :return: Binary field. Stores the generated image
        """
        fd = io.BytesIO()
        dataa = ""
        companyRUC = self.company.ruc if self.company.ruc else ""
        documentType = self.sunat_document_type if self.sunat_document_type else ""
        sunatSerial = self.sunat_serial_prefix + \
            self.sunat_serial if self.sunat_serial_prefix else ""
        sunatNumber = self.sunat_number if self.sunat_number else ""
        taxAmount = str(self.tax_amount) if self.tax_amount else "0.00"
        totalAmount = str(self.total_amount) if self.total_amount else "0.00"
        sunatDateGenerated = str(
            self.invoice_date) if self.invoice_date else ""
        documentTypeName = self.party.document_type_name if self.party.document_type_name else ""
        partyCode = str(
            self.party.document_number) if self.party.document_number else ""
        try:
            dataa = "" + companyRUC + "|" + documentType + "|" + sunatSerial \
                + "|" + sunatNumber + "|" + taxAmount + "|" + totalAmount + "|" \
                + sunatDateGenerated + "|" + documentTypeName + "|" + partyCode + "|"
        except TypeError:
            logger.info(
                "Algunos datos no se han encontrado, el código no puede ser generado. Codigo qr vacio"
            )

        image = treepoem.generate_barcode(barcode_type='qrcode', data=dataa)
        image.save(fd, format="png")
        fd.seek(0)
        return fields.Binary.cast(fd.read())

    @classmethod
    def get_amount_in_letters(cls, invoices, name):
        """
        Method to convert total amount to letters as peruvian tax
        authority require

        :param invoices: Invoice Objects
        :param name: Name

        :retun: Invoices dictionary
        """
        invoices_list = {}
        for invoice in invoices:
            if invoice.total_amount >= 0:
                if invoice.currency.id is not None:
                    if invoice.currency.code == 'USD':
                        currency_in_letters = 'DOLARES AMERICANOS'
                    elif invoice.currency.code == 'PEN':
                        currency_in_letters = 'SOLES'
                    elif invoice.currency.code == 'EUR':
                        currency_in_letters = 'EUROS'
                    else:
                        currency_in_letters = invoice.currency.name.upper()
                invoices_list[invoice.id] = to_word(
                    invoice.total_amount) + currency_in_letters
            else:
                invoices_list[invoice.id] = to_word(invoice.total_amount * -1)

        return invoices_list

    @classmethod
    def get_modified_document(cls, invoices, name):
        """
        Method to get the modified document in credit note dodcuments

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
        return invoices_list

    @staticmethod
    def default_sunat_sent_status():
        return ''

    @classmethod
    def __setup__(cls):
        super(Invoice, cls).__setup__()
        cls.number.readonly = False
        cls._check_modify_exclude.extend(['move', 'void_status'])
        cls.currency.states['readonly'] = Eval(
            'state').in_(['posted', 'paid']) | Eval('lines')
        cls.invoice_date.states['readonly'] = Eval(
            'state').in_(['validated', 'posted', 'paid', 'anulado', 'voided'])
        cls.number.states['readonly'] = Eval('state').in_(['posted', 'paid', 'anulado', 'voided']) | Equal(
            Eval('invoice_type'), 'electronic')
        cls.payment_lines.states['invisible'] = ~Eval('payment_lines')
        cls.state.selection.append(('anulado', 'Anulado'))
        cls.state.selection.append(('voided', 'En Baja'))
        cls._transitions |= set((
            ('posted', 'draft'),
            ('paid', 'anulado'),
            ('posted', 'anulado'),
        ))
        cls._buttons.update({
            'draft': {
                'invisible':
                (Eval('state').in_(['draft', 'paid', 'anulado', 'voided']) |
                 ((Eval('state') == 'cancel') & Eval('cancel_move'))),
            },
            'write_einvoice': {
                'invisible':
                Eval('state').in_(['draft', 'validated', 'anulado', 'cancel']) |
                ~(Eval('sunat_sent_status') == '99') |
                (Eval('type') == 'in')
            },
            'sign_einvoice': {
                'invisible':
                ~Equal(Eval('sunat_generated_status'), 'signederror'),
            },
            'send_einvoice': {
                'invisible':
                (Eval('state').in_(['draft', 'validated', 'anulado', 'cancel', 'voided'])) |
                (Eval('sunat_sent_status').in_(['0', '99'])) |
                (Eval('type') == 'in')
            },
            #'cancel_einvoice': {
                #'invisible':
                #(Eval('state').in_(['draft', 'validated', 'anulado', 'cancel']) |
                #~(Eval('sunat_invoice_status') == 'rejected')),

            #},
            'nullify_einvoice': {
                'invisible':
                ~(Eval('state') == 'paid')
            },
            'generate_xml': {
                'invisible':
                    ~(Equal(Eval('sunat_generated_status'), 'signedok'))
            }
        })

    @fields.depends('party', 'type')
    def on_change_party(self):
        super(Invoice, self).on_change_party()

        document_type = None
        if self.party:
            document_type = 'commercial'
            if self.party.document_type != 'pe_vat':
                document_type = 'simple'
        self.document_type = document_type

    @classmethod
    def set_number(cls, invoices):
        '''
        Set number to invoice
        '''
        Sequence = Pool().get('ir.sequence.strict')
        Date = Pool().get('ir.date')
        InvoiceSequence = Pool().get('account.invoice.sequence')

        for invoice in invoices:
            date = invoice.invoice_date or Date.today()
            if not invoice.document_type:
                cls.raise_user_error(
                    "No se ha definido un tipo de comprobante"
                )

            if invoice.state in {'posted', 'paid'}:
                continue

            if not invoice.tax_identifier:
                invoice.tax_identifier = invoice.get_tax_identifier()

            if invoice.invoice_type == 'electronic' and invoice.number:
                continue
            if invoice.document_type != 'other':
                invoice.sunat_document_type = '01'
                if invoice.document_type == 'simple':
                    invoice.sunat_document_type = '03'

            invoice_type = invoice.type
            if 'debit' in invoice.document_type:
                invoice_type += '_debit_note'
                invoice.sunat_document_type = '08'
            elif 'credit' in invoice.document_type:
                invoice_type += '_credit_note'
                invoice.sunat_document_type = '07'
            else:
                invoice_type += '_invoice'

            invoice_sequences = InvoiceSequence.search([
                ('invoice_type', '=', invoice_type),
                ('document_type', '=', invoice.document_type)
            ])

            if len(invoice_sequences) == 0:
                cls.raise_user_error(
                    "No se ha hallado un número de secuencia válido")

            period = invoice_sequences[0].period
            if invoice.type == 'out' and period and not (period.start_date <= date and
                               period.end_date >= date):
                cls.raise_user_error(
                    "No se ha hallado un periodo fiscal valido")

            fiscalyear = invoice_sequences[0].fiscalyear
            if invoice.type == 'out' and fiscalyear and not (fiscalyear.start_date <= date and
                                   fiscalyear.end_date >= date):
                cls.raise_user_error(
                    "No se ha hallado un ejercicio fiscal valido")

            with Transaction().set_context(date=Date.today()):
                if not invoice.number:
                    number = Sequence.get_id(
                        invoice_sequences[0].invoice_sequence.id)
                    invoice.number = number
                invoice_number = invoice.number.split('-')
                if len(invoice_number) == 2:
                    invoice.sunat_serial = invoice_number[0]
                    invoice.sunat_number = invoice_number[1]

                if not invoice.invoice_date and invoice.type == 'out':
                    invoice.invoice_date = Date.today()
                if not invoice.invoice_time and invoice.type == 'out':
                    invoice.invoice_time = Date.time()
                if not invoice.invoice_duedate and invoice.type == 'out':
                    #2. identificar la fecha del tipo de pago
                    dateAmount=invoice.payment_term.compute(
                        invoice.total_amount,
                        invoice.currency,
                        invoice.invoice_date
                    )
                    #Tuple of date,amount
                    finaldate = dateAmount[0][0]        
                    invoice.invoice_duedate = finaldate
        # cls.save(invoices)

    @classmethod
    @ModelView.button
    @Workflow.transition('validated')
    def validate_invoice(cls, invoices):
        for invoice in invoices:
            invoice.check_invoice_type()
        super(Invoice, cls).validate_invoice(invoices)

    def check_invoice_type(self):
        if not self.document_type:
            self.raise_user_error(
                'No se ha determinado un tipo de comprobante válido')

    @classmethod
    def check_modify(cls, invoices):
        return

    def check_cancel_move(self):
        if (self.type == 'out' and self.cancel_move) and self.void_status is False:
            self.raise_user_error('customer_invoice_cancel_move',
                                  self.rec_name)

    @classmethod
    def get_mode_cert(cls):
        pool = Pool()
        Company = pool.get('company.company')
        company_id = Transaction().context.get('company')
        if not company_id:
            cls.raise_user_error('company_not_defined')
        return Company(company_id)

    @classmethod
    #If there are not lines in invoice, the amount of invoice is 0.00
    #This method validate lines in invoice, they can not be 0
    def validate_quantity_lines_invoice(cls, invoice):
        'validate the quantity of lines in invoice cant be 0'
        if len(invoice.lines) == 0:
            cls.raise_user_error("No existen productos registrados en la factura")

    @classmethod
    #If there are lines in invoice with amount 0 or quantity 0, the amount of invoice will be 0.00
    #This method validate line by line in invoice, the amount or quantity of each line ca not be 0
    def validate_amount_invoice(cls, invoice):
        'validate the amount of the invoice'
        listProductsWAmount = []
        listProductsWQuantity = []
        if invoice.lines:
            listProductsWAmount = []
            listProductsWQuantity = []
            for line in invoice.lines:
                if line.unit_price == Decimal('0.00'):
                    listProductsWAmount.append(line.product.name)

                if line.quantity == 0:
                    listProductsWQuantity.append(line.product.name)

            strError = ""
            if len(listProductsWAmount) > 0:
                strError += "Hay productos con precio de venta " + invoice.currency.symbol + " 0.00 :\n" + '\n'.join(listProductsWAmount) + '\n'

            if len(listProductsWQuantity) > 0:
                strError += "Hay productos con cantidad de venta 0:\n" + '\n'.join(listProductsWQuantity) + '\n'

            if len(listProductsWAmount) > 0 or len(listProductsWQuantity) > 0:
                cls.raise_user_error(strError)


    @classmethod
    def check_invoice_move_date(cls, invoice, move):
        '''validate invoice move date'''
        today = Pool().get('ir.date').today()
        '''
        if (move.date + relativedelta(months=+1)) < today:
            cls.raise_user_error("La fecha efectiva no puede ser menor a un mes del periodo actual")
        if move.date > (invoice.invoice_date + timedelta(days = 365)):
            cls.raise_user_error("La fecha efectiva asiento no puede ser mayor a 1 año de la fecha de emisión")
        '''


    @classmethod
    def check_invoice_date_out(cls, invoice):
        '''validate invoice date'''
        today = Pool().get('ir.date').today()

        '''
        if invoice.type == 'out' and invoice.invoice_type == 'electronic':
            if invoice.invoice_date > today:
                cls.raise_user_error("La fecha de factura no puede ser mayor a la fecha actual")
            elif invoice.invoice_date < today:
                    cls.raise_user_error("La fecha de factura no puede ser menor a la fecha actual")
        '''


    @classmethod
    @ModelView.button
    @Workflow.transition('posted')
    @set_employee('posted_by')
    def post(cls, invoices):
        pool = Pool()
        Move = pool.get('account.move')
        CurrencyRates = pool.get('currency.currency.rate')
        Invoice = pool.get('account.invoice')
        InvoiceLine = pool.get('account.invoice.line')

        cls.set_number(invoices)

        moves = []

        for invoice in invoices:
            # From now, the invoices cant be posted if the rate of the current invoice isn't exist
            cls.validate_quantity_lines_invoice(invoice)
            cls.validate_amount_invoice(invoice)
            # cls.check_invoice_date_out(invoice)
            invoice_rate = CurrencyRates.search(
                [('date', '=', invoice.invoice_date),
                 ('currency', '=', invoice.currency),
                 ], order=[('date', 'DESC')], limit=1)
            if invoice.document_type in ['simple_credit', 'commercial_credit']\
                    and invoice.type == 'out':
                origin_invoice = None
                if len(invoice.lines) > 0 and \
                        hasattr(invoice.lines[0].origin, 'invoice'):
                    origin_invoice = invoice.lines[0].origin.invoice
                if origin_invoice:
                    total_credit_amount = Decimal('0.00')
                    credit_invoices_line = InvoiceLine.search([
                        ('origin', 'in', [str(l)
                                          for l in origin_invoice.lines]),
                    ])
                    credit_invoices = [
                        line.invoice for line in credit_invoices_line]
                    for credit_invoice in credit_invoices:
                        if credit_invoice.id != invoice.id and\
                                credit_invoice.modified_document == origin_invoice.number and\
                            origin_invoice.document_type in credit_invoice.document_type and\
                                credit_invoice.state in ['posted', 'paid']:
                            total_credit_amount += abs(
                                credit_invoice.total_amount)
                    if origin_invoice.total_amount < total_credit_amount + abs(invoice.total_amount):
                        amount = str(origin_invoice.total_amount -
                                     total_credit_amount)
                        cls.raise_user_error(
                            "Solo puede abonar un máximo de " + amount)

            if not invoice_rate and invoice.currency != invoice.company.currency\
                    and invoice.invoice_date == datetime.today():
                cls.raise_user_error(
                    'No puede facturar. La moneda de la factura no tiene tipo de cambio para hoy')

            move = invoice.get_move()
            cls.check_invoice_move_date(invoice, move)

            if move != invoice.move:
                invoice.move = move
                cls.check_invoice_move_date(invoice, move)
                moves.append(move)

            if invoice.state != 'posted':
                invoice.state = 'posted'

            if invoice.type == 'out':
                if sunat_invoicing_path is None:
                    cls.raise_user_error(
                        "No se ha especificado una ruta de "
                        "almacenamiento para las facturas electrónicas")
                if invoice.type == 'out' and \
                        invoice.document_type == 'simple':
                    invoice.sunat_serial_prefix = 'B'
                    invoice.sunat_document_type = '03'
                elif invoice.type == 'out' and \
                        invoice.document_type == 'simple_credit':
                    invoice.sunat_serial_prefix = 'B'
                    invoice.sunat_document_type = '07'
                elif invoice.type == 'out' and \
                        invoice.document_type == 'commercial':
                    invoice.sunat_serial_prefix = 'F'
                    invoice.sunat_document_type = '01'
                elif invoice.type == 'out' and \
                        invoice.document_type == 'commercial_credit':
                    invoice.sunat_serial_prefix = 'F'
                    invoice.sunat_document_type = '07'
                elif invoice.type == 'out' and \
                        invoice.document_type == 'simple_debit':
                    invoice.sunat_serial_prefix = 'B'
                    invoice.sunat_document_type = '08'
                elif invoice.type == 'out' and \
                        invoice.document_type == 'commercial_debit':
                    invoice.sunat_serial_prefix = 'F'
                    invoice.sunat_document_type = '08'
                else:
                    cls.raise_user_error("No es un comprobante válido")
                try:
                    serial, number = invoice.number.split('-')
                except:
                    cls.raise_user_error(
                        "El número de factura no es válido")
                invoice.sunat_serial = serial
                invoice.sunat_number = number
                if invoice.invoice_type == 'electronic' and \
                        invoice.company.invoicing_mode != '':
                    sunat_invoice = DocumentFactory.get_document(invoice)
                    sunat_invoice.write_document(
                        sunat_invoice,
                        path=sunat_invoicing_path,
                        on_success=cls.on_file_created,
                        on_failure=cls.on_file_creation_failed)

        if moves:
            Move.save(moves)
        cls.save(invoices)
        Move.post([i.move for i in invoices if i.move.state != 'posted'])
        for invoice in invoices:
            if invoice.type == 'out':
                invoice.print_invoice()

    @classmethod
    @ModelView.button
    def write_einvoice(cls, invoices):
        for invoice in invoices:
            sunat_invoice = DocumentFactory.get_document(invoice)
            sunat_invoice.write_document(
                sunat_invoice,
                path=sunat_invoicing_path,
                on_success=cls.on_file_created,
                on_failure=cls.on_file_creation_failed)
            invoice.sunat_date_generated = datetime.now()
            if invoice.sunat_sent_status == '0':
                invoice.sunat_sent_error = ''
        cls.save(invoices)

    @classmethod
    @ModelView.button_action('account_invoice_pe.wizard_generate_xml')
    def generate_xml(cls, invoices):
        'label'
        for invoice in invoices:
            pass

    @classmethod
    @ModelView.button
    def sign_einvoice(cls, invoices):
        for invoice in invoices:
            sunat_invoice = DocumentFactory.get_document(invoice)
            DocumentSigner.sign_document(
                sunat_invoice,
                sunat_invoicing_path,
                on_success=cls.signing_successful,
                on_failure=cls.failed_sign)

        cls.save(invoices)


    @classmethod
    @ModelView.button
    def send_einvoice(cls, invoices):
        for invoice in invoices:
            try:
                if not invoice.sunat_document_type or len(
                        invoice.sunat_document_type) == 0:
                    continue
                document = DocumentFactory.get_document(invoice)

                client = cls.prepare_soap_client(invoice)
                document.send(
                    client,
                    file_path=sunat_invoicing_path,
                    on_success=cls.sunat_send_success,
                    on_failure=cls.sunat_send_failure)

            except Exception as e:
                invoice.sunat_sent_error = str(e)
                print(str(e))

        cls.save(invoices)



    @classmethod
    def resend_einvoice(cls):

        pool = Pool()
        Date = pool.get('ir.date')

        start_date = Date.today()
        end_date = start_date - timedelta(days = 5)

        error_invoices = pool.get('account.invoice').search([
            ('sunat_sent_status', '!=', '0'),
            ('state', 'in', ['posted', 'paid']),
            ('invoice_date', '<=', start_date),
            ('invoice_date', '>=', end_date)
        ], order = [('invoice_date', 'DESC')])

        logs = []

        for invoice in error_invoices:
            try:
                document = DocumentFactory.get_document(invoice)
                client = cls.prepare_soap_client(invoice)
                document.send(
                    client,
                    file_path=sunat_invoicing_path,
                    on_success=cls.sunat_send_success,
                    on_failure=cls.sunat_send_failure
                )
                invoice.save()
                logs.append(invoice)

            except Exception:
                continue

        return logs

    @classmethod
    def import_cron_resend_einvoice(cls, mail_to):
        logs = cls.resend_einvoice()
        cls.send_mail_report(logs, mail_to)

    @classmethod
    def send_mail_report(cls, logs, mail_to):

        uri_config = config.get('email', 'uri')
        uri_parsed = urlparse(uri_config)
        email_addrs = config.get('email', 'from')
        email_parsd = email.utils.parseaddr(email_addrs)
        SENDER = email_parsd[1]
        SENDERNAME = email_parsd[0]

        USERNAME_SMTP = uri_parsed.username
        PASSWORD_SMTP = uri_parsed.password

        HOST = uri_parsed.hostname
        PORT = uri_parsed.port

        RECIPIENT = mail_to
        SUBJECT = 'Registro de eventos al reenviar facturas a la SUNAT'

        msg = MIMEMultipart('alternative')
        msg['Subject'] = SUBJECT
        msg['From'] = email.utils.formataddr((SENDERNAME, SENDER))
        msg['To'] = RECIPIENT

        BODY_TEXT = ''
        BODY_HTML = ''

        if len(logs) > 0:

            BODY_TEXT = (
                "Mediante la presente se le informa que se reenviaron facturas a la SUNAT con el siguiente detalle:\n"
            )

            html_open = """<html>
                <head></head>
                <body>
                  <p>Mediante la presente se le informa que se reenviaron facturas a la SUNAT con el siguiente detalle:</p>
                  <ul>
                        """

            html_close = """</ul>
                    </body>
                </html>
                       """
            BODY_HTML += html_open

            for log in logs:

                invoice_serial = log.sunat_serial
                invoice_number = log.sunat_number
                invoice_prefix = log.sunat_serial_prefix
                status = ''

                if log.sunat_sent_status == '0':
                    status = 'Procesó correctamente'
                elif log.sunat_sent_status == '98':
                    status = 'En proceso'
                elif log.sunat_sent_status == '99':
                      status = 'Proceso con errores'
                elif log.sunat_sent_status == '':
                    status = 'Proceso sin respuesta'

                document = '{invoice_prefix}''{invoice_serial}-{invoice_number}'.format(
                    invoice_prefix=invoice_prefix,
                    invoice_serial=invoice_serial,
                    invoice_number=invoice_number
                )

                BODY_TEXT += document +', estado: '+ status +"\n"
                BODY_HTML += '<li>'+ document +', estado: '+ status +'</li>'

            BODY_HTML += html_close
        else:

            BODY_TEXT = (
                "Mediante la presente se le informa que SUNAT no recibió ninguna de las facturas reenviadas."
            )

            BODY_HTML = """<html>
            <head></head>
            <body>
              <p>Mediante la presente se le informa que SUNAT no recibió ninguna de las facturas reenviadas.</p>
            </body>
            </html>
                        """

        part1 = MIMEText(BODY_TEXT, 'plain')
        part2 = MIMEText(BODY_HTML, 'html')

        msg.attach(part1)
        msg.attach(part2)

        try:
            server = smtplib.SMTP(HOST, PORT)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(USERNAME_SMTP, PASSWORD_SMTP)
            server.sendmail(SENDER, RECIPIENT, msg.as_string())
            server.close()
        except Exception as exception:
            print(('Error: ', str(exception)))
        else:
            print(('Exito: informe enviado a ', str(RECIPIENT)))

    def _debit(self):
        '''
        Return values to debit invoice.
        '''
        debit = self.__class__()

        for field in ('company', 'party', 'invoice_address', 'currency',
                      'journal', 'account', 'payment_term', 'description',
                      'comment', 'type', 'document_type'):
            if getattr(self, field) in ('simple', 'commercial'):
                setattr(
                    debit, field, '{document_type}_debit'.format(
                        document_type=getattr(self, field)))
            else:
                setattr(debit, field, getattr(self, field))
        debit.lines = [line._debit() for line in self.lines]
        debit.taxes = [tax._debit() for tax in self.taxes if tax.manual]
        return debit

    @classmethod
    def debit(cls, invoices, reason=None, debit_note_reason=None):
        '''
        debit invoices and return ids of new invoices.
        Return the list of new invoice
        '''
        MoveLine = Pool().get('account.move.line')

        new_invoices = [i._debit() for i in invoices]
        if reason != '':
            for new_invoice in new_invoices:
                new_invoice.debit_modified_document_reason = reason
        if debit_note_reason:
            for new_invoice in new_invoices:
                new_invoice.debit_note_reason = debit_note_reason
        cls.save(new_invoices)
        cls.update_taxes(new_invoices)
        # cls.post(new_invoices)
        """for invoice, new_invoice in itertools.izip(invoices, new_invoices):
            if new_invoice.state == 'posted':
                MoveLine.reconcile([l for l in invoice.lines_to_pay
                        if not l.reconciliation] +
                    [l for l in new_invoice.lines_to_pay
                        if not l.reconciliation])"""

        return new_invoices

    @classmethod
    def voided(cls, invoices, reason=None):
        '''
        Null a invoice and send the same to SUNAT
        Return the list of new invoice
        '''
        pool = Pool()
        Move = pool.get('account.move')
        Line = pool.get('account.move.line')
        cancel_moves = []
        delete_moves = []
        to_save = []

        for invoice in invoices:
            invoice.void_status = True
            invoice.void_reason = reason
            invoice.save()
            if invoice.move:
                if invoice.move.state == 'draft':
                    delete_moves.append(invoice.move)
                elif not invoice.cancel_move:
                    invoice.cancel_move = invoice.move.cancel()
                    to_save.append(invoice)
                    cancel_moves.append(invoice.cancel_move)

        for invoice in invoices:
            for line in invoice.payment_lines:
                if line.move:
                    if line.state == 'draft':
                        delete_moves.append(line)
                    else:
                        a = line.move.cancel()
                        to_save.append(invoice)
                        cancel_moves.append(a)

        if cancel_moves:
            Move.save(cancel_moves)
        if delete_moves:
            Move.delete(delete_moves)
        if cancel_moves:
            Move.post(cancel_moves)

        cls.save(to_save)
        # Write state before reconcile to prevent invoice to go to paid state
        cls.write(invoices, {
            'state': 'voided',
        })
        # Reconcile lines to pay with the cancellation ones if possible
        for invoice in invoices:
            if not invoice.move or not invoice.cancel_move:
                continue
            to_reconcile = []
            for line in invoice.move.lines + invoice.cancel_move.lines + invoice.payment_lines:
                if line.account == invoice.account:
                    if line.reconciliation:
                        break
                    to_reconcile.append(line)
            else:
                if to_reconcile:
                    Line.reconcile(to_reconcile)

        cls.send_voided(invoices)
        cls.save(invoices)

        return invoices

    @classmethod
    def send_voided(cls, invoices):
        for invoice in invoices:
            if invoice.company.invoicing_mode != '':
                sunat_invoice = DocumentFactory.get_document(invoice)
                sunat_invoice.write_document(
                    sunat_invoice,
                    path=sunat_invoicing_path,
                    on_success=cls.on_file_created,
                    on_failure=cls.on_file_creation_failed)

    def _credit(self):
        '''
        Return values to credit invoice.
        '''
        credit = self.__class__()
        for field in ('company', 'party', 'invoice_address', 'currency',
                      'journal', 'account', 'payment_term', 'description',
                      'comment', 'type', 'document_type'):
            if getattr(self, field) in ('simple', 'commercial'):
                setattr(
                    credit, field, '{document_type}_credit'.format(
                        document_type=getattr(self, field)))
            else:
                setattr(credit, field, getattr(self, field))
        credit.lines = [line._credit() for line in self.lines]
        credit.taxes = [tax._credit() for tax in self.taxes if tax.manual]
        return credit

    @classmethod
    @ModelView.button
    @Workflow.transition('draft')
    def draft(cls, invoices):
        """
        workflow method to set the state of the invoice to draft

        :param invoices: list with invoice objects, provided by the tryton
        client
        """
        pool = Pool()
        Move = pool.get('account.move')
        try:
            Payment = pool.get('account.payment')
        except KeyError:
            Payment = None
        try:
            Commission = pool.get('commission')
        except KeyError:
            Commission = None
        moves = []
        lines = []
        for invoice in invoices:
            if invoice.move:
                if invoice.move.period.state == 'close':
                    cls.raise_user_error(
                        'draft_closed_period', {
                            'invoice': invoice.rec_name,
                            'period': invoice.move.period.rec_name,
                        })
                moves.append(invoice.move)
                lines.extend([l.id for l in invoice.move.lines])
        if moves:
            with Transaction().set_context(draft_invoices=True):
                Move.write(moves, {'state': 'draft'})
        if Payment:
            payments = Payment.search([
                ('line', 'in', lines),
                ('state', '=', 'failed'),
            ])
            if payments:
                Payment.write(payments, {'line': None})
        if Commission:
            for sub_invoices in grouped_slice(invoices):
                ids = [i.id for i in sub_invoices]
                commissions = Commission.search([
                    ('origin.invoice', 'in', ids, 'account.invoice.line'),
                ])
                Commission.delete(commissions)
        cls.write(invoices, {
            'invoice_report_format': None,
            'invoice_report_cache': None,
        })

    @classmethod
    @Workflow.transition('cancel')
    def cancel(cls, invoices):
        for invoice in invoices:
            if invoice.type == 'out' and invoice.number:
                cls.raise_user_error('cancel_invoice_with_number')

        return super(Invoice, cls).cancel(invoices)

    @classmethod
    def on_file_created(cls, document, result=None):
        document.document.sunat_generated_status = 'generatedok'
        document.document.sunat_date_generated = datetime.now()
        DocumentSigner.sign_document(
            document,
            sunat_invoicing_path,
            on_success=cls.signing_successful,
            on_failure=cls.failed_sign)

    @classmethod
    def on_file_creation_failed(cls, document, error=None):
        document.document.sunat_generated_status = 'generatederror'
        cls.raise_user_error(
            'Falló la generación de documento electrónico: {error}'.format(
                error=error))

    @classmethod
    def signing_successful(cls, document, result=None):
        # TODO: update status in database

        document.document.sunat_generated_status = 'signedok'
        document.document.save()
        client = cls.prepare_soap_client(document.document)
        if client:
            document.send(
                client,
                file_path=sunat_invoicing_path,
                on_success=cls.sunat_send_success,
                on_failure=cls.sunat_send_failure
            )

    @classmethod
    def failed_sign(cls, document, error=None):
        # TODO: update status in database
        document.document.sunat_generated_status = 'signederror'
        cls.raise_user_error(
            "falló la firma del documento electrónico: {error} ({document}) ".
            format(error=error, document=str(document.document.id)))

    @classmethod
    def sunat_send_success(cls, document, result=None):
        document.document.sunat_sent_status = '0'
        document.document.sunat_sent_error = ''

        #Send mail
        recipients = cls._prepare_email_recipients(document.document)

        try:
            document.mail_to(
                recipients=recipients,
                sender=config.get('email', 'from'),
                file_path=sunat_invoicing_path,
                message=cls._prepare_mail_message(document))
        except Exception as e:
            print('Error')
            print(str(e))
            logger.info(str(e))

        cls.save_observations(document)

    @classmethod
    def sunat_send_failure(cls, document, error=None):
        document.document.sunat_sent_status = document.sent_status
        if error:
            if type(error) is str:
                document.document.sunat_sent_error = error
            else:
                document.document.sunat_sent_error = error.message
        cls.save_observations(document)
        if error is not None:
            document.document.sunat_sent_status = '99'

    @classmethod
    def _prepare_email_recipients(cls, invoice):
        recipients = list()
        recipients.append(invoice.company.invoicing_email_receiver)
        for contact_mechanism in invoice.party.contact_mechanisms:
            if contact_mechanism.type == 'email' and contact_mechanism.invoice:
                recipients.append(contact_mechanism.value)

        return recipients

    @classmethod
    def _prepare_mail_message(cls, document):
        meta = document.document

        street = ' '
        if meta.company.party.addresses[0].street:
            street = meta.company.party.addresses[0].street

        district = ' '
        if meta.company.party.addresses[0].district:
            district = meta.company.party.addresses[0].district.name

        province = ' '
        if meta.company.party.addresses[0].province:
            province = meta.company.party.addresses[0].province.name

        country = ' '
        if meta.company.party.addresses[0].country:
            country = meta.company.party.addresses[0].country.name

        result = MarkupTemplate(default_email_template_string).generate(
            company_website=meta.company.invoicing_website,
            logo_url='',
            company_name=meta.company.party.name,
            party_name=meta.party.name,
            transaction_message='Gracias por tu preferencia',
            invoice_url='',
            company_street=street,
            company_district=district,
            company_province=province,
            company_country=country).render(
            method='html', doctype='html', encoding='iso-8859-1')
        if type(result) is bytes:
            result = result.decode('iso-8859-1')
        result = re.sub('\\n', '', result)
        return result

    @classmethod
    def prepare_soap_client(cls, invoice):
        token = UsernameToken(
            username=invoice.company.sol_username,
            password=base64.b64decode(invoice.company.sol_password).decode('utf-8'))
        is_production_env = invoice.company.invoicing_mode == 'production'
        try:
            return SoapClient(wsse=token, production=is_production_env)
        except Exception as e:
            invoice.sunat_response_message = str(e)
            print(e)
            logger.info(e)
            return None

    @classmethod
    def save_observations(cls, document):
        obs = document.observations
        if obs is None or len(obs) == 0:
            return

        for code in list(obs.keys()):
            values = dict()
            SunatObservation = Pool().get('sunat.observation')
            values['code'] = code
            values['description'] = obs[code]
            values['document'] = document.document.id
            SunatObservation.create([values])

    def get_total_discount(self, name):
        total_discount = Decimal(0.0)
        line_pre_discount = Decimal(0.0)
        for line in self.lines:
            line.global_discount = self.global_discount
            line_pre_discount += line.gross_unit_price * Decimal(line.quantity)
        total_discount = line_pre_discount - self.untaxed_amount
        return total_discount

    def get_sunat_invoice_status(self, name):
        """This method allows to obtain the state of send in SUNAT

        Arguments:
            name {str} -- The name of the field

        Returns:
            str -- The str value of the dictionary
        """
        if self.sunat_response_message and 'aceptada' in self.sunat_response_message:
            return 'accepted'
        elif self.sunat_sent_error and 'informado anteriormente' in self.sunat_sent_error:
            return 'accepted'
        elif self.sunat_sent_error and 'fuera de la fecha' in self.sunat_sent_error:
            return 'rejected'
        elif self.sunat_sent_error:
            return 'error'
        else:
            return ''

    @classmethod
    @ModelView.button
    def nullify_einvoice(cls, invoices):
        pool = Pool()
        Move = pool.get('account.move')
        Line = pool.get('account.move.line')
        Reconciliation = pool.get('account.move.reconciliation')
        for invoice in invoices:
            payment_lines = [
                x for x in invoice.payment_lines if invoice.payment_lines]
            moves = [x.move for x in payment_lines if payment_lines]

            for move in moves:
                # Move.cancel(move)
                cancel_moves = Move.search([
                    ('origin', '=', str(move))
                ])
                alredy_cancel_moves = [
                    x.origin for x in cancel_moves if cancel_moves]
                if move not in alredy_cancel_moves:
                    reconciliations = [
                        x.reconciliation for x in move.lines if x.reconciliation]
                    if reconciliations:
                        Reconciliation.delete(reconciliations)
                    cancel_move = move.cancel()
                    Move.post([cancel_move])
                    to_reconcile = defaultdict(list)
                    for line in move.lines + cancel_move.lines:
                        if line.account.reconcile:
                            to_reconcile[(line.account, line.party)
                                         ].append(line)
                    for lines in to_reconcile.values():
                        Line.reconcile(lines)

        cls.write(invoices, {
            'state': 'posted',
        })
        return None

    @classmethod
    def credit(cls, invoices, refund=False, reason=''):
        '''
        Credit invoices and return ids of new invoices.
        Return the list of new invoice
        '''
        MoveLine = Pool().get('account.move.line')
        new_invoices = [i._credit() for i in invoices]

        if reason != '':
            for new_invoice in new_invoices:
                new_invoice.modified_document_reason = reason

        cls.save(new_invoices)
        cls.update_taxes(new_invoices)
        if refund:
            cls.post(new_invoices)
            for invoice, new_invoice in zip(invoices, new_invoices):
                if new_invoice.state == 'posted':
                    MoveLine.reconcile([
                        l for l in invoice.lines_to_pay if not l.reconciliation
                    ] +
                        [l for l in new_invoice.lines_to_pay
                            if not l.reconciliation])
        return new_invoices

    def pay_invoice(self, amount, payment_method, date, description,
                    amount_second_currency=None, second_currency=None, operation_number=None, **kwargs):
        '''
        Adds a payment of amount to an invoice using the journal, date and
        description.
        Returns the payment line.'''
        pool = Pool()
        Move = pool.get('account.move')
        Line = pool.get('account.move.line')
        Period = pool.get('account.period')

        line1 = Line(description=description, account=self.account, operation_number=operation_number)
        line2 = Line(description=description)
        lines = [line1, line2]

        if amount >= 0:
            if self.type == 'out':
                line1.debit, line1.credit = 0, amount
            else:
                line1.debit, line1.credit = amount, 0
        else:
            if self.type == 'out':
                line1.debit, line1.credit = -amount, 0
            else:
                line1.debit, line1.credit = 0, -amount

        line2.debit, line2.credit = line1.credit, line1.debit
        if line2.debit:
            payment_account = 'debit_account'
        else:
            payment_account = 'credit_account'
        line2.account = getattr(payment_method, payment_account).current(date=date)

        # if self.account == line2.account:
        #     self.raise_user_error('same_%s' % account_journal, {
        #         'journal': journal.rec_name,
        #         'invoice': self.rec_name,
        #     })
        # if not line2.account:
        #     self.raise_user_error('missing_%s' % account_journal,
        #                           (journal.rec_name,))

        for line in lines:
            if line.account.party_required:
                line.party = self.party
            if amount_second_currency:
                line.amount_second_currency = amount_second_currency.copy_sign(
                    line.debit - line.credit)
                line.second_currency = second_currency

        period_id = Period.find(self.company.id, date=date)

        move = Move(journal=payment_method.journal, period=period_id, date=date,
                origin=self, description=description, company=self.company, lines=lines)
        move.save()
        Move.post([move])

        for line in move.lines:
            if line.account == self.account:
                self.add_payment_lines({self: [line]})
                return line
        raise Exception('Missing account')

    @classmethod
    @ModelView.button
    def nullify_einvoice(cls, invoices):
        """Cancel the pays of the invoice"""
        pool = Pool()
        Move = pool.get('account.move')
        Line = pool.get('account.move.line')
        Reconciliation = pool.get('account.move.reconciliation')
        for invoice in invoices:
            payment_lines = [
                x for x in invoice.payment_lines if invoice.payment_lines]
            moves = [x.move for x in payment_lines if payment_lines]

            for move in moves:
                # Move.cancel(move)
                cancel_moves = Move.search([
                    ('origin', '=', str(move))
                ])
                alredy_cancel_moves = [
                    x.origin for x in cancel_moves if cancel_moves]
                if move not in alredy_cancel_moves:
                    reconciliations = [
                        x.reconciliation for x in move.lines if x.reconciliation]
                    if reconciliations:
                        Reconciliation.delete(reconciliations)
                    cancel_move = move.cancel()
                    Move.post([cancel_move])
                    to_reconcile = defaultdict(list)
                    for line in move.lines + cancel_move.lines:
                        if line.account.reconcile:
                            to_reconcile[(line.account, line.party)
                                         ].append(line)
                    for lines in to_reconcile.values():
                        Line.reconcile(lines)

        cls.write(invoices, {
            'state': 'posted',
        })
        return None


class PayInvoice(metaclass=PoolMeta):
    '''Transition pay modify '''
    __name__ = 'account.invoice.pay'

    def transition_pay(self):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Currency = pool.get('currency.currency')
        MoveLine = pool.get('account.move.line')

        invoice = Invoice(Transaction().context['active_id'])

        with Transaction().set_context(date=self.start.date):
            amount = Currency.compute(self.start.currency,
                                      self.start.amount, invoice.company.currency)
            amount_invoice = Currency.compute(
                self.start.currency, self.start.amount, invoice.currency)

        reconcile_lines, remainder = self.get_reconcile_lines_for_amount(
            invoice, amount)

        amount_second_currency = None
        second_currency = None
        if self.start.currency != invoice.company.currency:
            amount_second_currency = self.start.amount
            second_currency = self.start.currency

        '''
        if (0 <= invoice.amount_to_pay < amount_invoice
                or amount_invoice < invoice.amount_to_pay <= 0
                and self.ask.type != 'writeoff'):
            self.raise_user_error('amount_greater_amount_to_pay',
                (invoice.rec_name,))
        '''

        line = None
        if not invoice.company.currency.is_zero(amount):
            line = invoice.pay_invoice(amount,
                self.start.payment_method, self.start.date, self.start.description,
                amount_second_currency, second_currency, self.start.operation_number)

        if remainder != Decimal('0.0'):
            if self.ask.type == 'writeoff':
                lines = [l for l in self.ask.lines] + \
                    [l for l in invoice.payment_lines
                        if not l.reconciliation]
                if line and line not in lines:
                    # Add new payment line if payment_lines was cached before
                    # its creation
                    lines += [line]
                if lines:
                    MoveLine.reconcile(lines,
                        writeoff=self.ask.writeoff,
                        date=self.start.date)
        else:
            if line:
                reconcile_lines += [line]
            if reconcile_lines:
                MoveLine.reconcile(reconcile_lines)
        return 'end'


class PayInvoiceStart(metaclass=PoolMeta):
    '''Add operation number'''
    __name__ = 'account.invoice.pay.start'
    operation_number = fields.Char("Nro. Operación")

    @staticmethod
    def default_description():
        Invoice = Pool().get('account.invoice')
        invoice = Invoice(Transaction().context['active_id'])
        return invoice.number


class MoveLine(metaclass=PoolMeta):
    '''Add field operation number'''
    __name__ = 'account.move.line'
    operation_number = fields.Char("Nro. Operación")


class InvoiceLine(metaclass=PoolMeta):
    __name__ = 'account.invoice.line'
    gross_unit_price = fields.Numeric(
        'Precio bruto',
        digits=price_digits,
        states={
            'invisible': Eval('type') != 'line',
            'required': Eval('type') == 'line',
            'readonly': Eval('invoice_state') != 'draft',
        },
        depends=['type', 'invoice_state'])

    gross_unit_price_wo_round = fields.Numeric(
        'Precio bruto sin redondeo',
        digits=(16, price_digits[1] + discount_digits[1]),
        readonly=True)

    discount = fields.Numeric(
        'Descuento',
        digits=discount_digits,
        states={
            'invisible': Eval('type') != 'line',
            'required': Eval('type') == 'line',
            'readonly': Eval('invoice_state') != 'draft',
        },
        depends=['type', 'invoice_state'])

    global_discount = fields.Numeric(
        'Descuento global',
        digits=discount_digits,
        states={
            'invisible': Eval('type') != 'line',
            'required': Eval('type') == 'line',
            'readonly': Eval('invoice_state') != 'draft',
        },
        depends=['type', 'invoice_state'])

    @classmethod
    def __setup__(cls):
        super(InvoiceLine, cls).__setup__()
        cls.unit_price.states['readonly'] = True
        cls.unit_price.digits = (20, price_digits[1] + discount_digits[1])
        if 'discount' not in cls.amount.on_change_with:
            cls.amount.on_change_with.add('discount')
        if 'global_discount' not in cls.amount.on_change_with:
            cls.amount.on_change_with.add('global_discount')
        if 'gross_unit_price' not in cls.amount.on_change_with:
            cls.amount.on_change_with.add('gross_unit_price')

    @staticmethod
    def default_discount():
        return Decimal(0.0)

    @staticmethod
    def default_global_discount():
        return Decimal(0.0)

    def update_prices(self):
        digits = self.__class__.gross_unit_price.digits[1]
        unit_price = self.unit_price if self.unit_price else _ZERO
        gross_unit_price = self.gross_unit_price if self.gross_unit_price else _ZERO
        discount = self.discount if self.discount else _ZERO
        global_discount = self.global_discount if self.global_discount else _ZERO

        if gross_unit_price is not None and (discount is not None
                                             or global_discount is not None):
            unit_price = gross_unit_price * (1 - discount) * (
                1 - global_discount)
            digits = self.__class__.unit_price.digits[1]
            unit_price = unit_price.quantize(Decimal(str(10.0**-digits)))

            # if discount != 1:
            #    gross_unit_price_wo_round = unit_price / (1 - discount)

            # if global_discount != 1:
            #    gross_unit_price_wo_round = gross_unit_price_wo_round / (1 - global_discount)

            # gross_unit_price = gross_unit_price_wo_round.quantize(
            #    Decimal(str(10.0 ** -digits)))

        # elif unit_price and (discount or global_discount):
        #    gross_unit_price_wo_round = unit_price / (1 - discount) / (1 - global_discount)
        #    gross_unit_price = gross_unit_price_wo_round.quantize(
        #        Decimal(str(10.0 ** -digits)))

        # if gross_unit_price_wo_round:
        #    digits = self.__class__.gross_unit_price_wo_round.digits[1]
        #    gross_unit_price_wo_round = gross_unit_price_wo_round.quantize(
        #        Decimal(str(10.0 ** -digits)))

        # self.gross_unit_price = gross_unit_price
        # self.gross_unit_price_wo_round = gross_unit_price_wo_round
        self.unit_price = unit_price

    @fields.depends('gross_unit_price', 'global_discount', 'discount',
                    'unit_price')
    def on_change_gross_unit_price(self):
        return self.update_prices()

    @fields.depends('gross_unit_price', 'global_discount', 'discount',
                    'unit_price')
    def on_change_discount(self):
        return self.update_prices()

    @fields.depends('gross_unit_price', 'global_discount', 'discount',
                    'unit_price')
    def on_change_global_discount(self):
        return self.update_prices()

    @fields.depends('gross_unit_price', 'unit_price', 'discount',
                    'global_discount')
    def on_change_product(self):
        super(InvoiceLine, self).on_change_product()
        self.description = ''
        if self.unit_price:
            self.gross_unit_price = self.unit_price
            self.discount = Decimal(0)
            self.global_discount = Decimal(0)
            self.update_prices()
        if not self.discount:
            self.discount = Decimal(0)
        if not self.global_discount:
            self.global_discount = Decimal(0)
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

    @classmethod
    def create(cls, vlist):
        vlist = [x.copy() for x in vlist]
        for vals in vlist:
            if vals.get('type') != 'line':
                continue
            gross_unit_price = (vals.get('unit_price', Decimal('0.0'))
                                or Decimal('0.0'))
            if vals.get('discount') not in (None, 1):
                gross_unit_price = gross_unit_price / (1 - vals['discount'])
            if vals.get('global_discount') not in (None, 1):
                gross_unit_price = gross_unit_price / (
                    1 - vals['global_discount'])
            digits = cls.gross_unit_price.digits[1]
            gross_unit_price = gross_unit_price.quantize(
                Decimal(str(10.0**-digits)))
            vals['gross_unit_price'] = gross_unit_price
            gross_unit_price = gross_unit_price.quantize(
                Decimal(str(10.0**-digits)))
            vals['gross_unit_price'] = gross_unit_price
            if not vals.get('discount'):
                vals['discount'] = Decimal(0)
            if not vals.get('global_discount'):
                vals['global_discount'] = Decimal(0)
        return super(InvoiceLine, cls).create(vlist)

    def _credit(self):
        line = super(InvoiceLine, self)._credit()
        for field in ('gross_unit_price', 'discount', 'global_discount'):
            setattr(line, field, getattr(self, field))
        return line

    def _debit(self):
        '''
        Return debit line.
        '''
        line = self.__class__()
        line.origin = self
        """if self.quantity:
            line.quantity = -self.quantity
        else:"""
        line.quantity = self.quantity

        for field in ('sequence', 'type', 'invoice_type', 'unit_price',
                      'description', 'unit', 'product', 'account'):
            setattr(line, field, getattr(self, field))
        line.taxes = self.taxes
        return line

    def _compute_taxes(self):
        pool = Pool()
        Currency = pool.get('currency.currency')
        TaxLine = pool.get('account.tax.line')

        tax_lines = []
        if self.type != 'line':
            return tax_lines
        taxes = list(self._get_taxes().values())
        for tax in taxes:
            if tax['base'] >= 0:
                # base_code = tax['base_code']
                amount = tax['base'] * 1
            else:
                # base_code = tax['base_code']
                amount = tax['base'] * -1
            # if base_code:
            #     modified_invoice_date = self.invoice.get_modified_document_date(
            #         [self.invoice], self.invoice.number)
            #     if list(modified_invoice_date.values())[0]:
            #         invoice_date = list(modified_invoice_date.values())[0]
            #     else:
            #         invoice_date = self.invoice.currency_date
            #     with Transaction().set_context(date=invoice_date):
            #         amount = Currency.compute(self.invoice.currency,
            #                                   amount, self.invoice.company.currency)
            #     tax_line = TaxLine()
            #     tax_line.code = base_code
            #     tax_line.amount = amount
            #     tax_line.tax = tax['tax']
            #     tax_lines.append(tax_line)
        return tax_lines

    def get_move_lines(self):
        '''
        Overwrite this method to fix a credit note bug
        '''
        pool = Pool()
        Currency = pool.get('currency.currency')
        MoveLine = pool.get('account.move.line')
        if self.type != 'line':
            return []
        line = MoveLine()
        line.description = self.description
        if self.invoice.currency != self.invoice.company.currency:
            modified_invoice_date = self.invoice.get_modified_document_date(
                [self.invoice], self.invoice.number)
            if list(modified_invoice_date.values())[0]:
                invoice_date = list(modified_invoice_date.values())[0]
            else:
                invoice_date = self.invoice.currency_date
            with Transaction().set_context(date=invoice_date):
                CurrencyRates = Pool().get('currency.currency.rate')
                invoice_rate = CurrencyRates.search(
                    [('date', '<=', invoice_date),
                     ('currency', '=', self.invoice.currency),
                     ], order=[('date', 'DESC')], limit=1)
                if invoice_rate:
                    exchange_rate = invoice_rate[0].rate
                else:
                    self.raise_user_error('La fecha %s no tiene tipo de cambio. Ingrese uno.' % str(
                        self.invoice.invoice_date))
                amount = self.invoice.company.currency.round(
                    self.amount/exchange_rate)
                # Currency.compute(self.invoice.currency,
                #                          self.amount, self.invoice.company.currency)
            line.amount_second_currency = self.amount
            line.second_currency = self.invoice.currency
        else:
            amount = self.amount
            line.amount_second_currency = None
            line.second_currency = None
        if amount >= 0:
            if self.invoice.type == 'out':
                line.debit, line.credit = 0, amount
            else:
                line.debit, line.credit = amount, 0
        else:
            if self.invoice.type == 'out':
                line.debit, line.credit = -amount, 0
            else:
                line.debit, line.credit = 0, -amount
        if line.amount_second_currency:
            line.amount_second_currency = (
                line.amount_second_currency.copy_sign(
                    line.debit - line.credit))
        line.account = self.account
        if self.account.party_required:
            line.party = self.invoice.party
        line.tax_lines = self._compute_taxes()
        return [line]


class InvoiceTax(metaclass=PoolMeta):
    __name__ = 'account.invoice.tax'

    def get_move_lines(self):
        '''
        Return a list of move lines instances for invoice tax
        '''
        Currency = Pool().get('currency.currency')
        pool = Pool()
        Currency = pool.get('currency.currency')
        MoveLine = pool.get('account.move.line')
        TaxLine = pool.get('account.tax.line')
        line = MoveLine()
        if not self.amount:
            return []
        line.description = self.description
        if self.invoice.currency != self.invoice.company.currency:
            modified_invoice_date = self.invoice.get_modified_document_date(
                [self.invoice], self.invoice.number)
            if list(modified_invoice_date.values())[0]:
                invoice_date = list(modified_invoice_date.values())[0]
            else:
                invoice_date = self.invoice.currency_date
            with Transaction().set_context(date=invoice_date):
                CurrencyRates = Pool().get('currency.currency.rate')
                invoice_rate = CurrencyRates.search(
                    [('date', '<=', invoice_date),
                     ('currency', '=', self.invoice.currency),
                     ], order=[('date', 'DESC')], limit=1)
                if invoice_rate:
                    exchange_rate = invoice_rate[0].rate
                amount = self.invoice.company.currency.round(
                    self.amount/exchange_rate)
                # amount = Currency.compute(self.invoice.currency, self.amount,
                #                          self.invoice.company.currency)
            line.amount_second_currency = self.amount
            line.second_currency = self.invoice.currency
        else:
            amount = self.amount
            line.amount_second_currency = None
            line.second_currency = None
        if amount >= 0:
            if self.invoice.type == 'out':
                line.debit, line.credit = 0, amount
            else:
                line.debit, line.credit = amount, 0
        else:
            if self.invoice.type == 'out':
                line.debit, line.credit = -amount, 0
            else:
                line.debit, line.credit = 0, -amount
        if line.amount_second_currency:
            line.amount_second_currency = (
                line.amount_second_currency.copy_sign(
                    line.debit - line.credit))
        line.account = self.account
        if self.account.party_required:
            line.party = self.invoice.party
        # if self.tax_code:
        #     tax_line = TaxLine()
        #     tax_line.code = self.tax_code
        #     tax_line.amount = amount * self.tax_sign
        #     tax_line.tax = self.tax
        #     line.tax_lines = [tax_line]
        return [line]

    def _debit(self):
        '''
        Return debit tax.
        '''
        line = self.__class__()
        line.base = self.base
        line.amount = self.amount

        for field in ('description', 'sequence', 'manual', 'account', 'tax'):
            setattr(line, field, getattr(self, field))
        return line


class Move(metaclass=PoolMeta):
    __name__ = 'account.move'

    @classmethod
    def check_modify(cls, *args, **kwargs):
        if Transaction().context.get('draft_invoices', False):
            return
        return super(Move, cls).check_modify(*args, **kwargs)


class InvoiceSequence(ModelSQL, ModelView):
    'Invoice Sequence'
    __name__ = 'account.invoice.sequence'

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
    invoice_type = fields.Selection(
        _TYPE_INVOICE,
        "Tipo de documento",
        select=True,
        required=True
    )
    document_type = fields.Selection(
        _DOCUMENT_TYPE,
        'Tipo de comprobante de pago',
        required=True,
        states={
            'required': ~Eval('type').in_(['out']),
        },
    )
    invoice_sequence = fields.Many2One(
        'ir.sequence.strict',
        'Secuencia',
        required=True,
        domain=[('code', '=', 'account.invoice')],
        context={'code': 'account.invoice'}
    )

    @classmethod
    def __setup__(cls):
        super(InvoiceSequence, cls).__setup__()
        t = cls.__table__()
        cls._sql_constraints += [
            ('period_uniq', Unique(t, t.fiscalyear, t.period, t.invoice_type),
                'Period can be used only once per Invoice Type per Fiscal Year.'),
        ]

    def get_rec_name(self, name):
        type2name = {}
        for type, name in self.fields_get(
                fields_names=['document_type'])['document_type']['selection']:
            type2name[type] = name
        return type2name[self.document_type]

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_invoice_type():
        return 'out_invoice'

    @staticmethod
    def default_document_type():
        return 'simple'


class FiscalYear(metaclass=PoolMeta):
    __name__ = 'account.fiscalyear'

    invoice_sequences = fields.One2Many(
        'account.invoice.sequence',
        'fiscalyear',
        "Secuencias de facturación"
    )


class SunatDocumentObservation(ModelSQL, ModelView):
    '''
    Observations sent by SUNAT
    '''
    __name__ = 'sunat.observation'

    document = fields.Many2One('account.invoice', 'Invoice')
    code = fields.Char(string='Código SUNAT')
    description = fields.Char(string='Descripción SUNAT')


class CreditInvoiceStart(metaclass=PoolMeta):
    'Credit Invoice'
    __name__ = 'account.invoice.credit.start'

    modified_document_reason = fields.Selection(
        _MODIFIED_DOCUMENT_TYPE_CREDIT
        if Eval('document_type').in_(['simple_credit', 'commercial_credit'])
        else _MODIFIED_DOCUMENT_TYPE_DEBIT
        if Eval('document_type').in_(['simple_debit', 'commercial_debit'])
        else [('', '')],
        'Motivo',
        select=True,
        required=True)


class CreditInvoice(metaclass=PoolMeta):
    'Credit Invoice'
    __name__ = 'account.invoice.credit'

    def do_credit(self, action):
        '''Credit wizard method'''
        pool = Pool()
        Invoice = pool.get('account.invoice')
        InvoiceLine = pool.get('account.invoice.line')

        refund = self.start.with_refund
        reason = self.start.modified_document_reason
        invoices = Invoice.browse(Transaction().context['active_ids'])
        credit_amounted = Decimal('0.00')
        modified_document_list = list()
        for invoice in invoices:
            credit_invoices_line = InvoiceLine.search([
                ('origin', 'in', [str(l) for l in invoice.lines]),
            ])
            credit_invoices = [line.invoice for line in credit_invoices_line]
            for credit in credit_invoices:
                if credit.modified_document == invoice.number and\
                    invoice.document_type in credit.document_type and\
                        credit.state in ['posted', 'paid']:
                    modified_document_list.append(credit)
            for modified_invoice in modified_document_list:
                credit_amounted += abs(modified_invoice.total_amount)
            if credit_amounted >= invoice.total_amount:
                self.raise_user_error(
                    'No se puede proceder debido a que ya se abonó'
                    ' la totalidad del monto de la factura {:.2f}'.format(credit_amounted))
        if refund:
            for invoice in invoices:
                if invoice.state != 'posted':
                    self.raise_user_error(
                        'refund_non_posted', (invoice.rec_name,))
                if invoice.payment_lines:
                    self.raise_user_error(
                        'refund_with_payement', (invoice.rec_name,))
                if invoice.type == 'in':
                    self.raise_user_error('refund_supplier', invoice.rec_name)

        credit_invoices = Invoice.credit(
            invoices, refund=refund, reason=reason)

        data = {'res_id': [i.id for i in credit_invoices]}
        if len(credit_invoices) == 1:
            action['views'].reverse()
        return action, data


class InvoiceReport(metaclass=PoolMeta):
    'Invoice Report'
    __name__ = 'account.invoice'

    @classmethod
    def get_context(cls, records, data):
        '''Delete invoice report cache for avoid context problems'''
        Invoice = Pool().get('account.invoice')
        report_context = super(InvoiceReport, cls).get_context(records, data)
        report_context['company'] = report_context['user'].company
        Invoice.write(records, {
            'invoice_report_format': None,
            'invoice_report_cache': None,
        })
        return report_context

    @classmethod
    def execute(cls, ids, data):
        '''Overwrite this method to add context to report'''
        pool = Pool()
        ActionReport = pool.get('ir.action.report')
        Model = pool.get(cls.__name__)
        cls.check_access()
        action_id = data.get('action_id')
        if action_id is None:
            action_reports = ActionReport.search([
                ('report_name', '=', cls.__name__)
            ])
            assert action_reports, '%s not found' % cls
            action_report = action_reports[0]
        else:
            action_report = ActionReport(action_id)

        records = None
        model = action_report.model or data.get('model')
        if model:
            records = Model.search([('id', 'in', ids)])
        report_context = cls.get_context(records, data)
        oext, content = cls.convert(action_report,
                                    cls.render(action_report, report_context))
        if not isinstance(content, str):
            content = bytearray(content) if bytes == str else bytes(content)
        return (oext, content, action_report.direct_print, action_report.name)


class DebitInvoiceStart(ModelView):
    'Debit Invoice'
    __name__ = 'account.invoice.debit.start'

    debit_note_reason = fields.Text('Razón de la Nota de Débito', required=True,
                                    help='Ingrese el motivo por el cuál se esté añadiendo valor a la factura')
    modified_document_reason = fields.Selection(_MODIFIED_DOCUMENT_TYPE_DEBIT
                                                if Eval('document_type').in_(['simple_debit', 'commercial_debit'])
                                                else [('', '')],
                                                'Motivo',
                                                select=True,
                                                required=True)


class DebitInvoice(Wizard):
    'Debit Invoice'
    __name__ = 'account.invoice.debit'
    start = StateView('account.invoice.debit.start',
                      'account_invoice_pe.debit_start_view_form', [
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Debit', 'debit',
                                 'tryton-ok', default=True),
                      ])
    debit = StateAction('account_invoice.act_invoice_form')

    @classmethod
    def __setup__(cls):
        super(DebitInvoice, cls).__setup__()

    def do_debit(self, action):
        """
            make a debit note into invoice by interface. The invoice should to be paid or post stated
        """
        pool = Pool()
        Invoice = pool.get('account.invoice')

        # refund = self.start.with_refund
        invoices = Invoice.browse(Transaction().context['active_ids'])

        for invoice in invoices:
            if invoice.sunat_document_type in ['08', '07']:
                self.raise_user_error(
                    'No se puede modificar a un documento que ya modifica por una nota de credito o debito')
            if invoice.state in ['draft', 'validated']:
                self.raise_user_error(
                    'No puede crear un nota de débito a una factura no contabilizada o pagada')

        reason = self.start.modified_document_reason
        debit_note_reason = self.start.debit_note_reason

        debit_invoices = Invoice.debit(
            invoices, reason=reason, debit_note_reason=debit_note_reason)
        data = {'res_id': [i.id for i in debit_invoices]}
        if len(debit_invoices) == 1:
            action['views'].reverse()
        return action, data


class VoidedDocumentStart(ModelView):
    'voided Invoice'
    __name__ = 'account.invoice.voided.start'

    reason = fields.Char('Razón de baja', required=True)


class VoidedDocument(Wizard):
    'voided Invoice'
    __name__ = 'account.invoice.voided'
    start = StateView('account.invoice.voided.start',
                      'account_invoice_pe.voided_start_view_form', [
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Dar de Baja', 'voided',
                                 'tryton-ok', default=True),
                      ])
    voided = StateAction('account_invoice.act_invoice_form')

    @classmethod
    def __setup__(cls):
        super(VoidedDocument, cls).__setup__()

    def do_voided(self, action):
        """
            make a voided document into invoice by interface.
        """
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Date = pool.get('ir.date')
        today = Date.today()

        # refund = self.start.with_refund
        invoices = Invoice.browse(Transaction().context['active_ids'])
        reason = self.start.reason
        for invoice in invoices:
            if invoice.type == 'in':
                invoice.raise_user_error(
                    'Solo es posible dar de baja comprobantes de Cliente')
            if invoice.state == 'voided':
                invoice.raise_user_error(
                    'El comprobante ya fue dado de baja')
            if invoice.state != 'posted':
                invoice.raise_user_error(
                    'Solo es posible dar de baja un comprobante contabilizada')
            if invoice.sunat_response_code != '0':
                invoice.raise_user_error(
                    'No puede dar de baja un comprobante no Aceptado por SUNAT')
            if (today - (invoice.sunat_date_generated).date()).days >= 8:
                invoice.raise_user_error(
                    'El plazo máximo para dar de baja un comprobante son 7 días')
        voided_invoices = Invoice.voided(invoices, reason)
        data = {'res_id': [i.id for i in voided_invoices]}
        if len(voided_invoices) == 1:
            action['views'].reverse()
        return action, data


class CanceledDocumentStart(ModelView):
    'canceled Invoice'
    __name__ = 'account.invoice.canceled.start'


class CanceledDocument(Wizard):
    'canceled Invoice'
    __name__ = 'account.invoice.canceled'
    start = StateView('account.invoice.canceled.start',
                      'account_invoice_pe.cancel_start_view_form', [
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Anular', 'canceled',
                                 'tryton-ok', default=True),
                      ])
    canceled = StateAction('account_invoice.act_invoice_form')

    @classmethod
    def __setup__(cls):
        super(CanceledDocument, cls).__setup__()

    def do_canceled(self, action):
        """
            make a canceled document into invoice by interface.
        """
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Date = pool.get('ir.date')
        today = Date.today()

        invoices = Invoice.browse(Transaction().context['active_ids'])
        for invoice in invoices:
            if invoice.state == 'posted':
                invoice.state = 'anulado'
                invoice.save()
            else:
                if invoice.state in ['draft', 'validated']:
                    invoice.raise_user_error('No puede anular un comprobante no contabilizado')
                elif invoice.state == 'paid':
                    invoice.raise_user_error('Para anular un comprobante pagado, utilice la acción "Anular Pagos"')
                elif invoice.state == 'cancel':
                    invoice.raise_user_error('No puede anular un comprobante cancelado')
                elif invoice.state == 'anulado':
                    invoice.raise_user_error('El comprobante ya se encuentra anulado')
                else:
                    invoice.raise_user_error('El comprobante no puede ser anulado')

        return 'end'



