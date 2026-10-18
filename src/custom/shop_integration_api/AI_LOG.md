# AI_LOG — shop_integration_api

## Herramientas

- Claude Code (modelo Claude Opus 5.5), desde la app de escritorio. Fue la única herramienta de IA que usé en este módulo.

## Prompts clave

1. *«Continúa el trabajo en curso en feature/ejercicio-1-shop-api: revisa los cambios sin commitear, dime en qué estado están y termina lo empezado»*, junto con mis notas sobre el 404 que daban todas las pruebas.
   - Encontró la causa en el código de Odoo 18: sin cookie de sesión, Odoo solo elige base si el `dbfilter` deja una sola, y la base temporal de las pruebas ni siquiera entraba en el filtro de la instancia. Propuso exponer solo la base de prueba durante las pruebas y reescribirlas para el contrato actual del controlador. Lo acepté y después le pedí simplificarlas: quedaron 8 pruebas en lugar de 21, con la misma cobertura.
2. *«¿Los tests verifican el funcionamiento del modelo de logs de la API?»*
   - Separó lo que sí se probaba de lo que no. Le pedí agregar las dos pruebas que faltaban: que un fallo al guardar el registro no rompa la respuesta y que solo los administradores puedan leerlo.
3. *«No existen las vistas del modelo de logs. Créalas para poder hacer pruebas funcionales»*
   - Creó lista, formulario, búsqueda y menú, y un nombre legible para cada registro. Actualizó el módulo en mi base de desarrollo y comprobó que las vistas cargan.
4. *«Ayúdame con los commits: sepáralos según los cambios que representa cada uno, con la nomenclatura del enunciado»*
   - Separó el trabajo en commits con prefijo y armó versiones intermedias del controlador para que cada commit fuera coherente. Detectó que `security/`, `views/` y `tests/__init__.py` nunca se habían commiteado, porque el `.gitignore` ignora `src/custom/*`.
5. *«Corrige el README del módulo»*, pidiéndole que revisara cada afirmación.
   - Comparó el README con el código y con Odoo 18 y encontró que el permiso que recomendaba para el usuario de integración no alcanzaba (ver abajo).

## Lo que la IA hizo mal

- En una sesión anterior intentó arreglar el 404 agregando `?db=` a las URLs de las pruebas. Odoo 18 no lee ese parámetro en rutas propias, así que las pruebas siguieron dando 404 hasta que se revisó `odoo/http.py`.
- Las primeras pruebas no correspondían al controlador: usaban la cabecera `X-API-Key`, esperaban respuestas con `success` y `error_code`, y creaban productos con `detailed_type`, un campo que ya no existe en Odoo 18. Se detectó al revisar los cambios sin commitear contra el controlador y el código de Odoo.
- Su primer arreglo del `dbfilter` usaba `patch.dict` y rompió todas las pruebas, porque Odoo exige que los patchers de clase tengan `.target`. Lo mostró la siguiente corrida de pruebas.
- Una prueba del registro buscaba con `('id', '>', False)` cuando la tabla estaba vacía, y esa búsqueda no encuentra nada. También lo mostró la corrida de pruebas.
- La primera versión del README decía que las pruebas cubrían filtros combinados, y no había ninguna. Además recomendaba el permiso *Solo mostrar documentos propios*, con el que la API responde 403 si el cliente tiene otro vendedor asignado. Se detectó al revisar el README contra el código, y el 403 se confirmó en un shell de Odoo.

## Lo que escribí sin IA

- Ningún código: todo el módulo pasó por Claude Code.
- Las decisiones sí fueron mías: qué pedirle, qué aceptar y qué alcance darle. Por ejemplo, noté que faltaban las vistas del registro de llamadas y decidí dejar el módulo en `src/custom/` en lugar de moverlo a `src/custom/prueba-tecnica/`.
