# -*- coding: utf-8 -*-
"""
.. module:: account_invoice_pe.party
    :plataform: Independent
    :synopsis: Party module models
.. moduleauthor: Carlos Eduardo Sotelo Pinto <carlos.sotelo@connecttix.pe>
.. copyright: (c) 2018
.. organization: Grupo ConnectTix SAC
.. license: GPL v3.
"""

from trytond.pool import Pool, PoolMeta

__all__ = [
    'Party',
]


class Party(metaclass=PoolMeta):
    __name__ = 'party.party'

    def get_invoicing_address(self, name):
        for address in self.addresses:
            if address:
                country = ""
                subdivision = ""
                province = ""
                district = ""
                if address.subdivision:
                    subdivision = address.subdivision.name
                if address.country:
                    country = address.country.name
                if address.province:
                    province = address.province.name
                if address.district:
                    district = address.district.name
                return "{street}, {district}, {province}, {subdivision}, {country}".format(
                    street=address.street,
                    district=district,
                    province=province,
                    subdivision=subdivision,
                    country=country
                )
        return ""


    @staticmethod
    def default_customer_payment_term():
        payment_term = Pool().get('account.invoice.payment_term').search([
            ('active', '=', True),
            ('is_customer_payment_term_default', '=', True)
        ], limit = 1)
        if payment_term:
            return payment_term[0].id


    @staticmethod
    def default_supplier_payment_term():
        payment_term = Pool().get('account.invoice.payment_term').search([
            ('active', '=', True),
            ('is_supplier_payment_term_default', '=', True)
        ], limit = 1)
        if payment_term:
            return payment_term[0].id

