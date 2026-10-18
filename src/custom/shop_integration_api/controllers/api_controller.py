import json
from datetime import datetime
from odoo import http
from odoo.http import request

class ShopIntegrationAPI(http.Controller):

    @http.route('/api/v1/products', type='http', auth='user', methods=['GET'], csrf=False)
    def get_products(self, **kwargs):
        try:
            # 1. Dominio base estricto: Solo productos activos y habilitados para la venta
            domain = [('active', '=', True), ('sale_ok', '=', True)]

            # 2. Filtrado por categoría
            category_id = kwargs.get('category_id')
            if category_id:
                try:
                    domain.append(('categ_id', '=', int(category_id)))
                except ValueError:
                    return self._json_response({
                        'error': {
                            'code': 'invalid_category',
                            'message': 'El parámetro category_id debe ser un número entero.'
                        }
                    }, status=400)

            # 3. Filtrado por disponibilidad de stock
            in_stock = kwargs.get('in_stock')
            if in_stock and str(in_stock).lower() in ['true', '1']:
                domain.append(('qty_available', '>', 0))

            # 4. Filtrado por fecha de modificación (Trampa del Error 500 controlada)
            modified_since = kwargs.get('modified_since')
            if modified_since:
                try:
                    valid_date = datetime.strptime(modified_since, '%Y-%m-%d')
                    domain.append(('write_date', '>=', valid_date))
                except ValueError:
                    return self._json_response({
                        'error': {
                            'code': 'invalid_date_format',
                            'message': 'El parámetro modified_since debe tener el formato YYYY-MM-DD.'
                        }
                    }, status=400)

            # 5. Búsqueda de productos en la base de datos
            products = request.env['product.product'].search(domain)

            # 6. Formateo exacto de la salida solicitada
            result = []
            for product in products:
                result.append({
                    'id': product.id,
                    'codigo': product.default_code or '',
                    'nombre': product.name,
                    'precio': product.list_price,
                    'cantidad_disponible': product.qty_available,
                })

            return self._json_response({'status': 'success', 'data': result}, status=200)

        except Exception as e:
            # Captura de seguridad o "catch-all" para cualquier otro error imprevisto
            return self._json_response({
                'error': {
                    'code': 'internal_server_error',
                    'message': str(e)
                }
            }, status=500)

    def _json_response(self, data, status=200):
        """Método auxiliar para devolver respuestas JSON nativas en controladores tipo 'http'."""
        return request.make_response(
            json.dumps(data),
            headers=[('Content-Type', 'application/json')],
            status=status
        )