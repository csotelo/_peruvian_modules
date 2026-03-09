from .invoice import SunatInvoice
from .invoice import Renderer as DocumentRenderer
from genshi.template import MarkupTemplate
from .document import _DOCUMENT_TYPE
from .document import DOCUMENT_XML_TYPE
from .document import TAXES
from datetime import date


class VoidedDocument(SunatInvoice):
    def __init__(self, document_object):
        if document_object is None:
            raise AttributeError('Document#_meta no puede ser None')
        self._meta = document_object
        header_xml_filename = 'voided_document.xml'
        line_xml_filename = 'invoice_line.xml'
        # tax_xml_filename = 'invoice_tax.xml'
        self._xml_header_template = self._load_xml_template(
            file_name=header_xml_filename)
        self._xml_line_template = self._load_xml_template(
            file_name=line_xml_filename)
        # self._xml_tax_template = self._load_xml_template(
        #     file_name=tax_xml_filename)

    @property
    def filename(self):
        return '{ruc}-RA-{generated_date}-{invoice_number}'.format(
            ruc=self.document.company.ruc.zfill(11),
            generated_date=date.today().strftime('%Y%m%d'),
            invoice_number=self.document.sunat_number.lstrip('0')
        )

    def render(self):
        return Renderer().render_document(self)


class Renderer(DocumentRenderer):

    def __init__(self):
        super(Renderer, self).__init__()

    def render_document(self, document):
        result = ''

        meta = document.document
        lines = list()
        for line_number in range(0, 1):
            line = meta
            lines.append(
                self.render_line(document, line, line_number + 1) or dict())

        result += self.render_header(document, lines)

        return result.encode('iso-8859-1')


    def render_header(self, document, lines):
        data = self._prepare_header(document, lines)
        return MarkupTemplate(
            document.xml_header_template).generate(document=data).render()
    
    def render_line(self, document, line, line_order):
        return self._prepare_line(document, line, line_order)

    def _prepare_header(self, document, lines):
        meta = document.document
        _lines = lines
        header = {
            'ID': 'RA-' + date.today().strftime('%Y%m%d') +'-'+ meta.sunat_number.lstrip('0'),
            'company_ruc': meta.company.ruc,
            'reference_date': meta.invoice_date if meta.invoice_date else date.today(),
            'generated_date': date.today(),
            'identification': meta.company.party.name,
            'SignatureID': 'IDSignKG',
            'SignatureIDPartyIdentification': meta.company.ruc,
            'SignatureIDPartyName': meta.company.party.full_name,
            'AccountingSupplierPartyID': meta.company.ruc,
            'AccountingSupplierPartyTypeId': _DOCUMENT_TYPE[meta.company.party.document_type],
            'Lines': _lines
        }
        return header

    def _prepare_line(self, document, line, order_id):
        meta = document.document
        line = {
            'order_id': order_id,
            'document_type': meta.sunat_document_type,
            'document_serial': meta.sunat_serial_prefix + meta.sunat_serial,
            'document_correlative': meta.sunat_number.lstrip('0'),
            'reason': meta.void_reason
        }
        return line
