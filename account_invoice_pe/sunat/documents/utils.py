from .invoice import SunatInvoice
from .credit_note import SunatNote
from .debit_note import SunatDebitNote
from .voided_document import VoidedDocument


class DocumentFactory(object):
    @staticmethod
    def get_document(document):
        document_type = document.sunat_document_type
        void = document.void_status
        if void:
            return VoidedDocument(document)
        else:
            if document_type == '03' or document_type == '01':
                return SunatInvoice(document)
            elif document_type == '07':
                return SunatNote(document)
            elif document_type == '08':
                return SunatDebitNote(document)


# SUNAT_DOCUMENT_TYPE = {
#     '': '',
#     '01': 'FACTURA ELECTRÓNICA',
#     '03': 'BOLETA DE VENTA',
#     '07': 'NOTA DE CRÉDITO',
#     '08': 'NOTA DE DÉBITO',
# }