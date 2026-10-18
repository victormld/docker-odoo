import functools
import json
import logging
import math
from collections import defaultdict
from datetime import datetime

from odoo import Command, fields, http
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


def required_string(payload, key):
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ApiError(422, 'FIELD_REQUIRED', f'El campo {key} es obligatorio.', field=key)
    return value.strip()


def parse_line(index, raw):
    """Valida la estructura de una línea. Los índices del campo son base 0."""
    prefix = f'lines[{index}]'
    if not isinstance(raw, dict):
        raise ApiError(422, 'INVALID_LINE', 'Cada línea debe ser un objeto JSON.', field=prefix)
    code = raw.get('default_code')
    if not isinstance(code, str) or not code.strip():
        raise ApiError(422, 'FIELD_REQUIRED', 'El código del producto es obligatorio.',
                       field=f'{prefix}.default_code')
    qty = raw.get('quantity')
    # bool es subclase de int; NaN/Infinity los acepta json.loads de Python
    if isinstance(qty, bool) or not isinstance(qty, (int, float)) or not math.isfinite(qty) or qty <= 0:
        raise ApiError(422, 'INVALID_QUANTITY', 'La cantidad debe ser un número mayor que cero.',
                       field=f'{prefix}.quantity')
    return index, code.strip(), qty


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

    @http.route('/api/v1/orders', type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False)
    @api_endpoint
    def create_order(self, **kwargs):
        payload = request.httprequest.get_json(force=True, silent=True)
        if not isinstance(payload, dict):
            raise ApiError(400, 'INVALID_JSON', 'El cuerpo de la petición debe ser un objeto JSON válido.')

        # 1) Validar TODA la estructura antes de tocar la base de datos
        rif = required_string(payload, 'customer_rif').upper()
        external_ref = required_string(payload, 'external_ref')
        raw_lines = payload.get('lines')
        if not isinstance(raw_lines, list) or not raw_lines:
            raise ApiError(422, 'FIELD_REQUIRED', 'Debe enviar al menos una línea de pedido.', field='lines')
        lines = [parse_line(i, raw) for i, raw in enumerate(raw_lines)]

        # 2) Resolver cliente y productos (una sola consulta para todos los productos)
        partner = self._find_partner(rif)
        resolved = self._find_products(lines)

        # 3) Crear la cotización
        order = request.env['sale.order'].create({
            'partner_id': partner.id,
            'client_order_ref': external_ref,
            'origin': 'Tienda en línea',
            'order_line': [
                Command.create({'product_id': product.id, 'product_uom_qty': qty})
                for product, qty in resolved
            ],
        })
        return json_response({'data': self._serialize_order(order)}, status=201)

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _find_partner(rif):
        # parent_id = False: el vat se sincroniza a los contactos hijos; queremos la ficha comercial
        partners = request.env['res.partner'].search(
            [('vat', '=', rif), ('parent_id', '=', False)], limit=2)
        if not partners:
            raise ApiError(422, 'CUSTOMER_NOT_FOUND', f'No existe un cliente con el RIF {rif}',
                           field='customer_rif')
        if len(partners) > 1:
            raise ApiError(422, 'CUSTOMER_AMBIGUOUS', f'Hay más de un cliente con el RIF {rif}',
                           field='customer_rif')
        return partners

    @staticmethod
    def _find_products(lines):
        codes = list({code for _index, code, _qty in lines})
        found = defaultdict(list)
        for product in request.env['product.product'].search([('default_code', 'in', codes)]):
            found[product.default_code].append(product)

        resolved = []
        for index, code, qty in lines:
            field = f'lines[{index}].default_code'
            matches = found.get(code, [])
            if not matches:
                raise ApiError(422, 'PRODUCT_NOT_FOUND', f'No existe un producto con el código {code}',
                               field=field)
            if len(matches) > 1:
                raise ApiError(422, 'PRODUCT_AMBIGUOUS', f'Hay más de un producto con el código {code}',
                               field=field)
            if not matches[0].sale_ok:
                raise ApiError(422, 'PRODUCT_NOT_SELLABLE',
                               f'El producto {code} no está disponible para la venta', field=field)
            resolved.append((matches[0], qty))
        return resolved

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

    @staticmethod
    def _serialize_order(order):
        return {
            'id': order.id,
            'name': order.name,
            'state': order.state,
            'external_ref': order.client_order_ref,
            'customer_rif': order.partner_id.vat,
            'amount_untaxed': order.amount_untaxed,
            'amount_total': order.amount_total,
            'currency': order.currency_id.name,
            'lines': [{
                'default_code': line.product_id.default_code,
                'quantity': line.product_uom_qty,
                'price_unit': line.price_unit,
                'subtotal': line.price_subtotal,
            } for line in order.order_line],
        }
