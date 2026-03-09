# -*- coding: utf-8 -*-
from trytond.pool import PoolMeta
from trytond.model import fields
from trytond.pyson import Bool, Eval

class Carrier(metaclass=PoolMeta):
    'Carrier'
    __name__ = 'carrier'

    is_private = fields.Boolean('Privado')

    driver_license = fields.Char(
        'Licencia de conducir',
        states = {
            'invisible': (
                Bool(~Eval('is_private'))
            ),
            'required': (
                Bool(Eval('is_private')) 
            )
        }
    )
    
    vehicle_plate = fields.Char(
        'Placa de vehículo',
        states = {
            'invisible': (
                Bool(~Eval('is_private'))
            ),
            'required': (
                Bool(Eval('is_private')) 
            )
        }
    )

    vehicle_brand = fields.Char(
        'Marca de vehículo',
        states = {
            'invisible': (
                Bool(~Eval('is_private'))
            ),
            'required': (
                Bool(Eval('is_private')) 
            )
        }
    )
