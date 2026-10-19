# Inspecciones de vehículos (`fleet_inspection`)

Migración a **Odoo 18** del módulo de inspecciones de vehículos escrito para Odoo 16. El original queda sin cambios en `src/custom/prueba-tecnica-odoo16/fleet_inspection` como referencia.

## Estado por tramo

| Tramo | Estado | Detalle |
|---|---|---|
| A | Completo | El módulo instala en Odoo 18, conserva todo lo que hacía y sus pruebas pasan. Cada cambio está explicado en la tabla de abajo. |
| B | Completo | El tipo de vehículo es un catálogo (`fleet.inspection.vehicle.type`) y los scripts de `migrations/18.0.2.0.0` asignan el tipo correcto a las inspecciones existentes. Probado con una actualización real. |
| C | No iniciado | |

## Qué hace

- Registra inspecciones de los vehículos de Flota con un checklist de puntos (frenos, luces, cauchos…) que se carga solo al crear la inspección.
- Estados: borrador → en curso → aprobada / rechazada. Un punto crítico con falla impide aprobar.
- Tipo de vehículo tomado de un catálogo configurable (moto, carro, camión, otro), que administra el supervisor.
- Grupos: *Inspector* (ve solo las inspecciones donde es el inspector) y *Supervisor de inspecciones* (ve todas, aprueba, rechaza y vuelve a borrador).
- Acción planificada diaria que marca las inspecciones con más de 7 días en curso y le crea una actividad al inspector.
- Reporte PDF de la inspección.

## Migración a Odoo 18: qué cambió

| Qué cambió | Por qué | Cómo lo resolví |
|---|---|---|
| Ubicación y versión (`16.0.1.0.0` → `18.0.1.0.0`) | Odoo 18 rechaza una versión 16.0 ("invalid manifest") y, con el módulo en sus rutas de addons, deja de poder crear bases. | Copia en `src/custom/fleet_inspection` con la versión nueva; el original queda como referencia. |
| `<tree>` → `<list>` | Odoo 18 ya no tiene el tipo de vista `tree`: el módulo no instalaba. | Raíz de las vistas de lista y `view_mode` de las acciones. |
| `attrs` y `states` en las vistas | Desde 17.0 son un `ValidationError` al instalar. | Expresiones de Python en `invisible`, `readonly` y `required` (botones por estado, alerta de vencida, campos bloqueados y resultado obligatorio en curso). |
| `invisible="1"` en columnas de listas | En Odoo 18, en una lista `invisible` solo vacía cada celda y la columna se sigue viendo; para ocultarla hay que usar `column_invisible`. | `column_invisible="True"` en "Vencida" (lista de inspecciones), "Activo" (puntos del checklist) y "Secuencia" y "Estado" (checklist del formulario). |
| `states=` en los campos `vehicle_id` y `vehicle_type` | Desde 17 no existe: Odoo lo ignora con un warning y el campo queda siempre de solo lectura. | Se quitaron del modelo; el bloqueo fuera de borrador quedó en la vista con `readonly="state != 'draft'"`. |
| `numbercall` y `doall` en la acción planificada | Ya no existen en `ir.cron` de Odoo 18: el XML no cargaba. | Se quitaron. |
| `create` con `@api.model` | Deprecado (ya daba warning en Odoo 16). | `@api.model_create_multi` con `Command.create`, con el mismo comportamiento. |
| `name_get` → `_compute_display_name` | Odoo 18 ya no llama a `name_get`: la placa desaparecía del nombre sin dar error. La prueba original seguía pasando porque llamaba a `name_get()` directamente. | `_compute_display_name` con la misma etiqueta (`INS/2026/0001 - <placa>`), y una prueba sobre `display_name`. |
| `<div class="oe_chatter">` | El formulario de Odoo 18 ya no lo reconoce. | `<chatter/>`. |
| `t-esc` en el reporte | Deprecado: con el modo desarrollador activo, cada impresión deja un warning. | `t-out` en sus 6 apariciones. |
| `odoo.tests.common.Form` | Deprecado en Odoo 18. | `from odoo.tests import Form`. |

### Evidencia

| Medición | Resultado |
|---|---|
| Módulo original en Odoo 16 | 9/9 pruebas, 94% de cobertura, 1 warning (`create` sin lote) |
| Odoo 18, después de vistas y acción planificada, con las pruebas originales | 9/9 pasan, pero quedan 12 warnings de `states`, el de `create` y el de `Form` |
| Odoo 18, pruebas nuevas antes de corregir los modelos | 13/14: falla `test_display_name_includes_plate` con `'INS/2026/0004' != 'INS/2026/0004 - AB123CD'` |
| Odoo 18, final del tramo A | 14/14 pruebas, 98% de cobertura, **0 warnings del módulo al instalar** |
| Odoo 18, junto con `shop_integration_api` en una base nueva | 24/24 pruebas |
| Comparación funcional manual con Odoo 16 | Mismo comportamiento (checklist, secuencia, estados, botones, permisos, vencidas, chatter, PDF y búsqueda). El error de acceso al vehículo para inspectores viene de las reglas del módulo `fleet` (ver limitaciones) |

Las pruebas nuevas cubren tres comportamientos que en Odoo 16 no tenían prueba: iniciar sin checklist, volver a borrador desde rechazada y borrar solo en borrador. También cubren los campos editables según el estado y que el reporte se renderice.

## Tramo B: tipo de vehículo como catálogo

**Versión 18.0.2.0.0.** El campo de selección `vehicle_type` se reemplaza por `vehicle_type_id`, un many2one obligatorio a `fleet.inspection.vehicle.type`:

- El catálogo tiene nombre, código, secuencia y activo. Trae cuatro tipos cuyos códigos son exactamente las claves del campo viejo: `motorcycle`, `car`, `truck` y `other`. La migración se basa en el código, no en el nombre, que el usuario puede cambiar.
- El tipo por defecto es "Carro", como antes. Un tipo en uso no se puede borrar (`ondelete="restrict"`).
- El inspector solo lee el catálogo; el supervisor lo administra en *Flota › Configuración › Tipos de vehículo*.

### Cómo se migran las inspecciones existentes

Al actualizar con `-u fleet_inspection` desde la versión 18.0.1, Odoo ejecuta:

1. **`pre-migrate.py`**, antes de tocar las tablas:
   - Renombra la columna vieja a `vehicle_type_legacy`, que queda como respaldo, y le quita el `NOT NULL`. Si lo conservara, ninguna inspección nueva se podría crear.
   - Crea `vehicle_type_id` vacía. Si la creara el ORM y el catálogo ya existiera, llenaría todas las filas con "Carro" y la migración ya no sabría cuáles faltan.
2. Odoo crea la tabla del catálogo y carga sus cuatro tipos.
3. **`post-migrate.py`**:
   - Asigna el tipo por código con un solo `UPDATE`, solo a las inspecciones que siguen sin tipo.
   - Un valor que no está en el catálogo crea su propio tipo, con un warning en el log; un valor vacío pasa a "Otro". Así no se pierde información.
   - Si alguna inspección queda sin tipo, lanza un error y Odoo revierte toda la actualización del módulo, incluido el renombre de la columna.
4. Recién después Odoo aplica el `NOT NULL` y la llave foránea a `vehicle_type_id`.

Correr los scripts dos veces no cambia nada, porque solo tocan lo que falta. El historial del chatter de los cambios de tipo se conserva: Odoo guarda la etiqueta del campo borrado en el seguimiento.

### Escenario probado

Sobre `dev_ej2_fleet`, con el módulo en la versión 18.0.1:

1. 4 inspecciones creadas a mano más 14 de prueba, en total 18: todos los tipos en todos los estados ("otro" incluido en los cuatro), y una inspección con historial de cambio de tipo en el chatter (Truck → Car → Truck).
2. Foto de cada inspección y su tipo antes de actualizar.
3. Actualización a 18.0.2.0.0 con `./odoo update prueba_tecnica -d dev_ej2_fleet -m fleet_inspection`.

| Verificación | Resultado |
|---|---|
| Log de la actualización | `18 inspections moved to the vehicle type catalog` · `{'car': 7, 'motorcycle': 3, 'other': 4, 'truck': 4}` · sin warnings ni errores |
| Inspecciones antes y después | 18 y 18 |
| Tipo de cada inspección contra la foto previa | 0 diferencias |
| Conteo por tipo y estado contra la foto previa | 0 diferencias ("otro": 4 antes, 4 después) |
| Tipo nuevo contra el respaldo `vehicle_type_legacy` | 0 diferencias |
| Inspecciones sin tipo | 0 |
| `vehicle_type_id` | `NOT NULL` y llave foránea con `ON DELETE RESTRICT` |
| Historial del chatter | Los dos cambios de tipo siguen visibles ("Vehicle Type: Truck → Car", "Car → Truck") |
| Inspección nueva después de migrar | Se crea con "Car" por defecto |
| Segunda actualización | No vuelve a ejecutar los scripts y no cambia ningún dato |

## Cómo probarlo

```bash
./odoo test prueba_tecnica fleet_inspection -d prueba_limpia
```

Son 20 pruebas. Las de `tests/test_vehicle_type.py` cubren el catálogo y la lógica de migración: cada una reconstruye dentro de su transacción la tabla como estaba antes de actualizar y ejecuta los scripts reales con `load_script`. Se comprobó que fallan si se rompe la lógica de los scripts.

Para comparar con el original se puede levantar una instancia de Odoo 16 con su propio servicio de Postgres y `src/custom/prueba-tecnica-odoo16` como única ruta de addons. Debe ser un servicio aparte: si dos instancias comparten servicio, el repositorio exige que cada una tenga su propio rol de Postgres o que no corra acciones planificadas.

```jsonc
"prueba_tecnica_16": {
  "odoo_version": "16.0",
  "external_port": 8070,
  "database": "db_prueba16",
  "odoo_config": "16.0_default",
  "overwrite_odoo_config": {
    "dev_mode": true,
    "addons": ["src/custom/prueba-tecnica-odoo16"]
  }
}
```

Al abrir *Flota › Inspecciones*, la lista muestra solo las inspecciones del usuario: la acción trae el filtro "Mis inspecciones" activo, igual que en Odoo 16. Un supervisor ve todas al quitar ese filtro.

## Supuestos

- La migración conserva el comportamiento del módulo original y no corrige su lógica, aunque tenga defectos (ver limitaciones).
- En la migración, un valor desconocido del campo viejo se conserva como un tipo nuevo del catálogo y un valor vacío pasa a "Otro".

## Limitaciones conocidas

- **La columna `vehicle_type_legacy` queda en la tabla** como respaldo de la migración. Odoo no la usa; se puede borrar en una versión futura, una vez confirmada la migración en producción.
Las dos primeras vienen del módulo original y se mantienen a propósito:

- **Aprobar, rechazar y volver a borrador no verifican el grupo en el servidor.** Los botones están ocultos para el inspector, pero un inspector puede llamar a esos métodos directamente (por ejemplo, por RPC) sobre sus propias inspecciones.
- **Inspectores y supervisores solo pueden abrir inspecciones de vehículos donde son el conductor.** El grupo *Inspector* hereda el grupo base de Flota, y la regla `fleet_rule_vehicle_visibility_user` del módulo `fleet` solo le deja leer esos vehículos; para el resto, el formulario de la inspección falla con un error de acceso a *Vehículo*. La regla y la herencia de grupos son idénticas en Odoo 16, así que allí pasa lo mismo. Para dar acceso: asignar al usuario como conductor del vehículo, o darle además el grupo *Administrador* de Flota.
- **La cobertura del script de pruebas mide la copia equivocada mientras exista el original.** `scripts/odoo-test` busca los módulos de forma recursiva y, con dos carpetas `fleet_inspection`, se queda con la última que encuentra (`prueba-tecnica-odoo16`). Odoo carga la correcta, así que el resultado de las pruebas es válido; solo el porcentaje de cobertura sale en 0%.
