from .invoice import SunatInvoice
from .invoice import Renderer as DocumentRenderer


class SunatNote(SunatInvoice):
    def __init__(self, document_object):
        super(SunatNote, self).__init__(document_object)

    def render(self):
        return Renderer().render_document(self)

class Renderer(DocumentRenderer):
    def __init__(self):
        super(Renderer, self).__init__()

    def _prepare_header(self, document, lines, taxes):
        meta = document.document
        result = super(Renderer, self)._prepare_header(document, lines, taxes)
        result['InvoiceTypeCode'] = meta.modified_document_reason
        return result

