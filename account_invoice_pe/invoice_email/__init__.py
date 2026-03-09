from os import path
import codecs

DEFAULT_EMAIL_TEMPLATES_DIR = path.dirname(__file__)
DEFAULT_EMAIL_TEMPLATE_PATH = path.join(
    DEFAULT_EMAIL_TEMPLATES_DIR, 'invoice_template.html')

default_email_template_string = None
with codecs.open(DEFAULT_EMAIL_TEMPLATE_PATH, 'r', encoding='utf-8') as html_template:
    default_email_template_string = html_template.read()
