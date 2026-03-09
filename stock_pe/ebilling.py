# -*- coding: iso-8859-1 -*-
'''
This module glues together the erp objects and the objects defined in the
'sunat' module.
'''
import logging
import codecs
from builtins import str
from os import path, makedirs
from zipfile import ZipFile
from lxml import etree
from dateutil import parser as date_parser
from decimal import Decimal
from datetime import date

from trytond.config import config

from .sunat import DespatchAdvice as DespatchAdviceDefinition
from .sunat import DespatchAdviceLine as DespatchLineDefinition
from .sunat import DespatchAdviceRenderer
from .sunat import DespatchAdviceValidator, DocumentSigner
from .sunat import SoapClient, UsernameToken
from .sunat import RequestException
from .sunat import SunatResponse


logging.basicConfig(filename='app.log', filemode='w', format='%(name)s - %(levelname)s - %(message)s')

sunat_invoicing_path = config.get('account_invoice', 'sunat_invoicing')
if not sunat_invoicing_path or len(sunat_invoicing_path) == 0:
    sunat_invoicing_path = '.'
DEST_PATH = path.join(sunat_invoicing_path, 'despatch')
GENERATED_DIR = path.join(DEST_PATH, 'generated')
SIGNED_DIR = path.join(DEST_PATH, 'signed')
CDR_DIR = path.join(DEST_PATH, 'cdrs')
SENT_DIR = path.join(DEST_PATH, 'sent')


def sanitatize(value):
    '''The sanitatize method eliminates inconsistencies in 
       the strings that are written into the document'''
    if value is not None:
        value = value.strip()
        value = value.replace("\n", "")
    return value


class DespatchAdvice(DespatchAdviceDefinition):
    _meta = None
    _lines = list()

    def __init__(self, document):
        if document is None:
            raise AttributeError('meta attribute cannot be None')
        self._meta = document
        self._hook_values()

    def _hook_values(self):
        '''Sets values for the elements to be rendered in the xml'''
        document = self._meta
        self.handling_code = document.sunat_shipment_handling_code
        self.reason = document.reason if document.reason else ''
        self.serial = document.sunat_serial_prefix + document.number
        self.issue_date = str(document.effective_date)
        self.signature_id = document.sunat_serial_prefix + document.number
        self.signature_party_identification = document.company.ruc
        self.signature_party_name = document.company.party.full_name
        self.observations = None
        self.has_observations = False
        # TODO: add support for unsubscription
        self.is_unsubscribing = False
        self.is_split_consignment = 0
        self.has_related_document = False
        self.related_document_serial = None
        self.supplier_id = document.company.ruc
        self.supplier_name = document.company.party.name
        self.customer_id = _find_ruc_in_identifiers(
            document.customer.identifiers)
        self.customer_name = document.customer.name
        # TODO: estimate weight, it hasn't been included in product
        self.gross_weight =\
            document.grossweight if document.grossweight else Decimal(0.0)
        # TODO: specify number of pallets or containers
        self.handling_unit_quantity = len(document.packages)
        # DONE: specify transport mode
        # 1 -> Public transport default
        # 2 -> Private transport
        self.transport_mode_code = '1'
        if document.carrier:
            if document.carrier.is_private:
                self.license_plate = '2'

        # TODO: maybe the transport start date is different
        self.transport_start_date = document.effective_date
        self.carrier_id = ''
        self.carrier_name = ''
        if document.carrier:
            if document.carrier.party.identifiers:
                self.carrier_id = _find_ruc_in_identifiers(
                    document.carrier.party.identifiers)
            if document.carrier.party.name:
                self.carrier_name = document.carrier.party.name
        # DONE: specify transport's license plate
        self.license_plate = None
        if document.carrier:
            if document.carrier.is_private:
                self.license_plate = document.carrier.vehicle_plate
        # TODO: specify if it is a convoy or something else
        self.has_multiple_vehicles = False
        # TODO: specify the license plates of the vehicles in the convoy
        self.vehicles_license_plates = None
        # TODO: which one should be the delivery address, the invoicing address
        self.delivery_ubigeo = document.delivery_address.ubigeo
        self.delivery_street_name = document.delivery_address.street
        self.origin_ubigeo = document.company.party.address_get().ubigeo
        self.origin_street_name = document.company.party.address_get().street
        self.port_id = '00'

        despatch_advice_data = ['handling_code',
                                'reason',
                                'serial',
                                'issue_date',
                                'signature_id',
                                'signature_party_identification',
                                'signature_party_name',
                                'observations',
                                'has_observations',
                                'is_unsubscribing',
                                'is_split_consignment',
                                'has_related_document',
                                'related_document_serial',
                                'supplier_id',
                                'supplier_name',
                                'customer_id',
                                'customer_name',
                                'gross_weight',
                                'handling_unit_quantity',
                                'transport_mode_code',
                                'transport_start_date',
                                'carrier_id',
                                'carrier_name',
                                'has_multiple_vehicles',
                                'vehicles_license_plates',
                                'delivery_ubigeo',
                                'delivery_street_name',
                                'origin_ubigeo',
                                'origin_street_name',
                                'port_id']

        for d in despatch_advice_data:
            if type(getattr(self, d)) in (str, str):
                clean_line = sanitatize(getattr(self, d))
                setattr(self, d, clean_line)

    @property
    def generated_file_path(self):
        return path.join(
            GENERATED_DIR,
            self.date,
            '{filename}.xml'.format(filename=self.filename))

    @property
    def shipment(self):
        return self._meta

    @property
    def signed_file_path(self):
        return path.join(
            SIGNED_DIR,
            self.date,
            '{filename}.xml'.format(filename=self.filename))

    @property
    def cdr_zipfile_path(self):
        return path.join(
            CDR_DIR,
            self.date,
            '{filename}.xml'.format(filename=self.filename))

    @property
    def date(self):
        return str(self._meta.effective_date)

    @property
    def cdr_filename(self):
        '''Returns the complete xml filename for this document\'s cdr'''
        return 'R-{filename}.xml'.format(filename=self.filename)

    @property
    def xml_filename(self):
        '''Returns the complete xml filename for this document'''
        return '{filename}.xml'.format(filename=self.filename)

    @property
    def zip_filename(self):
        '''Returns the complete zip filename for this document'''
        return '{filename}.zip'.format(filename=self.filename)

    @property
    def filename(self):
        '''
        Returns a string that complies with the filename specified by SUNAT
        '''
        return '{ruc}-{doc_type}-{serial}-{number}'.format(
            ruc=_find_ruc_in_identifiers(self._meta.company.party.identifiers),
            doc_type=self._meta.sunat_document_type,
            serial=self._meta.sunat_serial_prefix + self._meta.sunat_serial,
            number=self._meta.sunat_number)

    @property
    def lines(self):
        '''Returns the meta corresponding lines as DespatchAdviceLines'''
        return self._lines

    def add_line(self, line):
        if not self.gross_weight:
            self.gross_weight = 0
        self.gross_weight += line.get_weight()
        self._lines.append(line)

    def send(self,
             with_token=None,
             signed_document=None,
             read_signed_from=None,
             output_file=None,
             is_production=False,
             on_success=None,
             on_failure=None):
        '''
        Attempts to send the signed representation of this document, which is
        stored somewhere in the filesystem, to SUNAT's ebilling web service.
        '''

        if signed_document is None:
            if read_signed_from is None:
                date = self.date
                read_signed_from = path.join(
                    SIGNED_DIR, date, self.zip_filename)
            with codecs.open(
                    read_signed_from, 'r', encoding='iso-8859-1') as doc:
                signed_document = doc.read()

        if output_file is None:
            output_file = path.join(
                CDR_DIR, self.date, self.zip_filename)

        _make_sure_path_exists(output_file)

        try:
            signed_document = signed_document.encode('iso-8859-1')
        except Exception as ex:
            print(str(ex))
            pass

        try:
            client = SoapClient(wsse=with_token, production=is_production)      
            
            response = client.service.sendBill(self.zip_filename, signed_document)

            if response is None or len(response) <= 0:
                on_failure(self, 'No response')
                return

            try:
                response = response.decode('iso-8859-1')
            except Exception:
                logging.error(Exception)
                pass

            with codecs.open(output_file, 'w', 'iso-8859-1') as response_zip:
                response_zip.write(response)

            cdr_xml_contents = None
            with ZipFile(output_file, 'r') as cdr_zip:
                cdr_contents = cdr_zip.open(
                    'R-{filename}.xml'.format(filename=self.filename))
                if 'encode' in dir(cdr_contents):
                    cdr_contents = cdr_contents.encode('iso-8859-1')
                cdr_xml_contents = etree.parse(cdr_contents)

            if cdr_xml_contents is None:
                on_failure(self, error='CDR is empty')
                return
            ns = {
                'arx': 'urn:oasis:names:specification:ubl:schema:xsd:'
                'ApplicationResponse-2',
                'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:'
                'CommonBasicComponents-2',
                'ds': 'http://www.w3.org/2000/09/xmldsig#',
            }

            sunat_issue_date = cdr_xml_contents.find(
                './/cbc:IssueDate', ns).text
            sunat_response_date = cdr_xml_contents.find(
                './/cbc:ResponseDate', ns).text
            sunat_response_message = cdr_xml_contents.find(
                './/cbc:Description', ns).text
            sunat_digest = cdr_xml_contents.find(
                '//ds:DigestValue', ns).text

            results = SunatResponse()

            cdr_status = cdr_xml_contents.findall(".//cbc:ResponseCode", ns)
            results.sunat_response_code = cdr_status[0].text
            results.sunat_date_sent = date_parser.parse(sunat_issue_date)
            results.sunat_response_date =\
                date_parser.parse(sunat_response_date)
            results.sunat_response_message = sunat_response_message
            results.sunat_digest = sunat_digest
            sunat_response_obs = cdr_xml_contents.findall('.//cbc:Note', ns)
            if sunat_response_obs is not None:
                for obs in sunat_response_obs:
                    obs_code, obs_description = obs.text.split(' - ')
                    results.observations[obs_code] = obs_description

            self._meta.sunat_response_code = results.sunat_response_code
            self._meta.sunat_date_sent = results.sunat_date_sent
            self._meta.sunat_response_date = results.sunat_response_date
            self._meta.sunat_response_message = results.sunat_response_message
            self._meta.sunat_digest = results.sunat_digest

            on_success(self, results)
        except RequestException as e:
            error = e.detail.find('message')
            error_message = error.text
            logging.error(error_message)
            on_failure(self, error_message)
        except Exception as ex:
            logging.error(ex)
            on_failure(self, ex)

    def sign(self, key, cert,
             document=None,
             read_from=None,
             with_signer=DocumentSigner.sign_document,
             with_validator=DespatchAdviceValidator.is_valid_document,
             output_file_path=None,
             on_success=None,
             on_failure=None):
        '''
        Attemps to sign the xml representation generated for this document,
        which is stored somewhere in the filesystem, to SUNAT's ebilling web
        service.
        '''
        sign = with_signer
        validate = with_validator
        unsigned_data = None
        if document is None:
            if read_from is None:
                read_from = path.join(
                    GENERATED_DIR, self.date, self.xml_filename)
            unsigned_data = etree.parse(read_from)
        else:
            unsigned_data = etree.fromstring(document.encode('iso-8859-1'))

        if output_file_path is None:
            output_file_path = path.join(
                SIGNED_DIR, self.date, self.zip_filename)

        output_xml_file_path = path.join(
            path.dirname(output_file_path), self.xml_filename)

        _make_sure_path_exists(output_file_path)

        signed_document = None
        try:
            signed_data = sign(unsigned_data, key=key, cert=cert).getroot()
            signed_document = etree.ElementTree(signed_data)
            signed_document.write(
                output_xml_file_path,
                pretty_print=True,
                xml_declaration=True,
                encoding='ISO-8859-1',
                standalone='no'
            )

            with ZipFile(output_file_path, 'w') as myzip:
                myzip.write(
                    output_xml_file_path, self.xml_filename)

            if validate(signed_document) is False:
                on_failure(self, 'Signed document is invalid.')
            else:
                on_success(self, signed_document)
        except Exception as e:
            on_failure(self, e)

    def build_xml(self,
                  with_renderer=DespatchAdviceRenderer().render,
                  output_file=None,
                  on_success=None,
                  on_failure=None):
        '''
        Attempts to build an xml representation of this document, as
        specified by SUNAT's guides, and stores it somewhere in the filesystem
        '''
        if output_file is None:
            output_file = path.join(
                GENERATED_DIR, self.date, self.xml_filename)

        _make_sure_path_exists(output_file)

        render = with_renderer

        try:
            xml_output = render(self)
            if 'decode' in dir(xml_output):
                xml_output = xml_output.decode('iso-8859-1')
            with codecs.open(
                    output_file, 'w', encoding='iso-8859-1') as output:
                output.write(xml_output)
            on_success(self, xml_output)
        except Exception as e:
            print(str(e))
            on_failure(self, e)

    def _compute_weight_from_lines(self):
        result = 0
        for line in self.lines:
            result += line._meta.package.weight
        return result


class DespatchLine(DespatchLineDefinition):
    _meta = None

    def __init__(self, line, ordinal):
        if line is None:
            raise AttributeError('line cannot be none')
        self._meta = line
        self._hook_values(ordinal)

    def _hook_values(self, ordinal):
        '''Sets values for the elements to be rendered in the xml'''
        self.item_ordinal = ordinal + 1
        self.item_uom = self._meta.product.default_uom.symbol
        self.item_quantity = self._meta.quantity
        self.item_name = self._meta.product.name
        self.sellers_item_reference = self._meta.product.code

    def get_weight(self):
        if self._meta.package and self._meta.package.weight:
            return self._meta.package.weight
        return 0


def _find_ruc_in_identifiers(identifiers):
    for id in identifiers:
        # if id.type == 'pe_vat':
        return id.code


def _make_sure_path_exists(desired_path):
    try:
        desired_dirname = path.dirname(desired_path)
        makedirs(desired_dirname)
    except Exception as e:
        return
