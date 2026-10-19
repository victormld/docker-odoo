# AI_LOG — shop_integration_api

## Herramientas

- **Gemini (Google):** tramo A: `GET /api/v1/products`, sus filtros y la primera versión de las pruebas.
- **Claude Code** (app de escritorio; la última sesión con Claude Opus 5.5): tramo B, corrección de las pruebas, vistas del registro de llamadas, historial de commits y documentación.

## Prompts clave

1. **Gemini:** *«Desarrolla el tramo A: GET de productos con filtros por categoría, stock y fecha de modificación, con autenticación `user`»*, y luego *«cambia la autenticación para validar API keys»* (resumidos).
   - Generó el controlador con los filtros y después lo pasó a `auth='public'`, validando la clave contra `res.users.apikeys`. Lo tomé como base del tramo B: filtraba el stock en memoria y respondía los errores 500 con el texto de la excepción, y ambas cosas se corrigieron al reescribir el controlador.
2. **Claude Code:** *«Implementa el tramo B: POST /api/v1/orders con RIF, referencia externa y líneas, formato de error estándar y registro de cada llamada»* (resumido).
   - Reescribió el controlador con un decorador común (autenticación, savepoint, traducción de errores y registro) y agregó el endpoint de pedidos y el modelo `shop.api.call.log`. Lo revisé y lo probé con llamadas reales en mi base de desarrollo antes de seguir.
3. **Claude Code:** *«Continúa el trabajo en curso…»*, junto con mi análisis del 404 que daban todas las pruebas: sin cookie de sesión y con varias bases en el contenedor, Odoo no sabía a qué base enrutar.
   - Confirmó la causa en `odoo/http.py`: sin cookie, Odoo solo elige base si el `dbfilter` deja exactamente una, y la base temporal de las pruebas ni siquiera entraba en el filtro de la instancia. La solución fue exponer solo la base de prueba mientras corren las pruebas. Después le pedí simplificarlas: quedaron 8 en lugar de 21, con la misma cobertura.
4. **Claude Code:** *«¿Los tests verifican el funcionamiento del modelo de logs de la API?»*
   - No del todo: faltaban dos garantías del diseño. Le pedí probarlas: que un fallo al guardar el registro no rompa la respuesta y que solo los administradores puedan leerlo.
5. **Claude Code:** *«Corrige el README del módulo»*, pidiendo revisar cada afirmación contra el código.
   - Encontró que el permiso recomendado para el usuario de integración provocaba un 403 con clientes que tienen otro vendedor asignado, y lo confirmó en un shell de Odoo.

## Lo que la IA hizo mal

- **Gemini intentó arreglar el 404 agregando `?db=` a las URLs de las pruebas.** Odoo 18 no lee ese parámetro en rutas propias. Lo descarté porque el 404 seguía y mi análisis apuntaba a cómo Odoo resuelve la base sin cookie; se confirmó en `odoo/http.py`.
- **Las primeras pruebas no correspondían al controlador ni a Odoo 18:** usaban la cabecera `X-API-Key`, esperaban `success` y `error_code` en la respuesta y creaban productos con `detailed_type`, un campo que Odoo 18 eliminó. Se detectó al contrastar las pruebas con el controlador.
- **El registro de llamadas se creó sin vistas.** Lo noté al revisar el módulo y pedí lista, formulario, búsqueda y menú para poder probarlo desde la interfaz.
- **Las pruebas no cubrían dos garantías del registro** (que un fallo no rompa la respuesta y quién puede leerlo), aunque el modelo tenía 100% de cobertura de líneas. Salió al preguntar qué verificaban realmente las pruebas.
- **Claude se equivocó en dos pruebas propias:** un `patch.dict` que el `check_attrs` de Odoo rechaza, y una búsqueda con `('id', '>', False)` que nunca encuentra nada. Las corridas de pruebas lo mostraron y se corrigió antes de darlas por buenas.
- **La primera versión del README afirmaba cosas sin respaldo:** que había pruebas de filtros combinados y que bastaba el permiso *Solo mostrar documentos propios*. Se detectó al revisar el README contra el código: se agregó la prueba que faltaba y se corrigió el permiso después de confirmar el 403.

## Lo que escribí sin IA

- No escribí código a mano: lo generé con Gemini y Claude Code.
- Mi trabajo fue dirigir y validar: definir el alcance de cada paso, revisar el código de cada cambio antes de aceptarlo y probarlo funcionalmente en mi base de desarrollo con llamadas reales a los endpoints.
- El diagnóstico del 404 fue mío (cómo resuelve Odoo la base cuando la petición no trae cookie de sesión); la IA lo confirmó en el código fuente.
- Cómo separar el historial de commits según la convención del enunciado.
