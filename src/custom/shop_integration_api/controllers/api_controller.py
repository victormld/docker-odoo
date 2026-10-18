import json
import logging
from datetime import datetime
from odoo import http, fields
from odoo.http import request
_logger = logging.getLogger(__name__)

class ShopIntegrationAPI(http.Controller):

    def _json_response(self, data, status=200):
        """Genera respuestas JSON uniformes con el código HTTP correspondiente."""
        headers = [('Content-Type', 'application/json')]
        return request.make_response(json.dumps(data, default=str), headers=headers, status=status)

    def _authenticate_request(self):
        """Valida la API Key utilizando exclusivamente el sistema nativo de Odoo."""
        api_key = request.httprequest.headers.get('X-Api-Key')
        if not api_key:
            auth_header = request.httprequest.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                api_key = auth_header.split(' ', 1)[1]

        if not api_key:
            return False, self._json_response({
                'error': {'code': 'unauthorized', 'message': 'API Key ausente en la petición.'}
            }, status=401)

        # Validación estricta contra la base de datos (Hashes criptográficos)
        user_id = request.env['res.users.apikeys'].sudo()._check_credentials(scope='rpc', key=api_key)
        
        if not user_id:
            return False, self._json_response({
                'error': {'code': 'unauthorized', 'message': 'API Key inválida o revocada.'}
            }, status=401)
            
        # Adoptar la identidad de ese usuario en el entorno de Odoo
        request.update_env(user=user_id)
        return True, None

    @http.route('/api/v1/products', type='http', auth='public', methods=['GET'], csrf=False)
    def get_products(self, **kwargs):
        """Retorna el catálogo de productos activos filtrado y en stock."""
        # Paso 1: Autenticar la petición
        is_authenticated, error_response = self._authenticate_request()
        if not is_authenticated:
            return error_response

        try:
            domain = [('sale_ok', '=', True)]
            
            # Filtro por fecha de modificación
            modified_since = kwargs.get('modified_since')
            if modified_since:
                try:
                    dt = datetime.strptime(modified_since, '%Y-%m-%d')
                    domain.append(('write_date', '>=', dt))
                except ValueError:
                    return self._json_response({
                        'error': {
                            'code': 'invalid_parameter',
                            'message': 'Formato de fecha inválido. Use YYYY-MM-DD.'
                        }
                    }, status=400)

            # Filtro por categoría
            category_id = kwargs.get('category_id')
            if category_id:
                if not category_id.isdigit():
                    return self._json_response({
                        'error': {
                            'code': 'invalid_parameter',
                            'message': 'El parámetro category_id debe ser un entero.'
                        }
                    }, status=400)
                domain.append(('categ_id', '=', int(category_id)))

            products = request.env['product.template'].search(domain)

            # Filtro en memoria para stock > 0
            in_stock = kwargs.get('in_stock', '').lower() == 'true'
            if in_stock:
                products = products.filtered(lambda p: p.qty_available > 0)

            data = [{
                'id': p.id,
                'name': p.name,
                'list_price': p.list_price,
                'qty_available': p.qty_available,
                'categ_id': [p.categ_id.id, p.categ_id.name] if p.categ_id else False,
                'write_date': fields.Datetime.to_string(p.write_date),
            } for p in products]

            return self._json_response({'data': data}, status=200)

        except Exception as e:
            _logger.exception("Error en GET /api/v1/products")
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