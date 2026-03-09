from trytond.pool import Pool
from .shipment import *
from .carrier import Carrier
from .product_barcode import ReportBarcode

def register():
    Pool.register(
        Carrier,
        ShipmentIn,
        ShipmentOut,
        StockShipmentSequence,
        module='stock_pe', type_='model')
    Pool.register(
        ReportBarcode,
        module='stock_pe', type_='report')