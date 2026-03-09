# -*- coding: utf-8 -*-
"""
    sale_reports.py

    :copyright: (c) 2019 by Grupo ConnectTix SAC
    :license: see LICENSE for more details.
"""
import tempfile
import io
from trytond.report import Report
from trytond.model import  fields
from barcode import generate

__all__ = ['ReportBarcode']

class ReportBarcode(Report):
    'Report Barcode of product '
    __name__ = 'product.barcode.report'


    @classmethod
    def get_context(cls, records, data, **kwargs):
        context = super(ReportBarcode, cls).get_context(records,data)
        product = cls.generate_barcode(records)
        context['code_product'] = product[0]
        context['product_name'] = product[1]
        context['name_img'] = product[2]
        return context

    @classmethod
    def generate_barcode(cls,products):
        '''
        1) Identifies country :775
        2) Manufacturer product code, 3..8 digits.  :000
        3) product code, 2..6 digits.  product.code
        4) Check digit.
        ##number = '775' +'000'+ codeproduct #ean13
        '''
        product_code = ""
        product_name = ""
        namecodeBarimg = ""
        fp = io.BytesIO()

        #if select products  
        if products:
            product=products[0]
            # if exits the first product 
            if product:
                typeBarcode = 'code128'
                codeproduct = product.code
                product_name = product.name
                number = codeproduct
                level, path = tempfile.mkstemp(prefix='%s-%s-' % (typeBarcode,number))
                filename = generate(typeBarcode, number, output=path)
                try:
                    with open(filename, 'rb') as file_p:
                        label = fields.Binary.cast(file_p.read())
                except IOError:
                    self.raise_user_error('label_io_error', {
                        'number': codeproduct,
                        })
                except:
                    self.raise_user_error('label_error', {
                        'number': typeBarcode,
                        })
                return [codeproduct,product_name, label]