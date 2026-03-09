from trytond.modules.account_invoice_pe.sunat.documents.document import Document

class SunatTicket(Document):
    def __init__(self, ticket_object):
        super(SunatTicket, self).__init__(ticket_object)
