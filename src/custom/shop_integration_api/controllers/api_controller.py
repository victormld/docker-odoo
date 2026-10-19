import functools
import json
import logging
import math
import time
from collections import defaultdict
from datetime import datetime

from odoo import Command, fields, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

_logger = logging.getLogger(__name__)

DATE_FORMATS = ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S')


# ---------------------------------------------------------------------------
# Shared infrastructure: errors, responses, authentication and logging
# ---------------------------------------------------------------------------

class ApiError(Exception):
    """Controlled error: rendered in the error format documented for the shop."""

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
    """Check 'Authorization: Bearer <api key>' against Odoo's native API keys and
    act as the key's owner, so that user's access rights apply."""
    scheme, _sep, token = request.httprequest.headers.get('Authorization', '').partition(' ')
    token = token.strip()
    if scheme.lower() != 'bearer' or not token:
        raise ApiError(401, 'UNAUTHORIZED',
                       request.env._('Missing API key. Send the "Authorization: Bearer <key>" header.'))
    uid = request.env['res.users.apikeys'].sudo()._check_credentials(scope='rpc', key=token)
    if not uid:
        raise ApiError(401, 'UNAUTHORIZED', request.env._('Invalid, expired or revoked API key.'))
    request.update_env(user=uid)
    # From here on, messages and translated data follow the API user's language
    request.update_context(lang=request.env.user.lang)
    return request.env.user


def log_call(user, status, error, started):
    """Log the call. It must never break the API response."""
    try:
        with request.env.cr.savepoint():
            request.env['shop.api.call.log'].sudo().create({
                'endpoint': request.httprequest.path,  # no query string or headers: the key never gets here
                'method': request.httprequest.method,
                'user_id': user.id if user else False,
                'status_code': status,
                'duration_ms': int((time.monotonic() - started) * 1000),
                'error_code': error.code if error else False,
            })
    except Exception:
        _logger.exception('Could not log the API call')


def api_endpoint(func):
    """Authenticate, run the handler inside a savepoint, render errors in the
    standard format and log EVERY call (failed ones too)."""

    @functools.wraps(func)
    def wrapper(self, **kwargs):
        started = time.monotonic()
        user = None
        error = None
        response = None
        try:
            user = authenticate()
            # If something fails halfway, the savepoint rolls back what was written: no partial orders.
            with request.env.cr.savepoint():
                response = func(self, **kwargs)
        except ApiError as exc:
            error = exc
        except AccessError:
            error = ApiError(403, 'FORBIDDEN',
                             request.env._('The API user is not allowed to perform this operation.'))
        except UserError as exc:  # includes ValidationError: messages meant for people
            error = ApiError(422, 'BUSINESS_RULE_VIOLATION', str(exc))
        except Exception:
            _logger.exception('Unexpected error in %s', request.httprequest.path)
            error = ApiError(500, 'INTERNAL_ERROR', request.env._('Internal server error.'))

        if error:
            headers = [('WWW-Authenticate', 'Bearer')] if error.status == 401 else None
            response = json_response(error.payload(), error.status, headers)
        log_call(user, response.status_code, error, started)
        return response

    return wrapper


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def parse_datetime(value, field):
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ApiError(400, 'INVALID_DATE_FORMAT',
                   request.env._('Invalid date format. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS (UTC).'),
                   field=field)


def required_string(payload, key):
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ApiError(422, 'FIELD_REQUIRED', request.env._('The %s field is required.', key), field=key)
    return value.strip()


def parse_line(index, raw):
    """Check the structure of one line. Field indexes are zero-based."""
    prefix = f'lines[{index}]'
    if not isinstance(raw, dict):
        raise ApiError(422, 'INVALID_LINE', request.env._('Each line must be a JSON object.'), field=prefix)
    code = raw.get('default_code')
    if not isinstance(code, str) or not code.strip():
        raise ApiError(422, 'FIELD_REQUIRED', request.env._('The product code is required.'),
                       field=f'{prefix}.default_code')
    qty = raw.get('quantity')
    # bool is a subclass of int; Python's json.loads accepts NaN/Infinity
    if isinstance(qty, bool) or not isinstance(qty, (int, float)) or not math.isfinite(qty) or qty <= 0:
        raise ApiError(422, 'INVALID_QUANTITY',
                       request.env._('The quantity must be a number greater than zero.'),
                       field=f'{prefix}.quantity')
    return index, code.strip(), qty


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

class ShopIntegrationAPI(http.Controller):

    # auth='public' plus manual authentication: with auth='bearer' an invalid key would be
    # rejected before reaching the controller, and the 401 could not be logged.
    @http.route('/api/v1/products', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    @api_endpoint
    def get_products(self, **kwargs):
        domain = [('sale_ok', '=', True)]  # active_test already leaves out archived products

        modified_since = kwargs.get('modified_since')
        if modified_since:
            since = parse_datetime(modified_since, 'modified_since')
            # The price lives on the template: check the date of both records
            domain += ['|', ('write_date', '>=', since), ('product_tmpl_id.write_date', '>=', since)]

        category_id = kwargs.get('category_id')
        if category_id:
            try:
                domain.append(('categ_id', 'child_of', int(category_id)))
            except ValueError:
                raise ApiError(400, 'INVALID_CATEGORY', request.env._('category_id must be an integer.'),
                               field='category_id')

        in_stock = kwargs.get('in_stock')
        if in_stock is not None:
            if in_stock.lower() not in ('true', 'false', '1', '0'):
                raise ApiError(400, 'INVALID_PARAMETER', request.env._('in_stock must be true or false.'),
                               field='in_stock')
            if in_stock.lower() in ('true', '1'):
                domain.append(('qty_available', '>', 0))  # in the query, not in memory

        products = request.env['product.product'].search(domain, order='id')
        return json_response({'data': [self._serialize_product(p) for p in products]})

    @http.route('/api/v1/orders', type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False)
    @api_endpoint
    def create_order(self, **kwargs):
        payload = request.httprequest.get_json(force=True, silent=True)
        if not isinstance(payload, dict):
            raise ApiError(400, 'INVALID_JSON',
                           request.env._('The request body must be a valid JSON object.'))

        # 1) Check the WHOLE structure before touching the database
        rif = required_string(payload, 'customer_rif').upper()
        external_ref = required_string(payload, 'external_ref')
        raw_lines = payload.get('lines')
        if not isinstance(raw_lines, list) or not raw_lines:
            raise ApiError(422, 'FIELD_REQUIRED', request.env._('Send at least one order line.'),
                           field='lines')
        lines = [parse_line(i, raw) for i, raw in enumerate(raw_lines)]

        # 2) Find the customer and the products (one query for all the products)
        partner = self._find_partner(rif)
        resolved = self._find_products(lines)

        # 3) Create the quotation
        order = request.env['sale.order'].create({
            'partner_id': partner.id,
            'client_order_ref': external_ref,
            'origin': request.env._('Online Store'),
            'order_line': [
                Command.create({'product_id': product.id, 'product_uom_qty': qty})
                for product, qty in resolved
            ],
        })
        return json_response({'data': self._serialize_order(order)}, status=201)

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _find_partner(rif):
        # parent_id = False: the VAT is synced to child contacts; we want the commercial entity
        partners = request.env['res.partner'].search(
            [('vat', '=', rif), ('parent_id', '=', False)], limit=2)
        if not partners:
            raise ApiError(422, 'CUSTOMER_NOT_FOUND', request.env._('No customer has the RIF %s', rif),
                           field='customer_rif')
        if len(partners) > 1:
            raise ApiError(422, 'CUSTOMER_AMBIGUOUS',
                           request.env._('More than one customer has the RIF %s', rif),
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
                raise ApiError(422, 'PRODUCT_NOT_FOUND', request.env._('No product has the code %s', code),
                               field=field)
            if len(matches) > 1:
                raise ApiError(422, 'PRODUCT_AMBIGUOUS',
                               request.env._('More than one product has the code %s', code),
                               field=field)
            if not matches[0].sale_ok:
                raise ApiError(422, 'PRODUCT_NOT_SELLABLE',
                               request.env._('Product %s is not available for sale', code), field=field)
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
