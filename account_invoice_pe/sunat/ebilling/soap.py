'''
Sunat Soap client
'''

from zeep import Client
from zeep.wsse.username import UsernameToken
from os import path

from trytond.modules.account_invoice_pe.sunat import BASE_PATH


class SoapClient(Client):
    def __init__(self, wsdl=None, wsse=None, production=False):
        _wsdl = ''
        if wsdl is None:
            _wsdl = BASE_PATH + '/ebilling/sunat_beta.wsdl'
        else:
            _wsdl = wsdl
        if production:
            _wsdl = BASE_PATH + '/ebilling/sunat_prod.wsdl'

        if wsse == None:
            raise AttributeError('Authenticate yoself.')
        else:
            _wsse = wsse

        super(SoapClient, self).__init__(wsdl=_wsdl, wsse=_wsse)