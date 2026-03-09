# -*- coding: utf-8 -*-
"""
.. module:: stock_pe
    :plataform: Independent
    :synopsis: Stock module models
.. moduleauthor: Connecttix
.. copyright: (c) 2019
.. organization: Tryton-PE
.. license: GPL v3.
"""
import base64
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction

from .ebilling import DespatchAdvice, DespatchLine, UsernameToken
from trytond.wizard import Wizard, StateTransition, StateView, Button, StateAction

_SUNAT_DOCUMENT_TYPE = [
    ('', ''),
    ('09', 'GUÍA DE REMISIÓN REMITENTE'),
    ('31', 'GUÍA DE REMISIÓN TRANSPORTISTA'),
    ('71', 'GUÍA DE REMISIÓN REMITENTE COMPLEMENTARIA'),
    ('72', 'GUÍA DE REMISIÓN TRANSPORTISTA COMPLEMENTARIA'), ]

_TYPE_DOCUMENT = [
    ('sale_despatch_advice', 'Guía de remisión (venta)'),
    ('internal_despatch_advice', 'Guía de remisión (interno)'),
]

_DOCUMENT_TYPE = [
    ('', ''),
    ('despatch', 'Guía de remisión')
]

_GENERATED_STATUS = [
    ('', ''),
    ('generatederror', 'Generada con errores'),
    ('generatedok', 'Generada correctamente'),
    ('signederror', 'Firmada con errores'),
    ('signedok', 'Firmada correctamente'),
    ('senterror', 'No pudo ser enviada a SUNAT '),
    ('sentok', 'Enviada a SUNAT correctamente')
]

_CODE_STATUS = [
    ('', ''),
    ('0', 'Procesó correctamente'),
    ('98', 'En proceso'),
    ('99', 'Proceso con errores')
]

_SUNAT_HANDLING_CODE = [
    ('', ''),
    ('01', 'VENTA'),
    ('14', 'VENTA SUJETA A CONFIRMACION DEL COMPRADOR'),
    ('02', 'COMPRA'),
    ('04', 'TRASLADO ENTRE ESTABLECIMIENTOS DE LA MISMA EMPRESA'),
    ('18', 'TRASLADO EMISOR ITINERANTE CP'),
    ('08', 'IMPORTACION'),
    ('09', 'EXPORTACION'),
    ('19', 'TRASLADO A ZONA PRIMARIA'),
    ('13', 'OTROS')]

logger = logging.getLogger(__name__)


class ShipmentIn(metaclass=PoolMeta):
    'Supplier Shipment'
    __name__ = 'stock.shipment.in'


class ShipmentOut(metaclass=PoolMeta):
    '''Customer Shipment'''
    __name__ = 'stock.shipment.out'

    sunat_document_type = fields.Selection(
        _SUNAT_DOCUMENT_TYPE,
        'Tipo de documento SUNAT'
    )
    sunat_serial_prefix = fields.Text(
        'Prefijo SUNAT'
    )
    sunat_serial = fields.Text(
        'Número de serie SUNAT'
    )
    sunat_number = fields.Text(
        'Numero de documento SUNAT'
    )
    sunat_generated_status = fields.Selection(
        _GENERATED_STATUS,
        'Estado de guía de remisión electrónica generada'
    )
    sunat_date_generated = fields.DateTime(
        'Fecha de generación electrónica'
    )
    sunat_sent_status = fields.Selection(
        _CODE_STATUS,
        'Estado de envío SUNAT'
    )
    sunat_date_sent = fields.DateTime(
        'Fecha de envío SUNAT'
    )
    sunat_response_code = fields.Char(
        string='Código respuesta SUNAT'
    )
    sunat_response_message = fields.Text(
        'Mensaje de respuesta'
    )
    sunat_sent_observation = fields.One2Many(
        'sunat.observation', 'document', 'Observaciones SUNAT'
    )
    sunat_sent_error = fields.Text('Error en el envío')

    sunat_shipment_handling_code = fields.Selection(
        _SUNAT_HANDLING_CODE,
        'Motivo de traslado',
        required=True)

    reason = fields.Text('Detalles del traslado')

    grossweight = fields.Function(fields.Numeric(
        'Peso bruto', digits=(16, 4)), 'get_grossweight')
    netweight = fields.Function(
        fields.Numeric('Peso neto'),
        'get_netweight'
    )
    tareweight = fields.Numeric('Tara', digits=(16, 4), required=True)

    document_reference = fields.Char("Referencia", size=None, select=True,
                                     states={
                                         'readonly': Eval('state') == 'done',
                                     }, depends=['state'])


    @classmethod
    def __setup__(cls):
        '''Add a new buttton to send shipments to SUNAT'''
        super(ShipmentOut, cls).__setup__()
        cls._buttons.update({
            'send_sunat': {
                'invisible': Eval('state') != 'done',
                'readonly': Eval('sunat_sent_status') == '0',
            },
        })
        cls.tareweight.states['readonly'] = Eval('state').in_(
            ['done', 'cancel', 'assigned', 'packed'])
        cls.sunat_shipment_handling_code.states['readonly'] = Eval(
            'state').in_(['done', 'cancel', 'assigned', 'packed'])
        cls.state.selection.append(('voided', 'En Baja'))


    @fields.depends('outgoing_moves')
    def on_change_outgoing_moves(self, name=None):
        '''Update outgoing moves'''
        result = Decimal('0.0')
        for line in self.outgoing_moves:
            if line.product:
                weight = Decimal(
                    line.product.weight) if line.product.weight else Decimal('0.0')
                qty = Decimal(
                    line.quantity) if line.quantity else Decimal('0.0')
                line_weight = weight * qty
                result += Decimal(line_weight)

    @classmethod
    def done(cls, shipments):
        '''Overwrited method to the electronic shipment sends'''
        super(ShipmentOut, cls).done(shipments)

    @classmethod
    @ModelView.button
    def send_sunat(cls, shipments):
        '''Method to allows send a shipment to SUNAT included
           when the shipment is Done
        '''
        for shipment in shipments:
            if not shipment.outgoing_moves or\
                    len(shipment.outgoing_moves) == 0:
                return
            # Default values, stablished by SUNAT
            shipment.sunat_serial_prefix = 'T'
            shipment.sunat_document_type = '09'
            try:
                serial, number = shipment.number.split('-')
            except Exception:
                cls.raise_user_error(
                    'El número de guía de remisión no es válido')

            shipment.sunat_serial = serial
            shipment.sunat_number = number

            document = DocumentFactory.get_document(shipment)
            try:
                document.build_xml(
                    on_success=cls.successful_xml_generation,
                    on_failure=cls.xml_generation_failed)
            except Exception:
                if shipment.sunat_sent_error:
                    cls.raise_user_error(str(shipment.sunat_sent_error))
                continue
            if shipment.sunat_sent_status == '0':
                shipment.sunat_sent_error = ''
            shipment.save()

    @classmethod
    def resend_shipment(cls):
        pool = Pool()
        Date = pool.get('ir.date')

        start_date = Date.today()
        end_date = start_date - timedelta(days = 5)

        error_shipments = pool.get('stock.shipment.out').search([
            #('sunat_sent_status', '!=', '0'),
            ('state', 'in', ['done']),
            ('effective_date', '<=', start_date),
            ('effective_date', '>=', end_date)
        ], order = [('effective_date', 'DESC')])

        for shipment in error_shipments:

            if not shipment.sunat_sent_status:
                if not shipment.outgoing_moves or\
                        len(shipment.outgoing_moves) == 0:
                    return
                # Default values, stablished by SUNAT
                shipment.sunat_serial_prefix = 'T'
                shipment.sunat_document_type = '09'
                try:
                    serial, number = shipment.number.split('-')
                except Exception:
                    print('El número de guía de remisión no es válido')
                    #cls.raise_user_error( u'El número de guía de remisión no es válido' )

                shipment.sunat_serial = serial
                shipment.sunat_number = number
            
            if shipment.sunat_sent_status != '0':
                document = DocumentFactory.get_document(shipment)
                try:
                    document.build_xml(
                        on_success=cls.successful_xml_generation,
                        on_failure=cls.xml_generation_failed)
                    shipment.save()
                except Exception as e:
                    continue

    @classmethod
    def import_cron_resend_shipment(cls, args=None):
        '''The cron call the send routine for each shipment not sent
           successfully to the SUNAT
        '''
        cls.resend_shipment()

    @classmethod
    def successful_xml_generation(cls, despatch_advice, results):
        despatch_advice.shipment.sunat_generated_status = 'generatedok'
        despatch_advice.shipment.sunat_date_generated = datetime.now()
        shipment = despatch_advice.shipment
        key = shipment.company.sunat_private_key
        certificate = shipment.company.sunat_certificate
        despatch_advice.sign(
            key,
            certificate,
            on_success=cls.signing_succesful,
            on_failure=cls.signing_failed)

    @classmethod
    def xml_generation_failed(cls, despatch_advice, error=None):
        cls.raise_user_error(
            'Errores generando xml: {error}'.format(error=error))

    @classmethod
    def signing_succesful(cls, despatch_advice, results):
        '''When the document is signed correctly, the shipping sunat generated
           status is updated to "signedok", the SUNAT data are updated and
           the function tries to send the document to SUNAT
        '''
        despatch_advice.shipment.sunat_generated_status = 'signedok'
        company = despatch_advice.shipment.company
        username = company.sol_username
        password = base64.b64decode(company.sol_password).decode('utf-8')
        token = UsernameToken(username=username, password=password)
        in_production_environment = company.invoicing_mode == 'production'
        despatch_advice.send(
            with_token=token,
            is_production=in_production_environment,
            on_success=cls.send_succesful, on_failure=cls.send_failed)

    @classmethod
    def signing_failed(cls, despatch_advice, error=None):
        '''When the document is not signed correctly, the shipping status is updated
           to "Process with errors", and a user error message is trigger
        '''
        despatch_advice.shipment.sunat_sent_status = '99'
        despatch_advice.shipment.save()
        cls.raise_user_error(
            'Errores firmando xml: {error}'.format(error=error))

    @classmethod
    def send_succesful(cls, despatch_advice, results):
        '''When the shipment to the SUNAT is succesful, the shipping status is
           updated to "Process correctly"
        '''
        despatch_advice.shipment.sunat_sent_status = '0'
        despatch_advice.shipment.save()
        return

    @classmethod
    def send_failed(cls, despatch_advice=DespatchAdvice, error=None):
        '''When the shipment to the SUNAT fails, the shipping status is updated
           to "Process with errors", and the error field stores the error message
           that the SUNAT sends
        '''
        despatch_advice.shipment.sunat_sent_status = '99'
        despatch_advice.shipment.sunat_sent_error = error
        despatch_advice.shipment.save()
        return

    @staticmethod
    def default_sunat_shipment_handling_code():
        return '01'

    @staticmethod
    def default_grossweight():
        return Decimal(0.0)

    @staticmethod
    def default_netweight():
        return Decimal(0.0)

    @staticmethod
    def default_tareweight():
        return Decimal(0.0)

    def get_grossweight(self, name):
        """Calculate the grossweight. That is the sum of the netweight and 
           the tareweight"""
        if not self.tareweight:
            self.tareweight = Decimal('0.00')
        if not self.netweight:
            self.netweight = Decimal('0.00')
        return self.netweight + self.tareweight

    def get_netweight(self, name):
        """Calculates the net weight in kilos of the products in the lines

        Converts the total weights of each line to kilograms and returns
        as total net weight the sum rounded to two decimals

        """
        result = Decimal(0.0)
        move_kg_weight = Decimal(0.0)
        kg = Pool().get('product.uom')\
            .search([('symbol', '=', 'kg')])[0]
        for move in self.outgoing_moves:
            if move.product.weight_uom:
                if move.product.weight and move.quantity:
                    move_kg_weight = move.product.weight_uom.compute_qty(
                        move.product.weight_uom,
                        move.product.weight*move.quantity,
                        kg,
                        True
                    )
                else:
                    move_kg_weight = Decimal('0.0')
            else:
                move_kg_weight = Decimal('0.0')
            result += Decimal(move_kg_weight)

        return result.quantize(Decimal('0.0000'))

    @fields.depends('netweight', 'tareweight', 'grossweight', 'moves')
    def on_change_tareweight(self):
        '''Update the values of the netweight and the grossweight
           when the tareweight is changed
        '''
        if self.netweight and self.default_tareweight:
            self.grossweight = self.netweight + self.tareweight
            self.grossweight.quantize(Decimal(1.00))

    @fields.depends('netweight', 'tareweight', 'grossweight', 'moves')
    def on_change_netweight(self):
        '''Update the values of the tareweight and the grossweight
           when the netweight is changed
        '''
        if self.netweight and self.tareweight:
            self.grossweight = self.netweight + self.tareweight
            self.grossweight.quantize(Decimal(1.00))

    @fields.depends('netweight', 'tareweight', 'grossweight', 'moves')
    def on_change_moves(self):
        '''Update the values of the netweight, tareweight and grossweight
           when the moves(lines of the shipment) are changed
        '''
        return self.get_netweight(self.__name__)

    @property
    def sunat_shipment_handling_code_description(self):
        '''Get the human readeable string associated to the shipment
           handling code of the current shipment, to be used in the
           reports
        '''
        return self._find_description()

    def _find_description(self):
        '''Get the string associated to code in the dictionary related
           to field sunat shipment handling code
        '''
        for pair in _SUNAT_HANDLING_CODE:
            if self.sunat_shipment_handling_code in pair:
                return pair[1]


class StockShipmentSequence(ModelSQL, ModelView):
    '''Stock Shipment Sequence'''
    __name__ = 'stock.shipment.out.sequence'

    type = fields.Selection(
        _TYPE_DOCUMENT,
        'Tipo de documento',
        select=True,
        required=True
    )
    document_type = fields.Selection(
        _DOCUMENT_TYPE,
        'Tipo de comprobante',
        required=True,
    )

    despatch_sequence = fields.Many2One(
        'ir.sequence',
        'Secuencia',
        required = True,
        domain = [('code', '=', 'stock.shipment.out')],
        context = {'code': 'stock.shipment.out'}
    )


class DocumentFactory:
    @staticmethod
    def get_document(shipment_out):
        '''Get the generated document with the current shipment data'''
        despatch_advice = DespatchAdvice(shipment_out)
        # Renew the despatch lines to avoid duplication
        del despatch_advice.lines[:]
        for move_index in range(0, len(shipment_out.outgoing_moves)):
            move = shipment_out.outgoing_moves[move_index]
            despatch_line = DespatchLine(move, move_index)
            despatch_advice.add_line(despatch_line)
        return despatch_advice


class SUNATController(ModelSQL, ModelView):
    """This class allows to control the SUNAT connectivity in the
    stock_pe
    """
    
    sunat_automatic = fields.Boolean('Envio automático a SUNAT')

    
