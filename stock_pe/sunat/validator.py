# -*- coding: iso-8859-1 -*-

import codecs
from os import path
import logging
from lxml import etree

from . import BASE_PATH

_LOGGER = logging.getLogger
DEFAULT_DESPATCH_XSD_PATH = path.join(
    BASE_PATH, 'maindoc', 'UBL-DespatchAdvice-2.0.xsd')

class DespatchAdviceValidator:

    @staticmethod
    def is_valid_document(document, path_to_document=None, xsd=None,
                          path_to_xsd=DEFAULT_DESPATCH_XSD_PATH,
                          logger=_LOGGER):
        is_valid = False
        if xsd is None:
            with codecs.open(path_to_xsd, 'r', 'ISO-8859-1') as f:
                xsd = etree.parse(f)

        if document is None:
            with codecs.open(path_to_document, 'r', 'ISO-8859-1') as f:
                document = etree.parse(f)

        schema, is_valid = DespatchAdviceValidator._get_valid_xsd(
            xsd, logger=logger)

        is_valid = DespatchAdviceValidator._is_valid_schema(
            schema, document, logger=logger)
        return is_valid

    @staticmethod
    def _get_valid_xsd(xsd, logger=_LOGGER):
        schema = None
        is_valid = True
        try:
            schema = etree.XMLSchema(xsd)
        except etree.XMLSchemaParseError as e:
            is_valid = False
            raise Exception("No es un documento XSD válido: %s" % e)
        finally:
            return (schema, is_valid)

    @staticmethod
    def _is_valid_schema(schema, document, logger=_LOGGER):
        is_valid = True
        try:
            schema.assertValid(doc)
        except etree.DocumentInvalid as e:
            logger.info("No es un documento XML válido: %s" % e)
            is_valid = False
            raise Exception("No es un documento XML válido")
        finally:
            return is_valid