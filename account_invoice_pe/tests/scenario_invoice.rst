================
Invoice Scenario
================

Imports::
    >>> import datetime
    >>> import time
    >>> from datetime import datetime as time
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from operator import attrgetter
    >>> from proteus import Model, Wizard
    >>> from trytond.tests.tools import activate_modules
    >>> from trytond.modules.account_invoice_pe.tests.tools import create_company, \
    ...     get_company, set_fiscalyear_invoice_sequences
    >>> from trytond.modules.account.tests.tools import create_fiscalyear, \
    ...     create_chart, get_accounts, create_tax, create_tax_code
    >>> from trytond.modules.account_invoice_pe.sunat.documents.document import Document
    >>> today = datetime.date.today()
    >>> current_time = time.now().time()

Install account_invoice::

    >>> config = activate_modules('account_invoice_pe')

Create company::

    >>> _ = create_company()
    >>> company = get_company()
    >>> tax_identifier = company.party.identifiers.new()
    >>> tax_identifier.type = 'pe_vat'
    >>> tax_identifier.code = '20101010101'
    >>> company.invoicing_email_sender = u'fsdsd'    
    >>> company.invoicing_mode = 'development'
    >>> company.party.save()

Create fiscal year::

    >>> fiscalyear = set_fiscalyear_invoice_sequences(
    ...     create_fiscalyear(company))
    >>> fiscalyear.click('create_period')
    >>> period = fiscalyear.periods[0]

Create chart of accounts::

    >>> _ = create_chart(company)
    >>> accounts = get_accounts(company)
    >>> receivable = accounts['receivable']
    >>> revenue = accounts['revenue']
    >>> expense = accounts['expense']
    >>> account_tax = accounts['tax']
    >>> account_cash = accounts['cash']

Create tax::

    >>> TaxCode = Model.get('account.tax.code')
    >>> tax = create_tax(Decimal('.10'))
    >>> tax.save()
    >>> invoice_base_code = create_tax_code(tax, 'base', 'invoice')
    >>> invoice_base_code.save()
    >>> invoice_tax_code = create_tax_code(tax, 'tax', 'invoice')
    >>> invoice_tax_code.save()
    >>> credit_note_base_code = create_tax_code(tax, 'base', 'credit')
    >>> credit_note_base_code.save()
    >>> credit_note_tax_code = create_tax_code(tax, 'tax', 'credit')
    >>> credit_note_tax_code.save()

Create payment method::

    >>> Journal = Model.get('account.journal')
    >>> PaymentMethod = Model.get('account.invoice.payment.method')
    >>> Sequence = Model.get('ir.sequence')
    >>> journal_cash, = Journal.find([('type', '=', 'cash')])
    >>> payment_method = PaymentMethod()
    >>> payment_method.name = 'Cash'
    >>> payment_method.journal = journal_cash
    >>> payment_method.credit_account = account_cash
    >>> payment_method.debit_account = account_cash
    >>> payment_method.save()

Create Write Off method::

    >>> WriteOff = Model.get('account.move.reconcile.write_off')
    >>> sequence_journal, = Sequence.find([('code', '=', 'account.journal')])
    >>> journal_writeoff = Journal(name='Write-Off', type='write-off',
    ...     sequence=sequence_journal)
    >>> journal_writeoff.save()
    >>> writeoff_method = WriteOff()
    >>> writeoff_method.name = 'Rate loss'
    >>> writeoff_method.journal = journal_writeoff
    >>> writeoff_method.credit_account = expense
    >>> writeoff_method.debit_account = expense
    >>> writeoff_method.save()

Create party::

    >>> Party = Model.get('party.party')
    >>> Identifier = Model.get('party.identifier')
    >>> identifier_type = 'pe_vat'
    >>> identifier_code = '20101013101'
    >>> identifiers = Identifier(type=identifier_type, code=identifier_code)
    >>> party = Party(name='Dunder Mifflin', identifiers=[identifiers])
    >>> party.save()

Create product::

    >>> ProductUom = Model.get('product.uom')
    >>> unit, = ProductUom.find([('name', '=', 'Unit')])
    >>> ProductTemplate = Model.get('product.template')
    >>> Product = Model.get('product.product')
    >>> product = Product()
    >>> template = ProductTemplate()
    >>> template.name = 'product'
    >>> template.default_uom = unit
    >>> template.type = 'service'
    >>> template.list_price = Decimal('40')
    >>> template.cost_price = Decimal('25')
    >>> template.account_expense = expense
    >>> template.account_revenue = revenue
    >>> template.customer_taxes.append(tax)
    >>> template.save()
    >>> product.template = template
    >>> product.save()

Create payment term::

    >>> PaymentTerm = Model.get('account.invoice.payment_term')
    >>> payment_term = PaymentTerm(name='Term')
    >>> line = payment_term.lines.new(type='percent', ratio=Decimal('.5'))
    >>> delta = line.relativedeltas.new(days=20)
    >>> line = payment_term.lines.new(type='remainder')
    >>> delta = line.relativedeltas.new(days=40)
    >>> payment_term.save()

Create strict sequence for invoice sequence::

    >>> SequenceStrict = Model.get('ir.sequence.strict')
    >>> inv_seq = SequenceStrict(name=fiscalyear.name, code='account.invoice', company=fiscalyear.company, prefix='001-')

Create invoice sequence::

    >>> InvoiceSequence = Model.get('account.invoice.sequence')
    >>> invoice_sequence = InvoiceSequence()
    >>> invoice_sequence.fiscalyear = fiscalyear
    >>> invoice_sequence.company = company
    >>> invoice_sequence.document_type = 'commercial'
    >>> invoice_sequence.invoice_type = 'out_invoice'
    >>> invoice_sequence.invoice_sequence = fiscalyear.out_invoice_sequence
    >>> invoice_sequence.save()

Create invoice::

    >>> Invoice = Model.get('account.invoice')
    >>> InvoiceLine = Model.get('account.invoice.line')
    >>> invoice = Invoice()
    >>> invoice.party = party
    >>> invoice.number = '0001-001'
    >>> invoice.invoice_date = today
    >>> invoice.invoice_duedate = today
    >>> invoice.invoice_time = current_time
    >>> invoice.payment_term = payment_term
    >>> invoice.state = 'draft'
    >>> line = InvoiceLine()
    >>> invoice.lines.append(line)
    >>> line.product = product
    >>> line.quantity = 5
    >>> line.unit_price = Decimal('40')
    >>> line = InvoiceLine()
    >>> invoice.lines.append(line)
    >>> line.account = revenue
    >>> line.description = 'Test'
    >>> line.quantity = 1
    >>> line.unit_price = Decimal(20)
    >>> line.unit = unit
    >>> invoice.untaxed_amount
    Decimal('220.00')
    >>> invoice.tax_amount
    Decimal('20.00')
    >>> invoice.total_amount
    Decimal('240.00')
    >>> invoice.save()

Test change tax::

    >>> tax_line, = invoice.taxes
    >>> tax_line.tax == tax
    True
    >>> tax_line.tax = None
    >>> tax_line.tax = tax

Post invoice::

    >>> invoice.click('post')
    >>> invoice.state
    'posted'
    >>> invoice.tax_identifier.code
    'BE0897290877'
    >>> invoice.untaxed_amount
    Decimal('220.00')
    >>> invoice.tax_amount
    Decimal('20.00')
    >>> invoice.total_amount
    Decimal('240.00')
    >>> receivable.reload()
    >>> receivable.debit
    Decimal('240.00')
    >>> receivable.credit
    Decimal('0.00')
    >>> revenue.reload()
    >>> revenue.debit
    Decimal('0.00')
    >>> revenue.credit
    Decimal('220.00')
    >>> account_tax.reload()
    >>> account_tax.debit
    Decimal('0.00')
    >>> account_tax.credit
    Decimal('20.00')
    >>> with config.set_context(periods=period_ids):
    ...     invoice_base_code = TaxCode(invoice_base_code.id)
    ...     invoice_base_code.amount
    Decimal('200.00')
    >>> with config.set_context(periods=period_ids):
    ...     invoice_tax_code = TaxCode(invoice_tax_code.id)
    ...     invoice_tax_code.amount
    Decimal('20.00')
    >>> with config.set_context(periods=period_ids):
    ...     credit_note_base_code = TaxCode(credit_note_base_code.id)
    ...     credit_note_base_code.amount
    Decimal('0.00')
    >>> with config.set_context(periods=period_ids):
    ...     credit_note_tax_code = TaxCode(credit_note_tax_code.id)
    ...     credit_note_tax_code.amount
    Decimal('0.00')

Check SUNAT states::

    >>> invoice.sunat_document_type
    '01'
    >>> invoice.document_type
    'commercial'
    >>> invoice.sunat_serial_prefix
    'F'
    >>> invoice.sunat_serial
    '0001'
    >>> invoice.sunat_number
    '001'
    >>> invoice.sunat_invoice_status
    'rejected'