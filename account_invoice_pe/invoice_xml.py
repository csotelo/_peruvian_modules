# This file is part product_barcode_label module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import os

from trytond.config import config
from trytond.model import ModelView, fields
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.wizard import Button, StateView, Wizard
from trytond.modules.account_invoice_pe.sunat.documents import DocumentFactory
from trytond.error import UserError

sunat_invoicing_path = config.get('account_invoice', 'sunat_invoicing')
if not sunat_invoicing_path or len(sunat_invoicing_path) == 0:
    sunat_invoicing_path = '.'

__all__ = ['InvoiceXMLModel', 'InvoiceXMLWizard']


class InvoiceXMLModel(ModelView):
    'Invoice XML Model'
    __name__ = 'account.invoice.xml.model'
    label = fields.Binary('Archivo', filename='filename')
    filename = fields.Char('Ruta')


class InvoiceXMLWizard(Wizard):
    'Invoice XML Wizard'
    __name__ = 'account.invoice.xml.wizard'

    start = StateView('account.invoice.xml.model',
                      'account_invoice_pe.invoice_xml_view_form', [
                          Button('Done', 'end', 'tryton-ok', default=True),
                      ])

    def default_start(self, name):
        '''Show the invoice xml file'''
        pool = Pool()
        Invoice = pool.get('account.invoice')

        invoice, = Invoice.browse([Transaction().context['active_id']])

        document = DocumentFactory.get_document(invoice)
        document_name = document.filename

        filepath = os.path.join(
            sunat_invoicing_path,
            'signed',
            invoice.invoice_date.strftime('%Y%m%d'),
            document_name)

        document_path = '%s.xml' % filepath
        try:
            with open(document_path, 'rb') as file_p:
                label = fields.Binary.cast(file_p.read())
        except IOError:
            raise UserError('No encontrado')
        except:
            raise UserError('Error desconocido')
        default = {}
        default['label'] = label
        default['filename'] = '%s.xml' % filepath
        return default
