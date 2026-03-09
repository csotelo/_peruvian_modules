# -*- coding: utf-8 -*-
""".. module:: account.py.

    :plataform: Independent
    :synopsis: Accountant module for tryton
.. moduleauthor: Carlos Eduardo Sotelo Pinto <carlos.sotelo.pinto@gmail.com>
.. copyright: (c) 2017
.. organization: Tryton - PE
.. license: GPL v3.
"""

from trytond.model import fields
from trytond.pool import PoolMeta
from trytond.pyson import Eval

__all__ = ['Account', 'Move']


class Move(metaclass=PoolMeta):
    __name__ = 'account.move'

    move_type = fields.Selection([
        ('move', 'Movimiento'),
        ('open', 'Apertura'),
        ('close', 'Cierre'),
    ], 'Tipo de Asiento', required=True, select=True,
        states={'readonly': Eval('state') == 'posted'})

    @staticmethod
    def default_move_type():
        return 'move'


class Account(metaclass=PoolMeta):
    __name__ = 'account.account'

    @classmethod
    def __setup__(cls):
        super(Account, cls).__setup__()
