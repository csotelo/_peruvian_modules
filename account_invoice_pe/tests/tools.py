# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from proteus import Model
from proteus import Model, Wizard
from proteus.config import get_config
from trytond.modules.currency.tests.tools import get_currency

__all__ = ['set_fiscalyear_invoice_sequences']


def set_fiscalyear_invoice_sequences(fiscalyear, config=None):
    "Set invoice sequences to fiscalyear"
    SequenceStrict = Model.get('ir.sequence.strict', config=config)

    invoice_seq = SequenceStrict(name=fiscalyear.name, code='account.invoice',
        company=fiscalyear.company)
    invoice_seq.save()
    fiscalyear.out_invoice_sequence = invoice_seq
    fiscalyear.in_invoice_sequence = invoice_seq
    fiscalyear.out_credit_note_sequence = invoice_seq
    fiscalyear.in_credit_note_sequence = invoice_seq
    return fiscalyear


def create_payment_term(config=None):
    "Create a direct payment term"
    PaymentTerm = Model.get('account.invoice.payment_term')

    payment_term = PaymentTerm(name='Direct')
    payment_term.lines.new(type='remainder')
    return payment_term


def create_company(party=None, currency=None, config=None):
    "Create the company using the proteus config"
    Party = Model.get('party.party', config=config)
    User = Model.get('res.user', config=config)
    Identifier = Model.get('party.identifier', config=config)

    company_config = Wizard('company.company.config')
    company_config.execute('company')
    company = company_config.form
    if not party:
        identifier_type = 'pe_vat'
        identifier_code = '20101010101'
        identifiers = Identifier(type=identifier_type, code=identifier_code)
        party = Party(name='Dunder Mifflin', identifiers=[identifiers])
        party.save()
    company.party = party
    if not currency:
        currency = get_currency()
    company.currency = currency
    company.password = 'x'
   
    company_config.execute('add')

    if not config:
        config = get_config()
    config._context = User.get_preferences(True, {})
    return company_config


def get_company(config=None):
    "Return the only company"
    Company = Model.get('company.company', config=config)
    company, = Company.find()
    return company
