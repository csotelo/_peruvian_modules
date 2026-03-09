# -*- coding: utf-8 -*-
# This file is part of the account_sunat_pe module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool
from trytond.pyson import Eval, If
from trytond.report import Report
from trytond.transaction import Transaction
from trytond.wizard import Button, StateReport, StateView, Wizard
from collections import OrderedDict
from decimal import Decimal

__all__ = ['BalanceSheet',
           'BalanceSheetWizard',
           'BalanceSheetReport',
           'BalanceSumsWizard',
           'BalanceSumsReport']


class BalanceSheet(ModelView):
    """The balance sheet class(Balance General)"""

    __name__ = 'balance.sheet'

    fiscalyear = fields.Many2One(
        'account.fiscalyear',
        'Fiscalyear',
        required=True,
        domain=[
            ('company', '=', Eval('company', -1)),
        ],
        depends=['company']
    )
    start_period = fields.Many2One('account.period', 'Start Period',
                                   domain=[
                                       ('fiscalyear', '=', Eval('fiscalyear')),
                                       ('start_date', '<=',
                                        (Eval('end_period'), 'start_date')),
                                   ], depends=['fiscalyear', 'end_period'])
    end_period = fields.Many2One('account.period', 'End Period',
                                 domain=[
                                     ('fiscalyear', '=', Eval('fiscalyear')),
                                     ('start_date', '>=',
                                      (Eval('start_period'), 'start_date'))
                                 ],
                                 depends=['fiscalyear', 'start_period'])
    company = fields.Many2One(
        'company.company',
        'Company',
        required=True,
        domain=[
            ('id', If(Eval('context', {}).contains('company'), '=', '!='),
                Eval('context', {}).get('company', -1)),
        ],
        select=True
    )

    @staticmethod
    def default_company():
        return Transaction().context.get('company')


class BalanceSheetWizard(Wizard):
    """The balance sheet wizard class"""

    __name__ = 'balance.sheet.wizard'

    start = StateView(
        'balance.sheet',
        'account_pe.balance_sheet_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Generar Reporte', 'sheet_',
                   'tryton-ok'),
        ])

    sheet_ = StateReport(
        'balance.sheet.report'
    )

    def do_sheet_(self, action):
        """Send a report action and a dict with the report data"""
        return action, {
            'id': action['action'],
            'company': self.start.company.id,
            'fiscalyear': self.start.fiscalyear.id,
            'start_period': self.start.start_period.id if self.start.start_period else None,
            'end_period': self.start.end_period.id if self.start.end_period else None,
        }


class BalanceSheetReport(Report):
    """The balance sheet report class"""

    __name__ = 'balance.sheet.report'

    @classmethod
    def get_context(cls, records, data):
        """Add to context all the accounts for the report"""
        report_context = super(
            BalanceSheetReport, cls).get_context(records, data)
        pool = Pool()
        Account_ = pool.get('account.general_ledger.account')
        Period = pool.get('account.period')
        for period in ['start_period', 'end_period']:
            if data.get(period):
                Transaction().context[period] = Period(data[period])
            else:
                Transaction().context[period] = None

        # Activo corriente
        caja = Account_.search([('code', '=', '10')])[0]
        valores_neg = Account_.search([('code', '=', '11')])[0]
        ccporcobrar = Account_.search([('code', '=', '12')])[0]
        ccvinculadas = Account_.search([('code', '=', '13')])[0]
        otrascc = Account_.search([('code', '=', '14')])[0]
        existencias = Account_.search([('code', '=', '28')])[0]
        anticipados = Account_.search([('code', '=', '18')])[0]
        act_corr_list = [caja, valores_neg, ccporcobrar,
                         ccvinculadas, otrascc, existencias, anticipados]
        i = 1
        total_act_corr = Decimal('0.00')
        for account in act_corr_list:
            start_balance = Account_.get_account([account], 'start_balance')
            end_balance = Account_.get_account([account], 'end_balance')
            balance = start_balance[account.id] + end_balance[account.id]
            report_context['ac' + str(i)] = balance
            total_act_corr += balance
            i += 1
        report_context['total_act_corr'] = total_act_corr

        # Activo No Corriente
        cc_largo_plazo = Account_.search([('code', '=', '16')])[0]
        cc_vinculadas_largo_plazo = Account_.search([('code', '=', '17')])[0]
        otras_cc_largo_plazo = Account_.search([('code', '=', '19')])[0]
        inversiones = Account_.search([('code', '=', '31')])[0]
        inmuebles = Account_.search([('code', '=', '33')])[0]
        intangibles = Account_.search([('code', '=', '34')])[0]
        impuesto_renta_part = Account_.search([('code', '=', '371')])[0]
        otros_activos = Account_.search([('code', '=', '38')])[0]

        i = 1
        total_act_no_corr = Decimal('0.00')
        act_no_corr_list = [cc_largo_plazo, cc_vinculadas_largo_plazo, otras_cc_largo_plazo,
                            inversiones, inmuebles, intangibles, impuesto_renta_part, otros_activos]
        for account in act_no_corr_list:
            start_balance = Account_.get_account([account], 'start_balance')
            end_balance = Account_.get_account([account], 'end_balance')
            balance = start_balance[account.id] + end_balance[account.id]
            report_context['anc' + str(i)] = balance
            total_act_no_corr += balance
            i += 1
        report_context['total_act_no_corr'] = total_act_no_corr

        # Pasivo Corriente
        pagares = Account_.search([('code', '=', '45')])[0]
        ccxpagar = Account_.search([('code', '=', '42')])[0]
        ccxpagar_vinc = Account_.search([('code', '=', '43')])[0]
        otras_ccxpagar = Account_.search([('code', '=', '44')])[0]
        partecorriente = Account_.search([('code', '=', '45')])[0]
        i = 1
        total_pas_corr = Decimal('0.00')
        pas_corr_list = [pagares, ccxpagar,
                         ccxpagar_vinc, otras_ccxpagar, partecorriente]
        for account in pas_corr_list:
            start_balance = Account_.get_account([account], 'start_balance')
            end_balance = Account_.get_account([account], 'end_balance')
            balance = start_balance[account.id] + end_balance[account.id]
            report_context['pc' + str(i)] = balance
            total_pas_corr += balance
            i += 1
            report_context['total_pas_corr'] = total_pas_corr

        # Pasivo no Corriente

        ccxpagar_largo = Account_.search([('code', '=', '46')])[0]
        ccxpagar_largo_vinc = Account_.search([('code', '=', '47')])[0]
        ingresos_diferidos = Account_.search([('code', '=', '49')])[0]
        renta_pasiva = Account_.search([('code', '=', '491')])[0]

        contingencias = Account_.search([('code', '=', '48')])[0]
        interes_minoritario = Account_.search([('code', '=', '491')])[0]

        i = 1
        total_pas_no_corr = Decimal('0.00')
        total_others = Decimal('0.00')
        pas_no_corr_list = [
            ccxpagar_largo, ccxpagar_largo_vinc, ingresos_diferidos, renta_pasiva]
        others = [contingencias, interes_minoritario]
        for account in pas_no_corr_list:
            start_balance = Account_.get_account([account], 'start_balance')
            end_balance = Account_.get_account([account], 'end_balance')
            balance = start_balance[account.id] + end_balance[account.id]
            report_context['pnc' + str(i)] = balance
            total_pas_no_corr += balance
            i += 1
        for account in others:
            start_balance = Account_.get_account([account], 'start_balance')
            end_balance = Account_.get_account([account], 'end_balance')
            balance = start_balance[account.id] + end_balance[account.id]
            report_context['pnc' + str(i)] = balance
            total_others += balance
            i += 1
        report_context['total_pas_no_corr'] = total_pas_no_corr

        # Patrimonio Neto
        capital = Account_.search([('code', '=', '50')])[0]
        capital_adicional = Account_.search([('code', '=', '52')])[0]
        acciones_inversion = Account_.search([('code', '=', '51')])[0]
        excedentes_reval = Account_.search([('code', '=', '57')])[0]
        reservas_legales = Account_.search([('code', '=', '58')])[0]
        otras_reservas = Account_.search([('code', '=', '589')])[0]
        result_acum = Account_.search([('code', '=', '59')])[0]

        pat_net_list = [capital, capital_adicional, acciones_inversion,
                        excedentes_reval, reservas_legales, otras_reservas, result_acum]
        i = 1
        total_patrimonio = Decimal('0.00')
        for account in pat_net_list:
            start_balance = Account_.get_account([account], 'start_balance')
            end_balance = Account_.get_account([account], 'end_balance')
            balance = start_balance[account.id] + end_balance[account.id]
            report_context['p' + str(i)] = balance
            total_patrimonio += balance
            i += 1
        report_context['total_patrimonio'] = total_patrimonio

        report_context['total_activo'] = total_act_corr + total_act_no_corr
        report_context['total_pasivo'] = total_pas_corr + total_pas_no_corr
        report_context['patpluspasiv'] = total_pas_corr + \
            total_pas_no_corr + total_patrimonio

        Company = Pool().get('company.company')
        company = Company(Transaction().context['company'])

        report_context['company'] = company

        return report_context


class BalanceSumsWizard(Wizard):
    """The balance sums wizard class"""

    __name__ = 'balance.sums.wizard'

    start = StateView(
        'balance.sheet',
        'account_pe.balance_sheet_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Generar Reporte', 'sheet_',
                   'tryton-ok'),
        ])

    sheet_ = StateReport(
        'balance.sums.report'
    )

    def do_sheet_(self, action):
        """Send a report action and a dict with the report data"""
        return action, {
            'id': action['action'],
            'company': self.start.company.id,
            'fiscalyear': self.start.fiscalyear.id,
            'start_period': self.start.start_period.id if self.start.start_period else None,
            'end_period': self.start.end_period.id if self.start.end_period else None,
        }


class BalanceSumsReport(Report):
    """The balance sums report class"""

    __name__ = 'balance.sums.report'

    @classmethod
    def get_context(cls, records, data):
        """Add to context all the accounts for the report"""
        report_context = super(
            BalanceSumsReport, cls).get_context(records, data)
        Account_ = Pool().get('account.account')
        accounts_codes = ['101', '104', '12', '1421', '191', '20', '25', '30', '366', '33', '39', '40', '41',
                          '42', '46', '50', '59', '601', '603', '611', '613', '62', '63', '64', '65', '68',
                          '691', '701', '709', '73', '74', '75', '78', '79', '94', '95']
        accounts = Account_.search([('code', 'in', accounts_codes)])
        entries_dict = dict()
        adjust_rows_debit = cls.get_adjust_rows(accounts)[0]
        adjust_rows_credit = cls.get_adjust_rows(accounts)[1]
        inven_rows_debit = cls.get_inven_rows(accounts)[0]
        inven_rows_credit = cls.get_inven_rows(accounts)[1]
        result_nat_lose = cls.get_result_nat(accounts)[0]
        result_nat_gain = cls.get_result_nat(accounts)[1]
        result_func_lose = cls.get_result_func(accounts)[0]
        result_func_gain = cls.get_result_func(accounts)[1]
        for account in accounts:
            balance = account.debit - account.credit
            if balance >= Decimal('0'):
                balance_de = abs(balance)
                balance_acre = None
            else:
                balance_acre = abs(balance)
                balance_de = None
            entries_dict[account.code] = [account.code,
                                          account.name, account.debit, account.credit, balance_de, balance_acre]
        report_context['data'] = entries_dict
        report_context['accounts'] = accounts
        report_context['accounts_codes'] = accounts_codes
        report_context['adjust_debit'] = adjust_rows_debit
        report_context['adjust_credit'] = adjust_rows_credit
        report_context['inven_debit'] = inven_rows_debit
        report_context['inven_credit'] = inven_rows_credit
        report_context['result_nat_lose'] = result_nat_lose
        report_context['result_nat_gain'] = result_nat_gain
        report_context['result_func_lose'] = result_func_lose
        report_context['result_func_gain'] = result_func_gain
        report_context['sum'] = cls.sum
        report_context['major'] = cls.major_number

        return report_context

    @classmethod
    def get_adjust_rows(cls, accounts):
        """Returns the balance of adjust entries"""
        pool = Pool()
        Account_ = pool.get('account.account')
        adjust_rows_debit = dict()
        adjust_rows_credit = dict()
        for account in accounts:
            balance = account.debit - account.credit
            if account.code in ['611', '691', '78', '79', '94', '95']:
                if account.code == '611':
                    account691 = Account_.search([('code', '=', '691')])
                    debit = account691[0].debit - account691[0].credit
                    adjust_rows_debit[account.code] = abs(debit)
                    adjust_rows_credit[account.code] = None
                elif account.code == '691':
                    adjust_rows_credit[account.code] = abs(balance)
                    adjust_rows_debit[account.code] = None
                elif account.code in ['78', '79', '94', '95']:
                    if balance >= Decimal('0'):
                        adjust_rows_credit[account.code] = abs(balance)
                        adjust_rows_debit[account.code] = None
                    elif balance < Decimal('0'):
                        adjust_rows_debit[account.code] = abs(balance)
                        adjust_rows_credit[account.code] = None
            else:
                adjust_rows_debit[account.code] = None
                adjust_rows_credit[account.code] = None

        return [adjust_rows_debit, adjust_rows_credit]

    @classmethod
    def get_inven_rows(cls, accounts):
        """Add inventory entries"""
        pool = Pool()
        Account_ = pool.get('account.account')
        inven_rows_debit = dict()
        inven_rows_credit = dict()
        for account in accounts:
            balance = account.debit - account.credit
            if account.code in ['101', '104', '12', '1421', '191', '20', '25',
                                '30', '366', '33', '39', '40', '41', '42', '46', '50', '59']:
                if balance >= Decimal('0'):
                    inven_rows_debit[account.code] = abs(balance)
                    inven_rows_credit[account.code] = None
                elif balance < Decimal('0'):
                    inven_rows_debit[account.code] = None
                    inven_rows_credit[account.code] = abs(balance)
            else:
                inven_rows_debit[account.code] = None
                inven_rows_credit[account.code] = None

        return [inven_rows_debit, inven_rows_credit]

    @classmethod
    def get_result_nat(cls, accounts):
        """Add natural results entries"""
        pool = Pool()
        Account_ = pool.get('account.account')
        result_nat_lose = dict()
        result_nat_gain = dict()
        for account in accounts:
            balance = account.debit - account.credit
            if account.code in ['601', '603', '62', '63', '64', '65', '68',  '701', '709', '73', '74', '75']:
                if balance >= Decimal('0'):
                    result_nat_lose[account.code] = abs(balance)
                    result_nat_gain[account.code] = None
                if balance < Decimal('0'):
                    result_nat_lose[account.code] = None
                    result_nat_gain[account.code] = abs(balance)
            elif account.code == '611':
                data1 = cls.get_adjust_rows([account])
                result = balance - data1[0]['611']
                if result < Decimal('0'):
                    result_nat_gain[account.code] = abs(result)
                    result_nat_lose[account.code] = None
                else:
                    result_nat_gain[account.code] = None
                    result_nat_lose[account.code] = abs(result)
            else:
                result_nat_lose[account.code] = None
                result_nat_gain[account.code] = None
        return [result_nat_lose, result_nat_gain]

    @classmethod
    def get_result_func(cls, accounts):
        """Add functional results entries"""
        pool = Pool()
        Account_ = pool.get('account.account')
        result_func_lose = dict()
        result_func_gain = dict()
        for account in accounts:
            balance = account.debit - account.credit
            if account.code in ['691', '701', '709', '73', '74', '75', '94', '95']:
                if balance >= Decimal('0'):
                    result_func_lose[account.code] = abs(balance)
                    result_func_gain[account.code] = None
                else:
                    result_func_lose[account.code] = None
                    result_func_gain[account.code] = abs(balance)
            else:
                result_func_lose[account.code] = None
                result_func_gain[account.code] = None

        return [result_func_lose, result_func_gain]

    @classmethod
    def sum(cls, accounts, data, index):
        """Sums between balances"""
        result = Decimal('0.00')
        for account in accounts:
            if data[account.code] != None:
                if type(data[account.code]) == list:
                    if data[account.code][index] != None:
                        result += data[account.code][index]
                else:
                    result += data[account.code]
        return result

    @classmethod
    def major_number(cls, a, b):
        """Compare two numbers and returns the major"""
        if a >= b:
            return a
        else:
            return b
