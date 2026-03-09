import codecs
from genshi.template import MarkupTemplate
from os import path
import os

from . import BASE_PATH

TEMPLATES_FOLDER = path.join(BASE_PATH, 'template')
DEFAULT_DESPATCH_LINE_TEMPLATE = path.join(
    TEMPLATES_FOLDER, 'despatch_line.xml')
DEFAULT_DESPATCH_ADVICE_TEMPLATE = path.join(
    TEMPLATES_FOLDER, 'despatch_advice.xml')


class ParseableDocument(object):
    _xml_template = ''
    _xml_template_path = ''
    serial = None
    issue_date = None
    signature_id = None
    signature_party_identification = None
    signature_party_name = None
    observations = None
    is_unsubscribing = False
    has_related_document = False
    related_document_serial = None
    supplier_id = None
    supplier_name = None
    customer_id = None
    customer_name = None
    gross_weight = None
    is_split_consignment = 1
    handling_unit_quantity = None
    transport_mode_code = None
    transport_start_date = None
    carrier_id = None
    carrier_name = None
    driver_id = '00000000'
    license_plate = None
    has_multiple_vehicles = False
    vehicles_license_plates = list()
    delivery_ubigeo = None
    delivery_street_name = None
    origin_ubigeo = None
    origin_street_name = None
    port_id = None
    despatch_lines = list()

    @property
    def xml_template(self):
        raise AttributeError('This should be overriden')

    @property
    def xml_template_path(self):
        raise AttributeError('This should be overriden')

    @xml_template.setter
    def xml_template(self, xml_template):
        raise AttributeError('This should be overriden')

    @xml_template_path.setter
    def set_xml_template_path(self, xml_template_path):
        raise AttributeError('This should be overriden')


class DespatchAdvice(ParseableDocument):
    def __init__(self):
        self.handling_code = '01'
        self.reason = 'undefined'
        self.serial = None
        self.issue_date = None
        self.signature_id = None
        self.signature_party_identification = None
        self.signature_party_name = None
        self.observations = None
        self.is_unsubscribing = False
        self.has_related_document = False
        self.related_document_serial = None
        self.supplier_id = None
        self.supplier_name = None
        self.customer_id = None
        self.customer_name = None
        self.gross_weight = None
        self.is_split_consignment = 1
        self.handling_unit_quantity = None
        self.transport_mode_code = None
        self.transport_start_date = None
        self.carrier_id = None
        self.carrier_name = None
        self.driver_id = '00000000'
        self.license_plate = None
        self.has_multiple_vehicles = False
        self.vehicles_license_plates = list()
        self.delivery_ubigeo = None
        self.delivery_street_name = None
        self.origin_ubigeo = None
        self.origin_street_name = None
        self.port_id = None
        self.despatch_lines = list()
        return

    @property
    def xml_template(self):
        if len(self._xml_template) == 0:
            with codecs.open(
                    DEFAULT_DESPATCH_ADVICE_TEMPLATE, 'r', 'iso-8859-1') as template:
                self._xml_template = template.read()
        return self._xml_template

    @xml_template.setter
    def set_xml_template(self, path):
        self._xml_template

    @property
    def xml_template_path(self):
        return self._xml_template_path

    @xml_template_path.setter
    def set_xml_template_path(self,
                              template_path=DEFAULT_DESPATCH_ADVICE_TEMPLATE):
        self._xml_template_path = template_path


class DespatchAdviceLine(ParseableDocument):
    item_ordinal = None
    item_uom = None
    item_quantity = None
    item_name = None
    sellers_item_reference = None

    def __init__(self):
        return

    @property
    def xml_template(self):
        if len(self._xml_template) == 0:
            with codecs.open(
                    DEFAULT_DESPATCH_LINE_TEMPLATE, 'r', 'iso-8859-1') as template:
                self._xml_template = template.read()
        return self._xml_template

    @xml_template.setter
    def set_xml_template(self, path):
        self._xml_template

    @property
    def xml_template_path(self):
        return self._xml_template_path

    @xml_template_path.setter
    def set_xml_template_path(self,
                              template_path=DEFAULT_DESPATCH_LINE_TEMPLATE):
        self._xml_template_path = template_path


class DespatchAdviceRenderer(object):
    def render(self, despatch_advice, despatch_lines=None):
        rendered_lines = ''
        if despatch_lines is None:
            despatch_lines = despatch_advice.lines
        result = self._render_body(despatch_advice)
        return result

    def _render_body(self, despatch_advice):
        template = MarkupTemplate(despatch_advice.xml_template)
        result = template.generate(
            document=despatch_advice).render(encoding='iso-8859-1')
        return result
