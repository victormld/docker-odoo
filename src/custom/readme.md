# Prueba técnica — Desarrollador Odoo

Entrega de **Víctor Maldonado**: los cuatro ejercicios de la prueba, un módulo por ejercicio, todos en [`src/custom/prueba-tecnica/`](prueba-tecnica/). Los comandos de este documento se ejecutan desde la raíz del repositorio.

## Versión de Odoo

**18.0 Community.** En este repositorio la versión se elige por instancia en `instances.json` (`"odoo_version": "18.0"`), no con `ODOO_VERSION` en un `.env`. No hace falta Odoo Enterprise.

## Ejercicios

| # | Ejercicio | Módulo | Tramos | Documentación |
|---|---|---|---|---|
| 1 | Integración con API para una tienda en línea | `shop_integration_api` | A y B completos · C no iniciado | [README](prueba-tecnica/shop_integration_api/README.md) · [AI_LOG](prueba-tecnica/shop_integration_api/AI_LOG.md) |
| 2 | Migración del módulo de inspecciones | `fleet_inspection` | A y B completos · C no iniciado | [README](prueba-tecnica/fleet_inspection/README.md) · [AI_LOG](prueba-tecnica/fleet_inspection/AI_LOG.md) |
| 3 | Ticket urgente de última hora (T-200) | `sale_commission` | A y B completos · C pendiente | [Pull request #1](https://github.com/victormld/docker-odoo/pull/1) · [INCIDENT](https://github.com/victormld/docker-odoo/blob/hotfix/T-200/src/custom/prueba-tecnica/sale_commission/INCIDENT.md) · [AI_LOG](https://github.com/victormld/docker-odoo/blob/hotfix/T-200/src/custom/prueba-tecnica/sale_commission/AI_LOG.md) |
| 4 | Solicitudes de pago con aprobación | `payment_request` | A y B completos · C no implementado | [README](prueba-tecnica/payment_request/README.md) · [AI_LOG](prueba-tecnica/payment_request/AI_LOG.md) |

Cada README explica los tramos completados, cómo probar el módulo, los supuestos y las limitaciones conocidas, incluido lo que quedó pendiente. El del ejercicio 4 tiene la sección «Supuestos y preguntas al cliente».

### Ejercicio 3: la corrección está en el pull request

Como pide el enunciado, la corrección del ticket T-200 se hizo en la rama `hotfix/T-200` y se entrega como [pull request #1](https://github.com/victormld/docker-odoo/pull/1) hacia esta rama. **El pull request está abierto**, así que en esta rama `sale_commission` sigue como estaba antes del ticket: sus 4 pruebas originales pasan porque corren como administrador, que es justamente por qué no detectaron el error.

El pull request contiene:

- **La corrección:** el permiso de lectura de las reglas de comisión para el vendedor, y que la comisión sea la del vendedor del pedido y no la de quien lo confirma.
- **Las pruebas:** ahora corren con un usuario vendedor, no como administrador, y hay 4 nuevas: el vendedor confirma su pedido (sin regla y con regla de categoría), el permiso nuevo es solo de lectura y, si el gerente confirma el pedido de un vendedor, la comisión es la del vendedor. Las que reproducen el error fallaban antes de cada corrección y pasan después.
- **`INCIDENT.md`:** cómo se reproduce, causa raíz, corrección, contención en los primeros 15 minutos, qué commit introdujo el error y por qué pasó la revisión, despliegue y verificación, y el mensaje al cliente. También lo que queda para el tramo C.
- **`AI_LOG.md`** del ejercicio.

Para probar la corrección:

```bash
git checkout hotfix/T-200
./odoo test prueba_tecnica sale_commission -d prueba_limpia
```

Son 8 pruebas: las 4 originales y las 4 del ticket.

## Levantar el entorno

1. **Crear `instances.json`** en la raíz del repositorio. No se versiona: es la configuración local de cada entorno (la plantilla completa es `instances.example.jsonc`). Para esta prueba basta con:

   ```json
   {
     "odoo_configs": {
       "18.0_default": {
         "enabled": true,
         "workers": 2,
         "without_demo": true,
         "list_db": true,
         "proxy_mode": true,
         "server_wide_modules": "",
         "addons": []
       }
     },
     "databases": {
       "db_prueba": {
         "postgres_version": 16,
         "port": 5432,
         "expose_host_port": false,
         "user": "odoo",
         "config": "postgresql.small.conf",
         "create_container": true
       }
     },
     "instances": {
       "prueba_tecnica": {
         "enabled": true,
         "odoo_version": "18.0",
         "external_port": 8069,
         "database": "db_prueba",
         "odoo_config": "18.0_default",
         "overwrite_odoo_config": {
           "dev_mode": true,
           "addons": ["src/custom/prueba-tecnica"]
         }
       }
     },
     "pgadmin": {
       "enabled": false
     }
   }
   ```

   Los addons son solo `src/custom/prueba-tecnica`: `src/custom/prueba-tecnica-odoo16` guarda el módulo original de Odoo 16 como referencia y no debe estar en los addons, porque Odoo 18 rechaza su versión.

2. **Validar, construir y levantar:**

   ```bash
   ./odoo validate-instances
   ```

   ```bash
   ./odoo build
   ```

   ```bash
   ./odoo start
   ```

   Odoo queda en `http://localhost:8069`.

## Pruebas

```bash
./odoo test prueba_tecnica shop_integration_api,fleet_inspection,sale_commission,payment_request -d prueba_limpia
```

El script crea la base `prueba_limpia`, instala los cuatro módulos juntos, corre sus pruebas y borra la base al terminar. Resultado: **74 pruebas, 0 fallas, 96% de cobertura** (14 de `shop_integration_api`, 20 de `fleet_inspection`, 4 de `sale_commission` y 36 de `payment_request`).

El comando del enunciado (`./odoo test -d prueba_limpia -m …`) no indica la instancia; en este repositorio el script la pide de forma interactiva.

## Idioma de los textos

Código, nombres técnicos y modelos en inglés; documentación en español. Los textos que ve el usuario dependen del tipo de trabajo:

- **`shop_integration_api` y `payment_request`, desarrollos nuevos:** textos en inglés, el idioma fuente de Odoo, con la traducción al español en `i18n/es.po`. Se ven en español activando el idioma en *Ajustes › Idiomas* y eligiéndolo en el usuario. Los mensajes de la API salen en el idioma del usuario de integración.
- **`fleet_inspection`, migración:** conserva los textos originales en español del módulo de Odoo 16. Traducir es una actividad de desarrollo, no de migración.
- **`sale_commission`, corrección urgente:** cambio mínimo, sin tocar los textos.

## Ramas

| Rama | Contenido |
|---|---|
| `victor_maldonado_prueba_tecnica` | Esta rama: la entrega, con los cuatro módulos. |
| `feature/ejercicio-1-shop-api`, `feature/ejercicio-2-fleet-inspection`, `feature/ejercicio-4-payment-request` | El desarrollo de cada ejercicio, ya integrado en esta rama. |
| `hotfix/T-200` | La corrección del ejercicio 3, en el pull request #1. |
| `feature/ajustes-entrega` | Los ajustes finales, ya integrados: idioma de los textos, los módulos en una sola carpeta y el README de la entrega. |

Los commits son pequeños y llevan prefijo: `[FEAT]`, `[FIX]`, `[MIG]`, `[TEST]` y `[DOC]`. Los del ejercicio 3 llevan además el número de ticket.

## Uso de IA

Usé Claude Code en los cuatro ejercicios y, en el tramo A del ejercicio 1, también Gemini. Cada módulo tiene su `AI_LOG.md` con las herramientas, los prompts clave, lo que la IA hizo mal y lo que hice sin ella.

## Sobre este repositorio

Es un fork de [binaural-dev/docker-odoo](https://github.com/binaural-dev/docker-odoo), un entorno para levantar varias instancias de Odoo con Docker. La documentación completa de la herramienta (el CLI `./odoo`, todas las opciones de `instances.json`, bases de datos y subdominios) está en el README de ese repositorio.
