# -*- coding: utf-8 -*-
"""
    tests/__init__.py

    :copyright: (c) 2018 by Grupo ConnectTix SAC
    :license: see LICENSE for more details.
"""
try:
    from trytond.modules.sale_pe.tests.test_views_depends import suite
except ImportError:
    from .test_views_depends import suite

__all__ = ['suite']
