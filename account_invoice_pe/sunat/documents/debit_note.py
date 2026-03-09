from .invoice import SunatInvoice
from .invoice import Renderer as DocumentRenderer


class SunatDebitNote(SunatInvoice):
    """make a debit note """

    def __init__(self, document_object):
        super(SunatDebitNote, self).__init__(document_object)
    
    def render(self):
        """render a debit note"""
        return Renderer().render_document(self)


class Renderer(DocumentRenderer):
    """ class to render debit note"""

    def __init__(self):
        super(Renderer, self).__init__()

    def _prepare_header(self, document, lines, taxes):
        """make a header of debit note"""
        meta = document.document
        result = super(Renderer, self)._prepare_header(document, lines, taxes)
        result['InvoiceTypeCode'] = meta.modified_document_reason
        result['ReasonDescription'] = meta.debit_note_reason
        return result

