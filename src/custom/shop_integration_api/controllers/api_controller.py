import functools
import json
import logging
from datetime import datetime

from odoo import fields, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

_logger = logging.getLogger(__name__)

DATE_FORMATS = ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S')


# ---------------------------------------------------------------------------
# Infraestructura compartida: errores, respuestas, autenticación
# ---------------------------------------------------------------------------

class ApiError(Exception):
    """Error controlado: se traduce al formato de error documentado para la tienda."""

    def __init__(self, status, code, message, field=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.field = field

    def payload(self):
        return {'error': {'code': self.code, 'field': self.field, 'message': self.message}}


def json_response(data, status=200, headers=None):
    headers = [('Content-Type', 'application/json; charset=utf-8')] + (headers or [])
    return request.make_response(json.dumps(data, default=str), headers=headers, status=status)


def authenticate():
    """Valida 'Authorization: Bearer <api key>' con las API keys nativas de Odoo
    y adopta la identidad del usuario dueño de la clave (sus permisos aplican)."""
    scheme, _sep, token = request.httprequest.headers.get('Authorization', '').partition(' ')
    token = token.strip()
    if scheme.lower() != 'bearer' or not token:
        raise ApiError(401, 'UNAUTHORIZED',
                       'Falta la API key. Envíe la cabecera "Authorization: Bearer <clave>".')
    uid = request.env['res.users.apikeys'].sudo()._check_credentials(scope='rpc', key=token)
    if not uid:
        raise ApiError(401, 'UNAUTHORIZED', 'API key inválida, vencida o revocada.')
    request.update_env(user=uid)
    return request.env.user


def api_endpoint(func):
    """Autentica, ejecuta el handler dentro de un savepoint y traduce errores al
    formato estándar."""

    @functools.wraps(func)
    def wrapper(self, **kwargs):
        error = None
        response = None
        try:
            authenticate()
            # Si algo falla a medias, el savepoint deshace lo escrito: nunca queda un pedido parcial.
            with request.env.cr.savepoint():
                response = func(self, **kwargs)
        except ApiError as exc:
            error = exc
        except AccessError:
            error = ApiError(403, 'FORBIDDEN', 'El usuario de la API no tiene permisos para esta operación.')
        except UserError as exc:  # incluye ValidationError: mensajes pensados para personas
            error = ApiError(422, 'BUSINESS_RULE_VIOLATION', str(exc))
        except Exception:
            _logger.exception('Error inesperado en %s', request.httprequest.path)
            error = ApiError(500, 'INTERNAL_ERROR', 'Error interno del servidor.')

        if error:
            headers = [('WWW-Authenticate', 'Bearer')] if error.status == 401 else None
            response = json_response(error.payload(), error.status, headers)
        return response

    return wrapper


# ---------------------------------------------------------------------------
# Validación de entrada
# ---------------------------------------------------------------------------

def parse_datetime(value, field):
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ApiError(400, 'INVALID_DATE_FORMAT',
                   'Formato de fecha inválido. Use AAAA-MM-DD o AAAA-MM-DDTHH:MM:SS (UTC).',
                   field=field)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

class ShopIntegrationAPI(http.Controller):

    # auth='public' + autenticación manual: con auth='bearer' una clave inválida se
    # rechazaría antes de entrar al controlador y no podríamos registrar el 401 en el log.
    @http.route('/api/v1/products', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    @api_endpoint
    def get_products(self, **kwargs):
        domain = [('sale_ok', '=', True)]  # active_test ya excluye los archivados

        modified_since = kwargs.get('modified_since')
        if modified_since:
            since = parse_datetime(modified_since, 'modified_since')
            # El precio vive en la plantilla: se revisa la fecha de ambos registros
            domain += ['|', ('write_date', '>=', since), ('product_tmpl_id.write_date', '>=', since)]

        category_id = kwargs.get('category_id')
        if category_id:
            try:
                domain.append(('categ_id', 'child_of', int(category_id)))
            except ValueError:
                raise ApiError(400, 'INVALID_CATEGORY', 'category_id debe ser un número entero.',
                               field='category_id')

        in_stock = kwargs.get('in_stock')
        if in_stock is not None:
            if in_stock.lower() not in ('true', 'false', '1', '0'):
                raise ApiError(400, 'INVALID_PARAMETER', 'in_stock debe ser true o false.', field='in_stock')
            if in_stock.lower() in ('true', '1'):
                domain.append(('qty_available', '>', 0))  # en la consulta, no en memoria

        products = request.env['product.product'].search(domain, order='id')
        return json_response({'data': [self._serialize_product(p) for p in products]})

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _serialize_product(product):
        return {
            'id': product.id,
            'default_code': product.default_code or None,
            'name': product.name,
            'price': product.lst_price,
            'qty_available': product.qty_available,
            'category_id': product.categ_id.id or None,
            'write_date': fields.Datetime.to_string(product.write_date),
        }
