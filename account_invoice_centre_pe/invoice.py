# -*- coding: utf-8 -*-



from collections import defaultdict

from trytond.model import fields, ModelView
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateTransition


__all__ = [
    'Invoice',
    'InvoicePaymentLine',
    'InvoiceSequence',
]

__metaclass__ = PoolMeta

_DEPENDS = ['state']


class InvoiceSequence(metaclass=PoolMeta):
    'Invoice Sequence'
    __name__ = 'account.invoice.sequence'


class Invoice(metaclass=PoolMeta):
    'Invoice'
    __name__ = 'account.invoice'

    invoicing_centre_statement = fields.Many2One(
        'account.invoice.centre.statement',
        'Diario de Centro facturación',
        ondelete='RESTRICT'
    )

    """"currency_rate_paid = fields.Numeric(u'Tipo de cambio')"""

    def pay_invoice(self, amount, statement, date, description,
                    amount_second_currency=None, second_currency=None, operation_number=None):
        '''
        Adds a payment of amount to an invoice using the journal, date and
        description.
        Returns the payment line.'''
        pool = Pool()
        PaymentLine = pool.get('account.invoice-account.move.line')
        InvoiceCentreStatement = pool.get('account.invoice.centre.statement')
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
        line2.account = getattr(statement, payment_account).current(date=date)
        
        # if self.account == line2.account:
        #     self.raise_user_error('same_%s' % account_journal, {
        #         'journal': journal.rec_name,
        #         'invoice': self.rec_name,
        #     })
        # if not line2.account:
        #     self.raise_user_error('missing_%s' % account_journal,
        #                           (statement.rec_name,))

        for line in lines:
            if line.account.party_required:
                line.party = self.party
            if amount_second_currency:
                line.amount_second_currency = amount_second_currency.copy_sign(
                    line.debit - line.credit)
                line.second_currency = second_currency

        period_id = Period.find(self.company.id, date=date)

        move = Move(journal=statement.journal, period=period_id, date=date,
                origin=self, description=description, company=self.company, lines=lines)
        move.save()
        Move.post([move])

        for line in move.lines:
            if line.account == self.account:
                self.add_payment_lines({self: [line]})
        
        payment_lines = PaymentLine.search([
            ('invoice', '=', self.id),
            ('line', '=', line.id),
        ])

        if len(payment_lines) == 1:
            payment_line = payment_lines[0]
            invoice_centre_statement = InvoiceCentreStatement.get_current_process()
            if not invoice_centre_statement.invoicing_centre.can_pay:
                self.raise_user_error(
                    "El centro de facturación no esta habilitado para registrar pagos")
            payment_line.invoice_centre_statement = invoice_centre_statement.id
            payment_line.save()

        return line
        raise Exception('Missing account')

    @classmethod
    def set_number(cls, invoices):
        '''
        Set number to invoice
        '''
        Sequence = Pool().get('ir.sequence.strict')
        InvoiceCentreSequence = Pool().get(
            'account.invoice.centre-account.invoice.sequence')
        InvoiceCentreStatement = Pool().get('account.invoice.centre.statement')
        Date = Pool().get('ir.date')

        for invoice in invoices:
            date = invoice.invoice_date or Date.today()

            if not invoice.document_type:
                cls.raise_user_error(
                    "No se ha definido un tipo de comprobante"
                )
                
            # Validación entre el Comprobante de pago y Tipo de documento SUNAT
            if invoice.sunat_document_type is not None:
                if invoice.document_type == 'commercial' and invoice.sunat_document_type != '01':
                    cls.raise_user_error("El Tipo de documento SUNAT no coincide con el Comprobante de pago seleccionado") 
                elif invoice.document_type == 'simple' and invoice.sunat_document_type != '03':
                    cls.raise_user_error("El Tipo de documento SUNAT no coincide con el Comprobante de pago seleccionado") 
                elif invoice.document_type in ['commercial_credit', 'simple_credit']\
                    and invoice.sunat_document_type != '07':
                        cls.raise_user_error("El Tipo de documento SUNAT no coincide con el Comprobante de pago seleccionado") 
                elif invoice.document_type in ['commercial_debit', 'simple_debit'] \
                    and invoice.sunat_document_type != '08':
                        cls.raise_user_error("El Tipo de documento SUNAT no coincide con el Comprobante de pago seleccionado") 
             
            if invoice.state in {'posted', 'paid'}:
                continue

            if not invoice.tax_identifier:
                invoice.tax_identifier = invoice.get_tax_identifier()

            if invoice.invoice_type == 'electronic' and invoice.number:
                continue

            if invoice.document_type == 'commercial':
                invoice.sunat_document_type = '01'
            elif invoice.document_type == 'simple':
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

            invoicing_centre_statement = InvoiceCentreStatement.get_current_process()
            invoice_sequences = InvoiceCentreSequence.search([
                ('sequence.invoice_type', '=', invoice_type),
                ('sequence.document_type', '=', invoice.document_type),
                ('centre', '=', invoicing_centre_statement.invoicing_centre)
            ])
            invoice.invoicing_centre_statement = invoicing_centre_statement.id
            if not invoicing_centre_statement.invoicing_centre.can_post:
                cls.raise_user_error(
                    "El centro de facturación no esta habilitado para emitir comprobantes de pago")

            if len(invoice_sequences) == 0:
                cls.raise_user_error(
                    "No se ha hallado un número de secuencia válido")

            invoice_sequence = invoice_sequences[0].sequence
            period = invoice_sequence.period
            if invoice.invoice_type == 'electronic' and invoice.type == 'out' and period and not (period.start_date <= date and
                               period.end_date >= date):
                cls.raise_user_error(
                    "No se ha hallado un periodo fiscal valido")

            fiscalyear = invoice_sequence.fiscalyear
            if invoice.invoice_type == 'electronic' and invoice.type == 'out' and fiscalyear and not (fiscalyear.start_date <= date and
                                   fiscalyear.end_date >= date):
                cls.raise_user_error(
                    "No se ha hallado un ejercicio fiscal valido")

            with Transaction().set_context(date=Date.today()):
                if not invoice.number:
                    number = Sequence.get_id(
                        invoice_sequence.invoice_sequence.id)
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
                    dateAmount=invoice.payment_term.compute(
                        invoice.total_amount,
                        invoice.currency,
                        invoice.invoice_date
                    )
                    #Tuple of date,amount
                    finaldate = dateAmount[0][0]        
                    invoice.invoice_duedate = finaldate

                #VERIFICA QUE SEA A CREDITO

                if not invoice.invoice_date and invoice.type == 'out':
                    invoice.invoice_date = Date.today()
                if not invoice.invoice_time and invoice.type == 'out':
                    invoice.invoice_time = Date.time()
                if not invoice.invoice_duedate and invoice.type == 'out':
                    dateAmount=invoice.payment_term.compute(
                        invoice.total_amount,
                        invoice.currency,
                        invoice.invoice_date
                    )
                    #Tuple of date,amount
                #for i in dateAmount:
                #    finaldate = dateAmount[0][i]        
                #    invoice.invoice_duedate = finaldate
                #asigna diversas final due dates 
        cls.save(invoices)

    @classmethod
    @ModelView.button
    def nullify_einvoice(cls, invoices):
        '''Delete reconcile and create a cancel move. Add the cancel moves to payment lines
           of invoice'''
        pool = Pool()
        Move = pool.get('account.move')
        Line = pool.get('account.move.line')
        Reconciliation = pool.get('account.move.reconciliation')
        InvoiceCentreStatement = pool.get('account.invoice.centre.statement')
        PaymentLine = pool.get('account.invoice-account.move.line')
        for invoice in invoices:
            if invoice.state != 'paid':
                cls.raise_user_error(
                    'No se pueden anular los pagos de una factura no pagada')
            payment_lines = [
                x for x in invoice.payment_lines if invoice.payment_lines]
            moves = [x.move for x in payment_lines if payment_lines]
            str_moves = [str(move) for move in moves if moves]
            cancel_moves = Move.search([
                ('origin', 'in', str_moves)
            ])
            alredy_cancel_moves = [
                x.origin for x in cancel_moves if cancel_moves] + cancel_moves
            for move in moves:
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
                        payment_lines = PaymentLine.search([
                            ('line', 'in', lines)
                        ])
                    if payment_lines:
                        line_to_add = list()
                        for line in cancel_move.lines:
                            if line.reconciliation:
                                line_to_add.append(line)
                            if line_to_add:
                                cls.write([invoice], {
                                    'payment_lines': [('add', [line_to_add[0].id])],
                                })
                        for l in invoice.payment_lines:
                            invoice_line_list = PaymentLine.search(
                                [('invoice', '=', invoice), ('line', '=', l.id)])
                            invoice_line = invoice_line_list[0]
                            if not invoice_line.invoice_centre_statement:
                                invoice_line.invoice_centre_statement = InvoiceCentreStatement.get_current_process().id
                                invoice_line.save()
        cls.write(invoices, {
            'state': 'posted',
        })


class InvoicePaymentLine(metaclass=PoolMeta):
    'Invoice - Payment Line'
    __name__ = 'account.invoice-account.move.line'

    invoice_centre_statement = fields.Many2One(
        'account.invoice.centre.statement',
        'Diario de centro de facturación'
    )


class CancelMoves(Wizard):
    'Cancel Moves'
    __name__ = 'account.move.cancel'

    def transition_cancel(self):
        pool = Pool()
        Move = pool.get('account.move')
        Line = pool.get('account.move.line')
        PaymentLines = pool.get('account.invoice-account.move.line')
        Invoice = pool.get('account.invoice')
        InvoiceCentreStatement = pool.get('account.invoice.centre.statement')

        moves = Move.browse(Transaction().context['active_ids'])
        for move in moves:
            default = self.default_cancel(move)
            cancel_move = move.cancel(default=default)
            to_reconcile = defaultdict(list)
            payment_lines = None
            for line in move.lines + cancel_move.lines:
                if line.account.reconcile:
                    to_reconcile[(line.account, line.party)].append(line)
            for lines in to_reconcile.values():
                Line.reconcile(lines)
                payment_lines = PaymentLines.search([
                    ('line', 'in', lines)
                ])
            if payment_lines:
                line_to_add = list()
                origin = payment_lines[0].invoice
                for line in cancel_move.lines:
                    if line.reconciliation:
                        line_to_add.append(line)
                    Invoice.write([origin], {
                        'payment_lines': [('add', [line_to_add[0].id])],
                    })
                for l in origin.payment_lines:
                    invoice_line_list = PaymentLines.search(
                        [('invoice', '=', origin), ('line', '=', l.id)])
                    invoice_line = invoice_line_list[0]
                    if not invoice_line.invoice_centre_statement:
                        invoice_line.invoice_centre_statement = InvoiceCentreStatement.get_current_process().id
                        invoice_line.save()
        return 'end'


class NullifyMoves(Wizard):
    'Unreconcile Lines'
    __name__ = 'account.move.nullify'
    start_state = 'nullify'
    nullify = StateTransition()

    def transition_nullify(self):
        Invoice = Pool().get('account.invoice')
        invoices = Invoice.browse(Transaction().context['active_ids'])
        Invoice.nullify_einvoice(invoices)
        return 'end'
