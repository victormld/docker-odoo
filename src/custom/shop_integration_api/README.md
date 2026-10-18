# Shop Integration API

API REST para que la tienda en línea del cliente consulte el catálogo con su stock y cree pedidos de venta en Odoo, sin intervención manual. Cada llamada queda en un registro de auditoría.

- **Versión de Odoo:** 18.0
- **Dependencias:** `product`, `sale_management`, `stock`

## Estado por tramo

| Tramo | Estado | Detalle |
|---|---|---|
| A | Completo | `GET /api/v1/products` con filtros por categoría, «solo con stock» y «modificados desde», combinables. Una fecha mal escrita devuelve 400, no 500. La autenticación por sesión (`'user'`) que pedía este tramo se reemplazó por las API keys del tramo B. |
| B | Completo | API keys nativas en `Authorization: Bearer`, `POST /api/v1/orders`, formato de error estándar con el campo exacto, registro de todas las llamadas (también las fallidas) y pruebas con `HttpCase`. |
| C | No iniciado | Ver [Limitaciones y pendientes](#limitaciones-y-pendientes). |

## Puesta en marcha

1. **Instalar el módulo** en la base de datos del cliente.
2. **Crear un usuario de integración** (usuario interno) con el permiso *Ventas: Usuario - solo sus documentos*. La API actúa con la identidad del dueño de la clave: se aplican sus permisos y reglas de registro. Un usuario sin permisos de ventas recibe 403 al crear un pedido.
3. **Generar la API key**: con ese usuario, en *Preferencias › Seguridad de la cuenta › Nueva clave API*. Odoo la muestra una sola vez; se entrega a la tienda por un canal seguro y se revoca desde la misma pantalla.
4. **Resolver una sola base por dominio.** La tienda no envía cookie de sesión, así que Odoo solo sabe qué base usar si el `dbfilter` deja exactamente una para el dominio de la petición (por ejemplo `^%d$` con un subdominio por base, o una sola base en el servidor). Si el filtro deja varias, toda ruta de la API responde 404.

## Referencia de la API

Todas las respuestas son JSON (`Content-Type: application/json; charset=utf-8`). Las fechas van en UTC.

### Autenticación

Todas las llamadas llevan la cabecera:

```
Authorization: Bearer <API key>
```

Sin la cabecera, o con una clave inválida, vencida o revocada, la respuesta es 401 con `WWW-Authenticate: Bearer`.

### `GET /api/v1/products`

Lista los productos activos que se pueden vender (`sale_ok`). Cada variante es un elemento.

| Parámetro | Formato | Efecto |
|---|---|---|
| `category_id` | entero | Productos de esa categoría y sus subcategorías. |
| `in_stock` | `true`, `false`, `1` o `0` | Con `true` solo trae productos con cantidad disponible mayor que cero. `false` no filtra. |
| `modified_since` | `AAAA-MM-DD`, `AAAA-MM-DDTHH:MM:SS` o `AAAA-MM-DD HH:MM:SS` (UTC) | Productos cuya variante o plantilla cambió en esa fecha o después (por ejemplo, un cambio de precio). |

```bash
curl -H "Authorization: Bearer $API_KEY" \
  "http://localhost:8069/api/v1/products?in_stock=true&category_id=5&modified_since=2026-10-01"
```

Respuesta `200`:

```json
{
  "data": [
    {
      "id": 42,
      "default_code": "ABC-123",
      "name": "Silla de oficina",
      "price": 100.0,
      "qty_available": 10.0,
      "category_id": 5,
      "write_date": "2026-10-15 13:20:05"
    }
  ]
}
```

- `price`: precio de venta de la ficha del producto, sin listas de precios.
- `qty_available`: stock a mano en las ubicaciones internas.
- `default_code` y `category_id` son `null` si el producto no los tiene.

### `POST /api/v1/orders`

Crea un pedido de venta. Odoo calcula precios e impuestos (lista de precios del cliente, impuestos del producto): la tienda no envía precios.

```bash
curl -X POST http://localhost:8069/api/v1/orders \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
        "customer_rif": "J-12345678-9",
        "external_ref": "WEB-1001",
        "lines": [
          {"default_code": "ABC-123", "quantity": 2},
          {"default_code": "XYZ-9", "quantity": 1.5}
        ]
      }'
```

| Campo | Obligatorio | Descripción |
|---|---|---|
| `customer_rif` | sí | RIF del cliente. Se pasa a mayúsculas, se ignoran los espacios al inicio y al final, y debe coincidir con el RIF de la ficha. |
| `external_ref` | sí | Referencia del pedido en la tienda. Se guarda como *Referencia del cliente*. |
| `lines` | sí | Lista con al menos una línea. |
| `lines[i].default_code` | sí | Código interno del producto. Debe coincidir exactamente; se ignoran los espacios al inicio y al final. |
| `lines[i].quantity` | sí | Número mayor que cero, en la unidad de venta del producto. Acepta decimales. |

Respuesta `201`:

```json
{
  "data": {
    "id": 17,
    "name": "S00017",
    "state": "draft",
    "external_ref": "WEB-1001",
    "customer_rif": "J-12345678-9",
    "amount_untaxed": 200.0,
    "amount_total": 232.0,
    "currency": "USD",
    "lines": [
      {"default_code": "ABC-123", "quantity": 2.0, "price_unit": 100.0, "subtotal": 200.0}
    ]
  }
}
```

El pedido se crea como **cotización** (`state: "draft"`), con origen *Tienda en línea*. Si algo falla, no se crea nada: nunca queda un pedido a medias.

### Errores

Todos los errores tienen el mismo formato:

```json
{
  "error": {
    "code": "PRODUCT_NOT_FOUND",
    "field": "lines[1].default_code",
    "message": "No existe un producto con el código ABC-123"
  }
}
```

- `code` es estable y sirve para programar contra él; `message` está en español y puede cambiar.
- `field` indica el dato que falló, o `null` si el error no es de un campo. Los índices de `lines` empiezan en 0: `lines[1]` es la segunda línea.
- Se devuelve un solo error, el primero que se encuentra. Primero se valida toda la estructura del cuerpo, después el cliente y al final los productos.

| HTTP | `code` | Cuándo | `field` |
|---|---|---|---|
| 400 | `INVALID_CATEGORY` | `category_id` no es un entero | `category_id` |
| 400 | `INVALID_PARAMETER` | `in_stock` no es `true`, `false`, `1` ni `0` | `in_stock` |
| 400 | `INVALID_DATE_FORMAT` | `modified_since` no tiene un formato aceptado | `modified_since` |
| 400 | `INVALID_JSON` | El cuerpo no es un objeto JSON | `null` |
| 401 | `UNAUTHORIZED` | Falta la API key o es inválida, vencida o revocada | `null` |
| 403 | `FORBIDDEN` | El usuario de la clave no tiene permisos para la operación | `null` |
| 422 | `FIELD_REQUIRED` | Falta un campo obligatorio o viene vacío | `customer_rif`, `external_ref`, `lines` o `lines[i].default_code` |
| 422 | `INVALID_LINE` | Una línea no es un objeto JSON | `lines[i]` |
| 422 | `INVALID_QUANTITY` | La cantidad no es un número mayor que cero | `lines[i].quantity` |
| 422 | `CUSTOMER_NOT_FOUND` | Ningún cliente tiene ese RIF | `customer_rif` |
| 422 | `CUSTOMER_AMBIGUOUS` | Más de un cliente tiene ese RIF | `customer_rif` |
| 422 | `PRODUCT_NOT_FOUND` | No existe un producto activo con ese código | `lines[i].default_code` |
| 422 | `PRODUCT_AMBIGUOUS` | Más de un producto tiene ese código | `lines[i].default_code` |
| 422 | `PRODUCT_NOT_SELLABLE` | El producto existe pero no se puede vender | `lines[i].default_code` |
| 422 | `BUSINESS_RULE_VIOLATION` | Odoo rechazó la operación por una regla de negocio | `null` |
| 500 | `INTERNAL_ERROR` | Error inesperado; el detalle queda en el log del servidor | `null` |

Con una ruta o un método HTTP que no existen, Odoo responde con sus propias páginas de error, no con este formato.

## Registro de llamadas

Cada petición a la API, exitosa o fallida, crea un registro en `shop.api.call.log` con endpoint, método HTTP, usuario (vacío si no se autenticó), código de respuesta, código de error y duración en milisegundos.

- **No se guardan** cabeceras, cuerpo ni query string: la API key nunca llega a la tabla.
- Si guardar el registro falla, la respuesta a la tienda no se ve afectada; el fallo queda en el log del servidor.
- Se consulta en *Ventas › Configuración › Tienda en línea › Llamadas a la API*. Tiene filtros por resultado (exitosas, 4xx, 5xx), llamadas sin autenticar y fecha, y agrupación por endpoint, código, usuario y día.
- Solo los administradores pueden verlo. Nadie puede crear ni modificar registros desde Odoo; un administrador puede borrarlos.

## Cómo probarlo

### Pruebas automáticas

```bash
./odoo test prueba_tecnica shop_integration_api -d prueba_limpia
```

Son 10 pruebas `HttpCase` que hacen peticiones HTTP reales contra el servidor de pruebas. Cubren:

- Autenticación: sin clave y con clave inválida.
- Listado de productos, cada filtro por separado y parámetros inválidos.
- Creación del pedido y todos los errores de validación del cuerpo.
- Usuario sin permisos de ventas: 403 y no se crea el pedido.
- El registro de llamadas: qué guarda, que un fallo al guardarlo no rompe la respuesta y quién puede leerlo.

Durante las pruebas el `dbfilter` expone solo la base de prueba, porque la tienda no envía cookie (ver *Puesta en marcha*, paso 4).

### Prueba manual

1. Seguir *Puesta en marcha*.
2. Crear un cliente con RIF y un producto vendible con código interno y stock.
3. Llamar a los endpoints con los `curl` de arriba.
4. Revisar la cotización en *Ventas* y las llamadas en *Ventas › Configuración › Tienda en línea › Llamadas a la API*.

## Supuestos

- **El pedido queda como cotización.** Así ventas revisa precios, stock y condiciones antes de comprometer inventario. Confirmarlo automáticamente sería llamar a `action_confirm()` después de crearlo.
- **Odoo es la fuente de verdad de los precios.** La tienda no envía precios; se aplican la lista de precios del cliente y los impuestos del producto.
- **El RIF se compara tal cual** (solo mayúsculas y espacios en los extremos). `J-12345678-9` y `J123456789` son RIF distintos. Se busca en la ficha comercial del cliente, no en sus contactos, que heredan el RIF.
- **El vendedor del pedido** es el asignado al cliente; si el cliente no tiene, queda el usuario de la API.
- **El código de producto** se compara exacto, distinguiendo mayúsculas y minúsculas (solo se ignoran los espacios en los extremos). Un producto archivado se trata como inexistente.
- **Las cantidades** van en la unidad de venta del producto.

## Limitaciones y pendientes

- **Tramo C no implementado:** paginación del listado, cabecera `Idempotency-Key`, aviso (webhook) a la tienda al validar la entrega y documentación en `openapi.yaml`.
- **Sin idempotencia:** si la tienda reintenta un POST, se crea otro pedido. `external_ref` no se valida como único.
- **`modified_since` no detecta cambios de stock:** un movimiento de inventario no modifica la fecha del producto. Para sincronizar stock hay que pedir el catálogo completo.
- **Listado sin paginar:** con catálogos grandes la respuesta crece sin límite. El stock se calcula en lote para todo el listado, pero no hay una prueba que mida el número de consultas.
- **Huecos en las pruebas:** no hay una prueba de filtros combinados (el código los combina, pero las pruebas cubren cada filtro por separado), ni de `PRODUCT_AMBIGUOUS`, `BUSINESS_RULE_VIOLATION` e `INTERNAL_ERROR`.
- **El registro de llamadas crece sin límite:** no hay limpieza automática de registros antiguos.
