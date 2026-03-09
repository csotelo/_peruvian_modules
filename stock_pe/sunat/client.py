'''
Sunat Soap client
'''

from zeep import Client, Transport
from zeep.exceptions import Fault as RequestException
from zeep.wsse.username import UsernameToken
from os import path

from . import BASE_PATH


class SoapClient(Client):
    def __init__(self, wsdl=None, wsse=None, production=False, timeout=3):
        _wsdl = ''
        if wsdl is None:
            _wsdl = 'https://e-beta.sunat.gob.pe/ol-ti-itemision-guia-gem-beta/billService?wsdl'
        else:
            _wsdl = wsdl

        if production:
            _wsdl = 'https://e-guiaremision.sunat.gob.pe/ol-ti-itemision-guia-gem/billService?wsdl'

        if wsse == None:
            raise AttributeError('Authenticate yoself.')
        else:
            _wsse = wsse

        transport = Transport(timeout=timeout)

        super(SoapClient, self).__init__(
            wsdl=_wsdl, wsse=_wsse, transport=transport)