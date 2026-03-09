import os
from decimal import Decimal
from genshi.template import MarkupTemplate

from .document import Document, DocumentRenderer
from .document import _DOCUMENT_TYPE
from .document import DOCUMENT_XML_TYPE
from .document import TAXES


class SunatInvoice(Document):
    def __init__(self, invoice_object):
        super(SunatInvoice, self).__init__(invoice_object)

    @property
    def filename(self):
        return "%s-%s-%s%s-%s" % (
            self.document.company.ruc.zfill(11),
            self.document.sunat_document_type.zfill(2),
            self.document.sunat_serial_prefix,
            self.document.sunat_serial.zfill(3),
            self.document.sunat_number.zfill(8),
        )

    def render(self):
        return Renderer().render_document(self)

    def write_document(self, document, path='.', on_success=None, on_failure=None):
        meta = document.document
        path = os.path.join(
            path,
            'generated',
            meta.invoice_date.strftime('%Y%m%d')
        )
        super(SunatInvoice, self).write_document(
            document, path, on_success=on_success, on_failure=on_failure)

    def delete_document(self, document, path='.'):
        meta = document.document
        gen_path = os.path.join(
            path,
            'generated',
            meta.invoice_date.strftime('%Y%m%d')
        )
        sig_path = os.path.join(
            path,
            'signed',
            meta.strftime('%Y%m%d')
        )
        super(SunatInvoice, self).delete_document(
            document, generated_path=gen_path, signed_path=sig_path)


class Renderer(DocumentRenderer):
    def __init__(self):
        super(Renderer, self).__init__()

    def render_document(self, document):
        result = ''

        meta = document.document

        lines = list()
        for line_number in range(0, len(meta.lines)):
            line = meta.lines[line_number]
            lines.append(
                self.render_line(document, line, line_number + 1) or dict())

        payment_terms = self.render_payment_terms(document)

        taxes = list()
        for tax_line in TAXES:
            for tax in meta.taxes:
                line = self.render_tax(document, tax_line, tax)
                if line is None:
                    continue
                taxes.append(line)

        result += self.render_header(document, lines, taxes, payment_terms)

        return result.encode('iso-8859-1')

    def render_header(self, document, lines, taxes, payment_terms):
        data = self.prepare_header(document, lines, taxes, payment_terms)
        return MarkupTemplate(
            document.xml_header_template).generate(document=data).render()

    def render_line(self, document, line, line_order):
        if line is None or line.product is None:
            return
        return self._prepare_line(document, line, line_order)

    def render_payment_terms(self, document):
        payment_terms = {
            'PaymentTerm': 'cash',
            'PaymentDates': []
        }
        
        """
        1. Determinar si las fechas de factura y fecha de due date son distintas
        2. Si las fechas son las mismas es contado, si las fechas son distintas es crédito
        2.1. Pago al contado
        2.1.1. En Genshi usar choose para renderizar etiqueta de pago al contado
        2.2. Pago al crédito
        2.2.1. Obtener listado de fechas de pago
        2.2.2. En Genshi usar Choose para rederizar pagos al crédito
        2.2.3. Hace un loop para las fechas de pago y renderizar el xml

        Tareas
        1. Revisar Chooose de Genshi [https://pythonhosted.org/Genshi/xml-templates.html]
        2. Revisar Loo for en Genshi [https://pythonhosted.org/Genshi/xml-templates.html]
        3. Revisar punto 1.
        4. Revisar 2, 2.1 y 2.2
        5. Revisar 2.2.1, 2.2.2, 2.2.3
        
        """
        if document.document.invoice_date != document.document.invoice_duedate:
            payment_terms['PaymentTerm'] = 'credit'
            payment_terms['PaymentDates'] = document.document.payment_term.compute(
                document.document.total_amount,
                document.document.currency,
                document.document.invoice_date
            )
            print(payment_terms)
        return payment_terms
    
    

    def render_tax(self, document, line_tax, tax):
        return self._render_taxes_delegate(document, line_tax, tax)

    def prepare_header(self, document, lines, taxes, payment_terms):
        meta = document.document
        _lines = lines
        _taxes = taxes
        _payment_terms = payment_terms
        if 'encode' in dir(lines):
            _lines = lines.encode('iso-8859-1')
        if 'encode' in dir(taxes):
            _taxes = taxes.encode('iso-8859-1')

        header = {
            'DocumentType': DOCUMENT_XML_TYPE[document.document_type_code],
            'DocumentCurrencyCode': meta.currency.code,
            'PayableAmount1001': '{0:.2f}'.format(meta.untaxed_amount
                                                  * document.mult),
            'PayableAmount1002': '{0:.2f}'.format(0.0),
            'PayableAmount1003': '{0:.2f}'.format(0.0),
            'PayableAmount1004': '{0:.2f}'.format(0.0),
            'PayableAmount1005': '{0:.2f}'.format(meta.total_amount
                                                  * document.mult),
            'PayableAmount1000': "SON %s" % meta.amount_in_letters,
            'ID': document.serial_number,
            'ModifiedDocumentID': meta.origins.split()[0] if meta.origins else '',
            'ModifiedDocumentDocumentType': document.modified_document_type,
            'ModifiedDocumentDocumentReason': meta.modified_document_reason,
            'IssueDate': meta.invoice_date,
            'IssueTime': '{0:%H:%M:%S}'.format(meta.invoice_time),
            'IssueDueDate': meta.invoice_duedate,
            'InvoiceTypeCode': meta.sunat_document_type,
            'SignatureID': 'IDSignKG',
            'SignatureIDPartyIdentification': meta.company.ruc,
            'SignatureIDPartyName': meta.company.party.full_name,
            'AccountingSupplierPartyID': meta.company.ruc,
            'AccountingSupplierPartyTypeId':
            # TODO where is the document_type set
            _DOCUMENT_TYPE[meta.company.party.document_type or ''],
            'AccountingSupplierPartyName': meta.company.party.full_name,
            'AccountingSupplierPartyPostalCode': meta.company.party.address_get().zip,
            'AccountingSupplierPartyAddress': meta.company.party.address_get().street,
            'AccountingSupplierBuildingNumber': meta.company.party.address_get().name,
            'AccountingSupplierPartyCityName': meta.company.party.address_get().city,
            'AccountingSupplierCountrySubentity': meta.company.party.address_get().subdivision.name if meta.company.party.address_get().subdivision else '',
            'AccountingSupplierPartyDistrict': meta.company.party.address_get().district.name if meta.company.party.address_get().district else '',
            'AccountingSupplierPartyCountryCode': meta.company.party.address_get().country.code if meta.company.party.address_get().country else '',
            'AccountingSupplierPartyRegistrationName': meta.company.party.full_name,
            'AccountingCustomerPartyID': meta.party.document_number.strip() or
            ' ',
            'AccountingCustomerPartyTypeID':
            _DOCUMENT_TYPE[meta.party.document_type or ''],
            'AccountingCustomerPartyRegistrationName': meta.party.full_name,
            'AccountingCustomerPartyPostalCode': meta.party.address_get().zip or '00000',
            'AccountingCustomerPartyAddress': meta.party.address_get().street,
            'AccountingCustomerPartyCity': meta.party.address_get().city,
            'AccountingCustomerPartyCountrySubentity': meta.party.address_get().subdivision.name if meta.party.address_get().subdivision else '',
            'AccountingCustomerPartyCountryCode': meta.party.address_get().country.code if meta.party.address_get().country else '',
            'LegalMonetaryTotalLineExtensionAmount': '{0:.2f}'.format(
                meta.untaxed_amount * document.mult),
            'LegalMonetaryTotalAllowanceTotalAmount': '{0:.2f}'.format(
                meta.global_discount * document.mult if meta.global_discount else 0),
            'LegalMonetaryTotalChargeTotalAmount': '{0:.2f}'.format(
                float(meta.global_discount * document.mult if meta.global_discount else '0.0')),
            'LegalMonetaryTotalPrepaidAmount': '{0:.2f}'.format(0.0),
            'LegalMonetaryTotalPayableAmount': '{0:.2f}'.format(
                meta.total_amount * document.mult),
            'PaymentTerm':  _payment_terms['PaymentTerm'],
            'PaymentDates': _payment_terms['PaymentDates'],
            'InvoiceTaxes': _taxes,
            'InvoiceLines': _lines,

        }
        sanity_header = sanitatize(header)
        return sanity_header

    def _prepare_line(self, document, line, order_id):
        meta = document.document
        line = {
            'DocumentCurrencyCode': meta.currency.code,
            'InvoiceLineID': order_id,
            'InvoiceLineQuantity': line.quantity * document.mult,
            'InvoiceLineExtensionAmount': '{0:.2f}'.format(float(line.unit_price) * float(line.quantity) * document.mult),
            'InvoiceLineFreeOfChargeIndicator': 'false',
            'InvoiceLinePriceAmount': '{0:.2f}'.format(
                line.unit_price * Decimal(1.18)),
            'InvoiceLinePriceTypeCode': '01',
            'InvoiceLineChargeIndicator': 'true',
            'InvoiceLineAmount': '{0:.2f}'.format(line.amount * document.mult),
            'InvoiceLineTaxableAmount': '{0:.2f}'.format(
                float(line.unit_price) * float(line.quantity) * document.mult),
            'InvoiceLineTaxAmount': '{0:.2f}'.format(
                float(line.unit_price) * float(line.quantity) * 0.18 * document.mult),
            'InvoiceLineTaxAmountPercent': '18.00',
            'InvoiceLineTaxCategory': '10',
            'InvoiceLineItemDescription': line.description if line.description else line.product.name,
            'InvoiceLineItemID': (line.product.code).strip() if (line.product.code).strip() else line.id,
            'InvoiceLineItemPriceAmount': '{0:.2f}'.format(line.unit_price),
            'AllowanceChargeMultiplierFactor': line.quantity,
            'AllowanceChargeAmount': '{0:.2f}'.format(line.discount * document.mult),
            'AllowanceChargeBaseAmount': '{0:.2f}'.format(line.amount * document.mult)
        }
        return sanitatize(line)

    def _render_taxes_delegate(self, document, line_tax, tax):
        meta = document.document

        if tax in meta.taxes and tax.tax.name == line_tax[2]:
            tax_amount = meta.tax_amount
            tax_subtotal = meta.tax_amount
        else:
            return

        if meta.sunat_document_type == '07' and tax_amount == 0.0:
            return

        taxes = {
            'DocumentCurrencyCode': meta.currency.code,
            'TaxTotalCategory': 'S',
            'TaxTotal': '{0:.2f}'.format(tax_amount * document.mult),
            'TaxableSubTotal': '{0:0.2f}'.format(float(tax_subtotal * document.mult)/0.18),
            'TaxSubTotal': '{0:.2f}'.format(tax_subtotal * document.mult),
            'TaxTotalID': line_tax[0],
            'TaxTotalName': line_tax[2],
            'TaxTotalTaxTypeCode': line_tax[1],
        }
        return sanitatize(taxes)


def sanitatize(di):
    for key, value in di.items():
        if type(value) in (str, str):
            value = value.strip()
            value = value.replace("\n", "")
            di[key] = value
    return di
