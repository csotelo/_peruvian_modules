# -*- coding: utf-8 -*-
# This file is part of the account_invoice_ar module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

import base64
from io import BytesIO

import requests
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import PoolMeta

__all__ = ['Company']


class Company(metaclass=PoolMeta):
    __name__ = 'company.company'

    logo = fields.Binary(
        "Logotipo"
    )
    ruc = fields.Function(
        fields.Char(
            "RUC",
        ),
        'get_ruc'
    )
    fiscal_address = fields.Function(
        fields.Char(
            "Dirección fiscal"
        ),
        'get_fiscal_address'
    )
    commercial_address = fields.Function(
        fields.Char(
            "Dirección comercial"
        ),
        'get_commercial_address'
    )
    website = fields.Function(
        fields.Char(
            "Website"
        ),
        'get_website'
    )
    email = fields.Function(
        fields.Char(
            "E-Mail"
        ),
        'get_email'
    )
    phone = fields.Function(
        fields.Char(
            "Teléfono"
        ),
        'get_phone'
    )
    fax = fields.Function(
        fields.Char(
            "Fax"
        ),
        'get_fax'
    )
    sol_username = fields.Char(
        "Usuario",
        help="Nombre de usuario para la clave SOL"
    )
    sol_password = fields.Char(
        "Contraseña",
        help="Contraseña para la clave SOL"
    )
    password = fields.Function(
        fields.Char(
            "Contraseña"
        ),
        getter='get_password',
        setter='set_password'
    )
    invoicing_email_sender = fields.Char(
        "Emisor de correo electrónico",
        help="Dirección de correo eletrónico para la emisión de la "
        "factura eletrónica"
    )
    invoicing_email_receiver = fields.Char(
        "Receptor de correo electrónico",
        help="Dirección de correo eletrónico para la recepción de la "
        "factura eletrónica"
    )
    sunat_certificate = fields.Text(
        "Certificado CRT",
        help="Certificado digital (.crt) de la empresa"
    )
    sunat_private_key = fields.Text(
        "Clave Privada",
        help="Clave Privada (.key) de la empresa"
    )
    invoicing_mode = fields.Selection(
        [
            ('', 'n/a'),
            ('production', "Producción"),
            ('development', "Desarrollo"),
        ],
        "Modo de certificación"
    )
    invoicing_resolution = fields.Char(
        "Resolución SUNAT"
    )
    invoicing_website = fields.Char(
        "Sitio Web de factura electrónica"
    )
    detraction_account = fields.Char(
        "Cuenta de detracciones"
    )
    second_currency = fields.Many2One('currency.currency', "Segunda Moneda",
                                      ondelete='CASCADE',)

    @classmethod
    def __setup__(cls):
        super(Company, cls).__setup__()

    @staticmethod
    def default_invoicing_mode():
        return ''

    @staticmethod
    def default_detraction_account():
        return '00-000-000000'

    def get_ruc(self, name):
        if len(self.party.identifiers) > 0:
            for identifier in self.party.identifiers:
                if identifier.type == 'pe_vat':
                    return identifier.code
        return ''

    def get_fiscal_address(self, name):
        if self.party.invoicing_address:
            return self.party.invoicing_address
        return ''

    def get_commercial_address(self, name):
        if self.party.invoicing_address:
            return self.party.invoicing_address
        return ''

    def get_website(self, name):
        if len(self.party.contact_mechanisms) > 0:
            for contact_mechanism in self.party.contact_mechanisms:
                if contact_mechanism.type == 'website':
                    return contact_mechanism.value
        return ''

    def get_email(self, name):
        if len(self.party.contact_mechanisms) > 0:
            for contact_mechanism in self.party.contact_mechanisms:
                if contact_mechanism.type == 'email':
                    return contact_mechanism.value
        return ''

    def get_phone(self, name):
        if len(self.party.contact_mechanisms) > 0:
            for contact_mechanism in self.party.contact_mechanisms:
                if contact_mechanism.type == 'phone':
                    return contact_mechanism.value
        return ''

    def get_fax(self, name):
        if len(self.party.contact_mechanisms) > 0:
            for contact_mechanism in self.party.contact_mechanisms:
                if contact_mechanism.type == 'fax':
                    return contact_mechanism.value

        return ''

    def get_password(self, name):
        return 'x' * 10

    @classmethod
    def set_password(cls, invoices, name, value):
        if value == 'x' * 10:
            return
        to_write = []
        for invoice in invoices:
            to_write.extend([
                [invoice],
                {
                    'sol_password': base64.b64encode(
                        value.encode('utf-8')
                    ).decode('utf-8'),
                }
            ])
        cls.write(*to_write)
