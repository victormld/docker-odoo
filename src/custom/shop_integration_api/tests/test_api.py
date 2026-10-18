import json
from unittest.mock import patch
from odoo.tests import HttpCase, tagged

@tagged('post_install', '-at_install')
class TestShopIntegrationAPI(HttpCase):

    def setUp(self):
        super().setUp()
        # 1. Crear categoría de prueba
        self.category_1 = self.env['product.category'].create({'name': 'Categoría API 1'})
        
        # 2. Crear producto A
        self.product_a = self.env['product.product'].create({
            'name': 'Producto Test A',
            'default_code': 'TEST-A',
            'list_price': 150.0,
            'categ_id': self.category_1.id,
            'sale_ok': True,
            'is_storable': True,  
        })
        
        # Añadir 25 unidades de stock al Producto A
        self.env['stock.quant'].create({
            'product_id': self.product_a.id,
            'location_id': self.env.ref('stock.stock_location_stock').id,
            'quantity': 25.0,
        })

        # 3. Crear producto B (Sin stock, pero habilitado para venta)
        self.product_b = self.env['product.product'].create({
            'name': 'Producto Test B',
            'default_code': 'TEST-B',
            'list_price': 50.0,
            'sale_ok': True,
            'is_storable': True,
        })

        # 4. Crear producto C (NO habilitado para la venta)
        self.product_c = self.env['product.product'].create({
            'name': 'Producto Test C',
            'sale_ok': False,
        })

    def test_01_get_products_success(self):
        """Verifica que el endpoint retorna productos válidos y omite los no vendibles."""
        self.authenticate('admin', 'admin')  # auth='user' exige sesión activa
        response = self.url_open('/api/v1/products')
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data['status'], 'success')
        
        # Extraer IDs de la respuesta JSON
        product_ids = [p['id'] for p in data['data']]
        self.assertIn(self.product_a.id, product_ids, "El Producto A debería estar en la respuesta.")
        self.assertIn(self.product_b.id, product_ids, "El Producto B debería estar en la respuesta.")
        self.assertNotIn(self.product_c.id, product_ids, "El Producto C NO debe estar porque sale_ok=False.")

    def test_02_filter_in_stock(self):
        """Verifica que el filtro de stock > 0 funcione correctamente."""
        self.authenticate('admin', 'admin')
        response = self.url_open('/api/v1/products?in_stock=true')
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        product_ids = [p['id'] for p in data['data']]
        self.assertIn(self.product_a.id, product_ids, "Producto A tiene 25 en stock, debe aparecer.")
        self.assertNotIn(self.product_b.id, product_ids, "Producto B tiene 0 en stock, NO debe aparecer.")

    def test_03_invalid_category_error(self):
        """Verifica que el sistema atrape un category_id inválido y retorne HTTP 400 sin romper el servidor."""
        self.authenticate('admin', 'admin')
        response = self.url_open('/api/v1/products?category_id=letras')
        self.assertEqual(response.status_code, 400)
        
        data = response.json()
        self.assertEqual(data['error']['code'], 'invalid_category')

    def test_04_invalid_date_error(self):
        """Verifica que un formato de fecha erróneo retorne HTTP 400 en lugar de un Error 500 crudo."""
        self.authenticate('admin', 'admin')
        response = self.url_open('/api/v1/products?modified_since=31-12-2026')
        self.assertEqual(response.status_code, 400)
        
        data = response.json()
        self.assertEqual(data['error']['code'], 'invalid_date_format')
    def test_05_unauthenticated_access(self):
        """Verifica que un usuario sin sesión no pueda acceder a los datos de la API."""
        response = self.url_open('/api/v1/products')
        
        # Como usamos auth='user', Odoo protege la ruta bloqueando el acceso y 
        # devolviendo un HTTP 303 (See Other) para redirigir al portal de /web/login
        data = response.json()
        self.assertEqual(data.get('error', {}).get('code'), 'unauthorized')