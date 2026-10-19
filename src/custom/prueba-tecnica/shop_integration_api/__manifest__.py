{
    'name': 'Shop Integration API',
    'version': '18.0.1.0.0',
    'category': 'Sales/Integration',
    'summary': 'REST API for external shops: product catalog and sales orders',
    'description': """
        REST API that lets an external online shop:
        - Read the catalog of products for sale and their stock.
        - Create sales orders directly in Odoo.
        - Keep an audit log of the API calls.
    """,
    'author': 'Víctor Maldonado',
    'depends': [
        'base',
        'product',
        'sale_management',
        'stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/shop_api_call_log_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
