
from trytond.pool import PoolMeta

__all__ = [
    'Product'
]

class Product(metaclass=PoolMeta):
    __name__ = 'product.Product'

    def get_product_quantity_by_warehouse(self):
        pass


