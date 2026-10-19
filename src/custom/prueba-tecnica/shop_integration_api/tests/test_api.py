import json
import re
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import HttpCase, tagged
from odoo.tests.common import get_db_name, new_test_user
from odoo.tools import config

RIF = 'J-12345678-9'
AMBIGUOUS_RIF = 'J-99999999-9'


def line(code='SHOPAPI-P1', quantity=1):
    return {'default_code': code, 'quantity': quantity}


def order(**overrides):
    return {'customer_rif': RIF, 'external_ref': 'EXT-001', 'lines': [line(quantity=2)], **overrides}


@tagged('-at_install', 'post_install', 'shop_integration_api')
class TestShopIntegrationAPI(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.classPatch(config, 'options', dict(config.options, dbfilter=f'^{re.escape(get_db_name())}$'))

        cls.api_user = new_test_user(
            cls.env, login='shop_api_user', groups='base.group_user,sales_team.group_sale_salesman')
        cls.api_key = cls._api_key(cls.api_user)
        # Internal user without sales rights: authenticates but cannot create orders
        cls.no_sales_key = cls._api_key(new_test_user(cls.env, login='shop_api_no_sales'))

        cls.category = cls.env['product.category'].create({'name': 'API Parent'})
        child = cls.env['product.category'].create({'name': 'API Child', 'parent_id': cls.category.id})
        # For the combined filters: one product matches category and stock, and each of
        # the other two fails only one of the two filters
        cls.in_stock = cls._product('SHOPAPI-P1', list_price=100.0, categ_id=child.id)
        cls.no_stock = cls._product('SHOPAPI-P2', categ_id=child.id)
        cls.other_category = cls._product('SHOPAPI-P5')
        cls.not_sellable = cls._product('SHOPAPI-P3', sale_ok=False)
        cls.archived = cls._product('SHOPAPI-P4', active=False)
        warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.env['stock.quant']._update_available_quantity(cls.in_stock, warehouse.lot_stock_id, 10.0)
        cls.env['stock.quant']._update_available_quantity(cls.other_category, warehouse.lot_stock_id, 5.0)

        Partner = cls.env['res.partner']
        cls.customer = Partner.create({'name': 'Shop Customer', 'vat': RIF})
        # The VAT is copied to child contacts: it must not make the RIF ambiguous
        Partner.create({'name': 'Purchasing Contact', 'parent_id': cls.customer.id})
        Partner.create([{'name': 'Duplicate A', 'vat': AMBIGUOUS_RIF}, {'name': 'Duplicate B', 'vat': AMBIGUOUS_RIF}])

    @classmethod
    def _api_key(cls, user):
        expiration = fields.Datetime.now() + timedelta(hours=12)
        return cls.env['res.users.apikeys'].with_user(user)._generate('rpc', 'Shop', expiration)

    @classmethod
    def _product(cls, code, **vals):
        return cls.env['product.product'].create({
            'name': code, 'default_code': code, 'type': 'consu', 'is_storable': True, **vals})

    # -- helpers ------------------------------------------------------------

    def _headers(self, key):
        key = self.api_key if key is True else key
        return {'Authorization': f'Bearer {key}'} if key else {}

    def _get_products(self, query='', key=True):
        return self.url_open(f'/api/v1/products{query}', headers=self._headers(key))

    def _post_order(self, body, key=True):
        data = body if isinstance(body, str) else json.dumps(body)
        headers = {'Content-Type': 'application/json', **self._headers(key)}
        return self.url_open('/api/v1/orders', data=data, headers=headers)

    def _product_ids(self, query=''):
        res = self._get_products(query)
        self.assertEqual(res.status_code, 200, res.text)
        return {product['id'] for product in res.json()['data']}

    def _assert_error(self, res, status, code, field=None):
        self.assertEqual(res.status_code, status, res.text)
        error = res.json()['error']
        self.assertEqual((error['code'], error['field']), (code, field))
        self.assertTrue(error['message'])

    def _last_log_id(self):
        return self.env['shop.api.call.log'].search([], limit=1).id or 0  # ('id', '>', False) matches nothing

    # -- tests --------------------------------------------------------------

    def test_authentication_required(self):
        for key in (False, 'made-up-key'):
            with self.subTest(key=key):
                res = self._get_products(key=key)
                self._assert_error(res, 401, 'UNAUTHORIZED')
                self.assertEqual(res.headers.get('WWW-Authenticate'), 'Bearer')

    def test_products_list(self):
        res = self._get_products()
        self.assertEqual(res.status_code, 200, res.text)
        products = {product['id']: product for product in res.json()['data']}
        self.assertIn(self.no_stock.id, products)
        self.assertNotIn(self.not_sellable.id, products)
        self.assertNotIn(self.archived.id, products)

        data = products[self.in_stock.id]
        self.assertTrue(data.pop('write_date'))
        self.assertEqual(data, {
            'id': self.in_stock.id, 'default_code': 'SHOPAPI-P1', 'name': 'SHOPAPI-P1',
            'price': 100.0, 'qty_available': 10.0, 'category_id': self.in_stock.categ_id.id,
        })

    def test_products_filters(self):
        none = self.env['product.product']
        yesterday = fields.Date.to_string(fields.Date.today() - timedelta(days=1))
        tomorrow = (fields.Datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')
        category = f'category_id={self.category.id}'
        cases = [
            # (query, must be listed, must not be listed)
            ('?in_stock=true', self.in_stock | self.other_category, self.no_stock),
            ('?in_stock=false', self.in_stock | self.no_stock | self.other_category, none),
            (f'?{category}', self.in_stock | self.no_stock, self.other_category),  # includes subcategories
            (f'?modified_since={yesterday}', self.in_stock, none),
            (f'?modified_since={tomorrow}', none, self.in_stock),
            # combined: each filter drops its own
            (f'?{category}&in_stock=true', self.in_stock, self.no_stock | self.other_category),
            (f'?{category}&in_stock=true&modified_since={yesterday}', self.in_stock,
             self.no_stock | self.other_category),
            (f'?{category}&in_stock=true&modified_since={tomorrow}', none, self.in_stock),
        ]
        for query, included, excluded in cases:
            with self.subTest(query=query):
                ids = self._product_ids(query)
                self.assertLessEqual(set(included.ids), ids)
                self.assertFalse(set(excluded.ids) & ids)

    def test_products_invalid_parameters(self):
        cases = [
            ('category_id=abc', 'INVALID_CATEGORY', 'category_id'),
            ('modified_since=31-12-2026', 'INVALID_DATE_FORMAT', 'modified_since'),
            ('in_stock=maybe', 'INVALID_PARAMETER', 'in_stock'),
        ]
        for query, code, field in cases:
            with self.subTest(query=query):
                self._assert_error(self._get_products(f'?{query}'), 400, code, field)

    def test_order_created(self):
        # The RIF is normalized: the shop may send it lowercase or with spaces
        res = self._post_order(order(customer_rif=' j-12345678-9 '))
        self.assertEqual(res.status_code, 201, res.text)
        data = res.json()['data']

        sale = self.env['sale.order'].browse(data['id'])
        self.assertEqual(sale.partner_id, self.customer)
        self.assertEqual(sale.client_order_ref, 'EXT-001')
        self.assertEqual(sale.state, 'draft')
        self.assertEqual(data['name'], sale.name)
        self.assertEqual(data['customer_rif'], RIF)
        self.assertEqual(data['lines'], [{
            'default_code': 'SHOPAPI-P1', 'quantity': 2.0, 'price_unit': 100.0, 'subtotal': 200.0,
        }])

    def test_order_validation_errors(self):
        cases = [
            ('this is not json', 400, 'INVALID_JSON', None),
            ('[1, 2]', 400, 'INVALID_JSON', None),
            ({}, 422, 'FIELD_REQUIRED', 'customer_rif'),
            (order(customer_rif='   '), 422, 'FIELD_REQUIRED', 'customer_rif'),
            (order(external_ref=None), 422, 'FIELD_REQUIRED', 'external_ref'),
            (order(lines=[]), 422, 'FIELD_REQUIRED', 'lines'),
            (order(lines=[{'quantity': 1}]), 422, 'FIELD_REQUIRED', 'lines[0].default_code'),
            (order(lines=['SHOPAPI-P1']), 422, 'INVALID_LINE', 'lines[0]'),
            *[(order(lines=[line(quantity=qty)]), 422, 'INVALID_QUANTITY', 'lines[0].quantity')
              for qty in (0, -5, 'text', None, True, float('nan'))],
            (order(customer_rif='J-00000000-0'), 422, 'CUSTOMER_NOT_FOUND', 'customer_rif'),
            (order(customer_rif=AMBIGUOUS_RIF), 422, 'CUSTOMER_AMBIGUOUS', 'customer_rif'),
            (order(lines=[line(), line('GHOST')]), 422, 'PRODUCT_NOT_FOUND', 'lines[1].default_code'),
            (order(lines=[line('SHOPAPI-P3')]), 422, 'PRODUCT_NOT_SELLABLE', 'lines[0].default_code'),
        ]
        for body, status, code, field in cases:
            with self.subTest(code=code, body=body):
                self._assert_error(self._post_order(body), status, code, field)

    def test_order_forbidden_without_sales_rights(self):
        res = self._post_order(order(external_ref='EXT-FORBIDDEN'), key=self.no_sales_key)
        self._assert_error(res, 403, 'FORBIDDEN')
        self.assertFalse(self.env['sale.order'].search_count([('client_order_ref', '=', 'EXT-FORBIDDEN')]))

    def test_calls_are_logged(self):
        last_id = self._last_log_id()
        self._get_products('?in_stock=true')
        self._get_products(key=False)
        self._post_order(order(customer_rif='J-00000000-0'))

        logs = self.env['shop.api.call.log'].search([('id', '>', last_id)], order='id')
        self.assertEqual(
            [(log.endpoint, log.method, log.user_id.id, log.status_code, log.error_code) for log in logs],
            [
                ('/api/v1/products', 'GET', self.api_user.id, 200, False),  # no query string
                ('/api/v1/products', 'GET', False, 401, 'UNAUTHORIZED'),
                ('/api/v1/orders', 'POST', self.api_user.id, 422, 'CUSTOMER_NOT_FOUND'),
            ],
        )
        self.assertEqual(logs[0].display_name, 'GET /api/v1/products (200)')

    def test_log_failure_does_not_break_response(self):
        Log = self.env['shop.api.call.log']
        last_id = self._last_log_id()
        with (
            patch.object(type(Log), 'create', side_effect=Exception('Simulated failure writing the log')),
            self.assertLogs('odoo.addons.shop_integration_api.controllers.api_controller', level='ERROR'),
        ):
            res = self._get_products()
        self.assertEqual(res.status_code, 200, res.text)
        self.assertFalse(Log.search_count([('id', '>', last_id)]))

    def test_log_access_restricted(self):
        Log = self.env['shop.api.call.log']
        admin = new_test_user(self.env, login='shop_api_admin', groups='base.group_user,base.group_system')
        self.assertFalse(Log.with_user(self.api_user).has_access('read'), 'The API user cannot see the log')
        self.assertTrue(Log.with_user(admin).has_access('read'))
        for operation in ('create', 'write'):
            with self.subTest(operation=operation):
                self.assertFalse(Log.with_user(admin).has_access(operation), 'Not even an administrator can alter the log')
