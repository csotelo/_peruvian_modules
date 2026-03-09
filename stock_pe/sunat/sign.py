from signxml import XMLSigner, XMLVerifier
from signxml import methods
from lxml import etree

from .validator import DespatchAdviceValidator as DocumentValidator


class DocumentSigner(object):
    @staticmethod
    def sign_document(
                      document,
                      validate_document=DocumentValidator.is_valid_document,
                      cert=None, key=None):

        if cert is None:
            cert = ''
        cert = str.encode(str(cert))

        if key is None:
            key = ''
        key = str.encode(str(key))

        signer = XMLSigner(
            method=methods.enveloped,
            signature_algorithm='rsa-sha1',
            digest_algorithm='sha1',
            c14n_algorithm='http://www.w3.org/TR/2001/REC-xml-c14n-20010315'
        )

        if cert and len(cert) > 0:
            signed = signer.sign(
                document, key=key, cert=cert)
            xml_doc = etree.ElementTree(signed)
            signed_data = etree.tostring(signed)
            verified_data = XMLVerifier().verify(
                signed_data, x509_cert=cert).signed_xml
        else:
            xml_doc = document

        if validate_document(xml_doc) == False:
            raise ValueError('The signed document is not valid')
        else:
            return xml_doc