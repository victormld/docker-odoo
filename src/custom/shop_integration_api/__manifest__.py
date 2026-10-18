{
    'name': 'Shop Integration API',
    'version': '1.0.0',
    'category': 'Sales/Integration',
    'summary': 'REST API para integración con tiendas externas (Catálogo y Pedidos)',
    'description': """
        Módulo de integración API REST diseñado para permitir a tiendas de terceros:
        - Consultar el catálogo de productos disponibles y su stock.
        - Crear pedidos de venta directamente en Odoo.
        - Registrar un log de auditoría de las llamadas a la API.
    """,
    'author': 'Víctor Maldonado',
    'depends': [
        'base',
        'product',
        'sale_management',
        'stock'
    ],
    'data': [
        
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}