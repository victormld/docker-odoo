import json
import re
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged
from odoo.tests.common import get_db_name, new_test_user
from odoo.tools import config

UNKNOWN_RIF = 'J-00000000-0'


@tagged('-at_install', 'post_install', 'shop_integration_api')
class TestSpanishTranslation(HttpCase):
    """API messages follow the API user's language; before authenticating, Accept-Language."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.classPatch(config, 'options', dict(config.options, dbfilter=f'^{re.escape(get_db_name())}$'))
        cls.env['res.lang']._activate_lang('es_VE')
        cls.env['ir.module.module']._load_module_terms(['shop_integration_api'], ['es_VE'], overwrite=True)

        cls.keys = {}
        expiration = fields.Datetime.now() + timedelta(hours=12)
        for lang in ('en_US', 'es_VE'):
            user = new_test_user(cls.env, login=f'shop_api_{lang}', lang=lang,
                                 groups='base.group_user,sales_team.group_sale_salesman')
            cls.keys[lang] = cls.env['res.users.apikeys'].with_user(user)._generate('rpc', 'Shop', expiration)

        cls.env['res.partner'].create({'name': 'Spanish Shop Customer', 'vat': 'J-11111111-1'})
        cls.env['product.product'].create({'name': 'LANG-P1', 'default_code': 'LANG-P1', 'type': 'consu'})

    def _post_order(self, lang, rif):
        body = {'customer_rif': rif, 'external_ref': f'EXT-{lang}',
                'lines': [{'default_code': 'LANG-P1', 'quantity': 1}]}
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {self.keys[lang]}'}
        return self.url_open('/api/v1/orders', data=json.dumps(body), headers=headers).json()

    def test_messages_in_api_user_language(self):
        for lang, expected in (('es_VE', f'No existe un cliente con el RIF {UNKNOWN_RIF}'),
                               ('en_US', f'No customer has the RIF {UNKNOWN_RIF}')):
            with self.subTest(lang=lang):
                self.assertEqual(self._post_order(lang, UNKNOWN_RIF)['error']['message'], expected)

    def test_order_origin_in_api_user_language(self):
        data = self._post_order('es_VE', 'J-11111111-1')['data']
        self.assertEqual(self.env['sale.order'].browse(data['id']).origin, 'Tienda en línea')

    def test_unauthenticated_message_follows_accept_language(self):
        # Without a valid key there is no user yet: the shop's Accept-Language decides
        cases = (
            ({}, 'Missing API key. Send the "Authorization: Bearer <key>" header.'),
            ({'Accept-Language': 'es-VE'}, 'Falta la API key. Envíe la cabecera "Authorization: Bearer <clave>".'),
        )
        for headers, expected in cases:
            with self.subTest(headers=headers):
                res = self.url_open('/api/v1/products', headers=headers)
                self.assertEqual(res.json()['error']['message'], expected)

    def test_log_labels_menu_and_module_in_spanish(self):
        env = self.env(context=dict(self.env.context, lang='es_VE'))
        self.assertEqual(env['shop.api.call.log'].fields_get(['status_code'], ['string'])['status_code']['string'],
                         'Código de respuesta')
        self.assertEqual(env.ref('shop_integration_api.shop_api_call_log_menu').name, 'Llamadas a la API')
        # Not in Odoo's export: added by hand to the template and to es.po
        self.assertEqual(env.ref('base.module_shop_integration_api').shortdesc, 'API de integración con la tienda')
