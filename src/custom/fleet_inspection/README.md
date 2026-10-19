# Inspecciones de vehículos (`fleet_inspection`)

Migración a **Odoo 18** del módulo de inspecciones de vehículos escrito para Odoo 16. El original queda sin cambios en `src/custom/prueba-tecnica-odoo16/fleet_inspection` como referencia.

## Estado por tramo

| Tramo | Estado | Detalle |
|---|---|---|
| A | Completo | El módulo instala en Odoo 18, conserva todo lo que hacía y sus pruebas pasan. Cada cambio está explicado en la tabla de abajo. |
| B | Pendiente | Tipo de vehículo como catálogo, con script de migración. |
| C | No iniciado | |

## Qué hace

- Registra inspecciones de los vehículos de Flota con un checklist de puntos (frenos, luces, cauchos…) que se carga solo al crear la inspección.
- Estados: borrador → en curso → aprobada / rechazada. Un punto crítico con falla impide aprobar.
- Grupos: *Inspector* (ve solo las inspecciones donde es el inspector) y *Supervisor de inspecciones* (ve todas, aprueba, rechaza y vuelve a borrador).
- Acción planificada diaria que marca las inspecciones con más de 7 días en curso y le crea una actividad al inspector.
- Reporte PDF de la inspección.

## Migración a Odoo 18: qué cambió

| Qué cambió | Por qué | Cómo lo resolví |
|---|---|---|
| Ubicación y versión (`16.0.1.0.0` → `18.0.1.0.0`) | Odoo 18 rechaza una versión 16.0 ("invalid manifest") y, con el módulo en sus rutas de addons, deja de poder crear bases. | Copia en `src/custom/fleet_inspection` con la versión nueva; el original queda como referencia. |
| Textos fuente en inglés | Odoo usa el inglés como idioma fuente y traduce con archivos `.po`. | Etiquetas, vistas, menús, datos, grupos, reporte y mensajes en inglés. Las claves técnicas, los XML-ID y el prefijo `INS/` no cambian. La traducción al español se agrega en `i18n/es.po` al final del trabajo. |
| Mensajes con variable: `_("…") % valor` → `_("…", valor)` | Con el formato por fuera, una traducción con el marcador `%s` mal escrito rompe la acción. Con el formato dentro de `_()`, Odoo formatea después de traducir y, si la traducción está mal, usa el texto original. | Los 4 mensajes con variable. El resumen de la actividad de vencimiento se traduce al idioma del inspector, que es quien la recibe. |
| `<tree>` → `<list>` | Odoo 18 ya no tiene el tipo de vista `tree`: el módulo no instalaba. | Raíz de las vistas de lista y `view_mode` de las acciones. |
| `attrs` y `states` en las vistas | Desde 17.0 son un `ValidationError` al instalar. | Expresiones de Python en `invisible`, `readonly` y `required` (botones por estado, alerta de vencida, campos bloqueados y resultado obligatorio en curso). |
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

## Cómo probarlo

```bash
./odoo test prueba_tecnica fleet_inspection -d prueba_limpia
```

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
- Los textos del módulo están en inglés y se muestran en español a los usuarios con el idioma en español, mediante `i18n/es.po`.

## Limitaciones conocidas

Las dos primeras vienen del módulo original y se mantienen a propósito:

- **Aprobar, rechazar y volver a borrador no verifican el grupo en el servidor.** Los botones están ocultos para el inspector, pero un inspector puede llamar a esos métodos directamente (por ejemplo, por RPC) sobre sus propias inspecciones.
- **Inspectores y supervisores solo pueden abrir inspecciones de vehículos donde son el conductor.** El grupo *Inspector* hereda el grupo base de Flota, y la regla `fleet_rule_vehicle_visibility_user` del módulo `fleet` solo le deja leer esos vehículos; para el resto, el formulario de la inspección falla con un error de acceso a *Vehículo*. La regla y la herencia de grupos son idénticas en Odoo 16, así que allí pasa lo mismo. Para dar acceso: asignar al usuario como conductor del vehículo, o darle además el grupo *Administrador* de Flota.
- **La cobertura del script de pruebas mide la copia equivocada mientras exista el original.** `scripts/odoo-test` busca los módulos de forma recursiva y, con dos carpetas `fleet_inspection`, se queda con la última que encuentra (`prueba-tecnica-odoo16`). Odoo carga la correcta, así que el resultado de las pruebas es válido; solo el porcentaje de cobertura sale en 0%.
