# -*- coding: utf-8 -*-
from trytond.pool import Pool

from .sale_pe import *
from .sale_reports import *
from .invoice import *
from .pending_pay import *

"""
    __init__.py

    :copyright: (c) 2020 by Grupo ConnectTix SAC
    :license: see LICENSE for details.
"""


def register():
    Pool.register(
        Sale,
        SaleLine,
        SunatPLESales,
        SunatPLEMainView,
        SunatPLESalesView,
        SaleDetailed,
        SaleDetailedView,
        Invoice,
        PendingPayView,
        PendingPayAccumulatedView,
        module='sale_pe', type_='model'
    )
    Pool.register(
        PLEReport,
        PLEReportSales,
        PLEReportSalesPlain,
        PLEReportSalesSpread,
        SaleDetailedReport,
        SaleReportCondensend,
        PendingPayReport,
        PendingPayAccumulatedReport,
        module='sale_pe', type_='report'
    )
    Pool.register(
        SunatPLESalesWizard,
        SaleDetailedWizard,
        PendingPayWizard,
        PendingPayAccumulatedWizard,
        module='sale_pe', type_='wizard'
    )
