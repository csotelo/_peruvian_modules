# -*- coding: utf-8 -*-
# This file is part product_barcode_label module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from trytond.pool import PoolMeta, Pool
from trytond.transaction import Transaction
from trytond.config import config
from trytond.exceptions import UserWarning

ebilling_status = config.get('account_invoice', 'debug')


__all__ = []


class InvoiceDebug(metaclass=PoolMeta):
    'Invoice Debug'

    __name__ = 'account.invoice'

    @classmethod
    def __setup__(cls):
        super(InvoiceDebug, cls).__setup__()
        cls._error_messages.update({
            'ebilling_incongruence': (
                'El modo de facturación de la configuración es '
                '%s es, pero en el sistema es '
                '%s'),
        })
        
    @classmethod
    def compare_debug(cls, debug_conf, debug_local):
        if debug_conf != debug_local:
            cls.raise_user_warning('incongruence', 'ebilling_incongruence', (debug_conf, debug_local))

    @classmethod
    def post(cls, invoices):
        '''Overwrite this method to add a user warning when the debug
        flag are set in a diferent way'''

        pool = Pool()
        Company = pool.get('company.company')
        company = Company(Transaction().context['company'])
        local_ebilling_status = company.invoicing_mode
        cls.compare_debug(ebilling_status, local_ebilling_status)
        super(InvoiceDebug, cls).post(invoices)
