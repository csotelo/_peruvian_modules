# -*- coding: iso-8859-1 -*-

import codecs
import logging
import os
import re
import smtplib
from smtplib import SMTP
from urllib.parse import urlparse
import email.utils
from builtins import str
from decimal import Decimal
from email import encoders
from email.mime.application import MIMEApplication
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate
from pathlib import Path
from zipfile import ZipFile
from datetime import date


from dateutil import parser as date_parser
from genshi.template import MarkupTemplate
from lxml import etree
from signxml import XMLSigner, XMLVerifier, methods
from trytond.modules.account_invoice_pe.sunat.documents import BASE_PATH
from trytond.pool import Pool

DOCUMENT_TEMPLATES = {
    '01': 'invoice.xml',
    '03': 'invoice.xml',
    '07': 'credit_note.xml',
    '08': 'debit_note.xml',
}

DOCUMENT_XML_TYPE = {
    '01': 'Invoice',
    '03': 'Invoice',
    '07': 'CreditNote',
    '08': 'DebitNote',
}

LINE_TEMPLATES = {
    '01': 'invoice_line.xml',
    '03': 'invoice_line.xml',
    '07': 'credit_note_line.xml',
    '08': 'credit_note_line.xml',
}

TAX_TEMPLATES = {
    '01': 'invoice_tax.xml',
    '03': 'invoice_tax.xml',
    '07': 'credit_note.xml',
    '08': 'credit_note.xml',
}

SUNAT_DOCUMENT_TYPE = {
    '': '',
    '01': 'FACTURA ELECTRÓNICA',
    '03': 'BOLETA DE VENTA',
    '07': 'NOTA DE CRÉDITO',
    '08': 'NOTA DE DÉBITO',
}

_DOCUMENT_TYPE = {
    '': '0',
    'pe_dtn': '0',
    'pe_dni': '1',
    'pe_frg': '4',
    'pe_vat': '6',
    'pe_pas': '7',
    'pe_dip': 'A',
}

TAXES = {
    ('1000', 'VAT', 'IGV'),
    ('2000', 'EXC', 'ISC'),
    ('9999', 'OTH', 'OTROS TRIBUTOS'),
}

_LOGGER = logging.getLogger(__name__)


class Document(object):
    _types = {
        '': '0',
        'pe_dtn': '0',
        'pe_dni': '1',
        'pe_frg': '4',
        'pe_vat': '6',
        'pe_pas': '7',
        'pe_dip': 'A',
    }

    _document_type_code = None
    _meta = None
    _xml_header_template = None
    _xml_line_template = None
    _xml_tax_template = None
    _sent_status = None
    _observations = dict()

    def __init__(self, document_object):
        if document_object is None:
            raise AttributeError('Document#_meta no puede ser None')
        self._meta = document_object
        header_xml_filename = DOCUMENT_TEMPLATES[self.document_type_code]
        line_xml_filename = LINE_TEMPLATES[self.document_type_code]
        tax_xml_filename = TAX_TEMPLATES[self.document_type_code]
        self._xml_header_template = self._load_xml_template(
            file_name=header_xml_filename)
        self._xml_line_template = self._load_xml_template(
            file_name=line_xml_filename)
        self._xml_tax_template = self._load_xml_template(
            file_name=tax_xml_filename)

    def _load_xml_template(self, folder_name='templates', file_name=None):
        template_path = os.path.join(
            BASE_PATH,
            folder_name,
            file_name
        )
        template = None
        with codecs.open(template_path, encoding='iso-8859-1') as template_file:
            template = template_file.read()
        return template

    def render(self):
        raise AttributeError('Document#renderer debe ser sobreescrito.')

    @property
    def filename(self):
        raise AttributeError(
            'Document#generate_filename debe ser sobreescrito.')

    @property
    def document_type(self):
        return SUNAT_DOCUMENT_TYPE[self._meta.sunat_document_type]

    @document_type.setter
    def document_type(self, value):
        raise AttributeError(
            'Se recomienda no modificar el tipo de documento.')

    @property
    def document_type_code(self):
        return self._meta.sunat_document_type

    @property
    def serial_prefix(self):
        return self._meta.sunat_serial_prefix

    @property
    def serial(self):
        return self._meta.sunat_serial

    @property
    def number(self):
        return self._meta.sunat_number

    @property
    def document(self):
        return self._meta

    @property
    def modified_document(self):
        return '{prefix}{number}'.format(
            prefix=self.serial_prefix,
            number=self.number
        )

    @property
    def modified_document_type(self):
        prefixes = {
            'B': '03',
            'F': '01',
        }
        return prefixes[self.serial_prefix]

    @property
    def serial_number(self):
        return "%s%s-%s" % (
            self.serial_prefix,
            self.serial.zfill(3),
            self.number.zfill(8)
        )

    @property
    def mult(self):
        mults = {
            '01': 1,
            '03': 1,
            '07': -1,
            '08': 1,
        }
        return mults[self.document_type_code]

    @property
    def sent_status(self):
        return self._sent_status

    @property
    def xml_header_template(self):
        # The type unicode is converted to str by 2to3 tool
        if 'encode' in dir(self._xml_header_template):
            return self._xml_header_template.encode('iso-8859-1')
        return self._xml_header_template

    @property
    def xml_line_template(self):
        # The type unicode is converted to str by 2to3 tool
        if 'encode' in dir(self._xml_line_template):
            return self._xml_line_template.encode('iso-8859-1')
        return self._xml_line_template

    @property
    def xml_tax_template(self):
        # The type unicode is converted to str by 2to3 tool
        if 'encode' in dir(self._xml_tax_template):
            return self._xml_tax_template.encode('iso-8859-1')
        return self._xml_tax_template

    @property
    def observations(self):
        return self._observations

    def write_document(self, document, path, on_success=None, on_failure=None):
        meta = document.document
        voided = meta.void_status
        filename = document.filename

        if not os.path.exists(path):
            os.makedirs(path)

        filepath = os.path.join(
            path,
            filename
        )
        xml_data = document.render()
        # The type unicode is converted to str by 2to3 tool
        if 'decode' in dir(xml_data):
            xml_data = xml_data.decode('ISO-8859-1').encode('utf-8')
            xml_doc = etree.XML(xml_data)
        else:
            xml_doc = etree.fromstring(xml_data)
        try:
            xml_result = etree.tostring(
                xml_doc,
                pretty_print=True,
                xml_declaration=True,
                encoding='ISO-8859-1',
                standalone='no'
            ).decode('iso-8859-1')

            try:
                xml_result = str(xml_result)
            except:
                pass
            with codecs.open(
                    '%s.xml' % filepath, 'w', encoding='utf-8') as f:
                f.write(xml_result)
            on_success(self, document)
        except Exception as e:
            if voided:
                meta.raise_user_error(str(e))
            pass

    def delete_document(self, document=None, path='.', generated_path=None, signed_path=None):
        if not document:
            document = self
        document_name = os.path.join(
            generated_path, '%s.xml' % document.filename)
        if Path(document_name).is_file():
            os.remove(document_name)
        document_name = os.path.join(signed_path, '%s.xml' % document.filename)
        if Path(document_name).is_file():
            os.remove(document_name)
        document_name = os.path.join(signed_path, '%s.zip' % document.filename)
        if Path(document_name).is_file():
            os.remove(document_name)

    def send(self, soap_client, file_path='.', zip_file_path=None, on_success=None, on_failure=None):
        _zip_file_path = None
        filename = self.filename
        void = self.document.void_status
        zip_file_name = '{filename}.zip'.format(filename=filename)
        if not zip_file_path:
            _zip_file_path = os.path.join(
                file_path,
                'signed',
                self.document.invoice_date.strftime('%Y%m%d'),
                zip_file_name
            )

        else:
            _zip_file_path = zip_file_path

        with codecs.open(_zip_file_path, 'r', encoding='iso-8859-1') as zip_file:
            zip_file_contents = zip_file.read()

        if not zip_file_contents:
            raise TypeError('El archivo zip no es válido')

        if not soap_client:
            raise TypeError('No se especificó un cliente soap')

        response = None
        ticket = None

        try:
            if void:
                ticket = soap_client.service.sendSummary(
                    zip_file_name, zip_file_contents.encode('iso-8859-1'))
                if ticket is None:
                    on_failure(self, error='Sin respuesta')
                    return
                else:
                    self.document.void_ticket = ticket
                    on_success(self, ticket)
                    return
            else:
                response = soap_client.service.sendBill(
                    zip_file_name, zip_file_contents.encode('iso-8859-1'))
                
            response_zip_path = os.path.join(
                file_path,
                'cdrs',
                self.document.invoice_date.strftime('%Y%m%d'),
                zip_file_name)

            if response is None:
                on_failure(self, error='Sin respuesta')
                return

            with open(response_zip_path, 'wb') as response_zip:
                response_zip.write(response)

            cdr_xml_contents = None

            with ZipFile(response_zip_path, 'r') as cdr_zip:
                cdr_file = cdr_zip.open(
                    'R-{filename}.xml'.format(filename=filename))
                cdr_xml_contents = etree.parse(cdr_file)

            if cdr_xml_contents is None:
                on_failure(self, error='CDR is empty')
                return

            ns = {
                'arx': "urn:oasis:names:specification:ubl:schema:xsd:ApplicationResponse-2",
                'cbc': "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
                'ds': 'http://www.w3.org/2000/09/xmldsig#',
            }

            sunat_issue_date = cdr_xml_contents.find(
                './/cbc:IssueDate', ns).text[:10]
            sunat_response_date = cdr_xml_contents.find(
                './/cbc:ResponseDate', ns).text
            sunat_response_message = cdr_xml_contents.find(
                './/cbc:Description', ns).text
            sunat_digest = cdr_xml_contents.find(
                '//ds:DigestValue', ns).text

            cdr_status = cdr_xml_contents.findall(".//cbc:ResponseCode", ns)
            self.document.sunat_response_code = cdr_status[0].text
            self.document.sunat_date_sent = date_parser.parse(sunat_issue_date)
            self.document.sunat_response_date = date_parser.parse(
                sunat_response_date)
            self.document.sunat_response_message = sunat_response_message
            if 'Presentacion fuera de fecha' in sunat_response_message:
                self.document.sunat_invoice_status = 'rejected'
            self.document.sunat_digest = sunat_digest
            sunat_response_obs = cdr_xml_contents.findall('.//cbc:Note', ns)
            if sunat_response_obs is not None:
                for obs in sunat_response_obs:
                    obs_text = obs.text.split(' - ')
                    if len(obs_text) >= 2:
                        obs_code = obs_text[0]
                        obs_description = obs_text[1]
                        self.observations[obs_code] = obs_description

            if(self.document.sunat_response_code == '0'):
                on_success(self, response)
            else:
                on_failure(self, '')

        except Exception as e:
            self.document.sunat_sent_error = str(e)
            if self.document.void_status:
                self.document.raise_user_error(str(e))
            pass

    def mail_to(self, recipient=None, sender=None, recipients=[], file_path='.', message=None):

        email_parsd = email.utils.parseaddr(sender)
        SENDER = email_parsd[1]
        SENDERNAME = email_parsd[0]

        uri_parsed = urlparse(sender)
        USERNAME_SMTP = uri_parsed.username
        PASSWORD_SMTP = uri_parsed.password
        
        HOST = uri_parsed.hostname
        PORT = uri_parsed.port

        self._is_email_address_valid(SENDER)
        if len(recipients) < 1 and recipient is None:
            raise ValueError("No ha ingresado una dirección de correo")
        elif len(recipients) < 1 and recipient is not None:
            recipients.append(recipient)

        self._are_email_addresses_valid(recipients)

        path_target = os.path.join(
            file_path,
            'signed',
            self.document.invoice_date.strftime('%Y%m%d')
        )
        filepath_target = os.path.join(
            path_target,
            self.filename
        )

        path_target_doc = os.path.join(
            file_path,
            'documents',
            self.document.invoice_date.strftime('%Y%m%d')
        )

        filepath_target_doc = os.path.join(
            path_target_doc,
            self.filename
        )

        xml_invoice = '%s.xml' % filepath_target

        if message is None:
            message = "Factura electronica %s" % self.filename
        subject = "Factura electronica %s" % self.filename
        themsg = MIMEMultipart('alternative')
        themsg['To'] = ', '.join(recipients)
        themsg['From'] = email.utils.formataddr((SENDERNAME, SENDER))
        themsg['Subject'] = subject  # 'File %s' % self.generate_filename()
        themsg['Date'] = formatdate(localtime=True)
        themsg.preamble = 'Factura electronica %s' % self.filename
        try:
            message = message.encode('iso-8859-1')
        except:
            pass
        themsg.attach(MIMEText(message, 'html', 'iso-8859-1'))
        themsg.attach(MIMEBase('application', 'zip'))

        InvoiceReport = Pool().get('account.invoice', type='report')
        report_info = InvoiceReport.execute([self.document.id], {})
        report_extension = report_info[0]
        report_cache = report_info[1]
        self.document.invoice_report_format, self.document.invoice_report_cache = \
            report_info[:2]
        self.document.save()
        if report_extension == 'pdf':
            pdf_file = open(filepath_target_doc + '.pdf', 'wb')
        if report_extension == 'odt':
            pdf_file = open(filepath_target_doc + '.odt', 'wb')
        pdf_file.write(report_cache)
        pdf_file.close()

        attachments = [xml_invoice, pdf_file.name]

        for f in attachments or []:
            part = MIMEBase('application', "octet-stream")
            with open(f, "rb") as file:
                part.set_payload(file.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition',
                    'attachment; filename="{}"'.format(os.path.basename(f)))
            themsg.attach(part)
        try:
            server = smtplib.SMTP(HOST, PORT)
            server.ehlo()
            server.starttls()
            #stmplib docs recommend calling ehlo() before & after starttls()
            server.ehlo()
            server.login(USERNAME_SMTP, PASSWORD_SMTP)
            server.sendmail(SENDER, recipients, themsg.as_string())
            server.close()
        except Exception as e:
            print(e)

    def _is_email_address_valid(self, address):
        re_pattern = r'^[_a-z0-9-]+(\.[_a-z0-9-]+)*@[a-z0-9-]+(\.[a-z0-9-]+)*(\.[a-z]{2,4})$'
        if address is None:
            raise ValueError("No ha ingresado una dirección de correo")
        if re.match(re_pattern, address, re.IGNORECASE) is False:
            raise ValueError(
                "La dirección de correo %s no es válida" % address
            )

    def _are_email_addresses_valid(self, addresses):
        for address in addresses:
            self._is_email_address_valid(address)


class DocumentValidator(object):
    def __init__(self):
        pass

    @classmethod
    def is_valid_document(cls, filename, sunat_document, logger=_LOGGER):
        is_valid = False
        document_type = sunat_document.document_type_code
        void = sunat_document.document.void_status
        if not isinstance(sunat_document, Document):
            raise AttributeError("El documento no es de tipo Document")
        if void:
            document_type = 'UBLPE-VoidedDocuments-1.0.xsd'
        else:
            if document_type in ('01', '03'):
                document_type = 'UBL-Invoice-2.1.xsd'
            elif document_type == '07':
                document_type = 'UBL-CreditNote-2.1.xsd'
            elif document_type == '08':
                document_type = 'UBL-DebitNote-2.1.xsd'

        xsd_file = os.path.join(
            BASE_PATH,
            'maindoc',
            document_type
        )

        schema, is_valid = cls._get_valid_xsd(xsd_file, logger=logger)
        is_valid = cls._is_valid_schema(schema, filename, logger=logger)

        return is_valid

    @classmethod
    def _get_valid_xsd(cls, xsd_file, logger=_LOGGER):
        schema = None
        is_valid = True
        with codecs.open(xsd_file, 'r', 'ISO-8859-1') as f:
            xsd_doc = etree.parse(f)
        try:
            schema = etree.XMLSchema(xsd_doc)
        except etree.XMLSchemaParseError as e:
            is_valid = False
            raise Exception("No es un documento XSD válido: %s" % e)
        finally:
            return (schema, is_valid)

    @classmethod
    def _is_valid_schema(cls, schema, filename, logger=_LOGGER):
        is_valid = True
        with codecs.open(filename, 'r', 'ISO-8859-1') as f:
            doc = etree.parse(f)
        try:
            schema.assertValid(doc)
        except etree.DocumentInvalid as e:
            logger.info("No es un documento XML válido: %s" % e)
            is_valid = False
            raise Exception("No es un documento XML válido")
        finally:
            return is_valid


class DocumentRenderer(object):

    def render_document(self, document):
        raise AttributeError(
            'DocumentRenderer#render_document debe sobreescribirse.')


class DocumentSigner(object):
    @classmethod
    def sign_document(cls, document, path,
                      validate_document=DocumentValidator.is_valid_document,
                      on_success=None, on_failure=None):
        meta = document.document
        void = meta.void_status
        path_source = os.path.join(
            path,
            'generated',
            meta.invoice_date.strftime('%Y%m%d')
        )
        path_target = os.path.join(
            path,
            'signed',
            meta.invoice_date.strftime('%Y%m%d')
        )
        path_sent = os.path.join(
            path,
            'sent',
            meta.invoice_date.strftime('%Y%m%d')
        )
        path_cdrs = os.path.join(
            path,
            'cdrs',
            meta.invoice_date.strftime('%Y%m%d')
        )
        path_documents = os.path.join(
            path,
            'documents',
            meta.invoice_date.strftime('%Y%m%d')
        )
        filename = document.filename
        generated_filename = filename

        if not os.path.exists(path_target):
            os.makedirs(path_target)
        if not os.path.exists(path_sent):
            os.makedirs(path_sent)
        if not os.path.exists(path_cdrs):
            os.makedirs(path_cdrs)
        if not os.path.exists(path_documents):
            os.makedirs(path_documents)
        filepath_source = os.path.join(
            path_source,
            filename
        )
        filepath_target = os.path.join(
            path_target,
            filename
        )
        cert = meta.company.sunat_certificate
        if cert is None:
            cert = ''
        cert = str.encode(str(cert))

        key = meta.company.sunat_private_key
        if key is None:
            key = ''
        key = str.encode(str(key))

        data = etree.parse('%s.xml' % filepath_source)
        signer = XMLSigner(
            method=methods.enveloped,
            signature_algorithm='rsa-sha1',
            digest_algorithm='sha1',
            c14n_algorithm='http://www.w3.org/TR/2001/REC-xml-c14n-20010315'
        )

        if cert and len(cert) > 0:
            signed = signer.sign(
                data, key=key, cert=cert)
            xml_doc = etree.ElementTree(signed)
            root = xml_doc.getroot()
            root[0][0][0][0].set('Id','SUNATSign')
            signed_data = etree.tostring(signed)
            verified_data = XMLVerifier().verify(
                signed_data, x509_cert=cert).signed_xml
        else:
            xml_doc = data

        xml_doc.write(
            '%s.xml' % filepath_target,
            pretty_print=True,
            xml_declaration=True,
            encoding='utf-8',
            standalone='no'
        )

        with ZipFile('%s.zip' % filepath_target, 'w') as myzip:
            myzip.write('%s.xml' % filepath_target, os.path.basename(
                '%s.xml' % filepath_target
            ))
        if validate_document('%s.xml' % filepath_target, document) == False:
            on_failure(document)
        else:
            on_success(document)
