# INCIDENT T-200 — Los vendedores no pueden confirmar pedidos

- **Ticket:** T-200 · Crítica · Comercial Los Andes C.A. (ficticia)
- **Módulo:** `sale_commission` 1.1.0, corregido en 1.1.1 (rama `hotfix/T-200`)

## Resumen

Desde el despliegue de las 12:00 (versión 1.1.0, comisión por categoría de producto), ningún vendedor puede confirmar pedidos: Odoo muestra un error de acceso. Con el gerente funciona.

La confirmación ahora lee las reglas de comisión por categoría y solo el gerente tenía permiso para leerlas. Además, esa misma versión toma el porcentaje de quien confirma en lugar del vendedor del pedido, así que los pedidos que el gerente confirmó esta tarde guardaron el porcentaje del gerente.

**Línea de tiempo (viernes):**

| Hora | Qué pasó |
|---|---|
| 12:00 | Se despliega la versión 1.1.0 (commit `3f4d73f`). |
| Desde las 12:00 | Los vendedores ven el error al confirmar; el gerente confirma los pedidos de todos. |
| 17:40 | Entra el ticket T-200. |

## Cómo se reproduce

En la interfaz:

1. Entrar con un usuario que tenga *Ventas: Usuario – solo mostrar documentos propios* y no sea gerente.
2. *Ventas › Pedidos › Nuevo*, elegir un cliente y cualquier producto, y pulsar **Confirmar**.
3. Aparece el error rojo: *«No puede acceder a los registros 'Comisión por categoría de producto' (sale.commission.rule)…»*.
4. El gerente confirma el mismo pedido sin problema. Si el pedido es de un vendedor y el producto no tiene regla de categoría, la línea guarda el porcentaje del gerente: con el vendedor al 5 % y el gerente al 7 %, la línea queda en 7 %.

Con las pruebas del módulo:

```bash
./odoo test prueba_tecnica sale_commission -d prueba_limpia
```

Antes de la corrección, las pruebas que confirman como vendedor fallan con el mismo error, en inglés en la base de pruebas: *"You are not allowed to access 'Comisión por categoría de producto' (sale.commission.rule) records. This operation is allowed for the following groups: Sales/Administrator"*.

## Causa raíz

Todo viene del commit **`3f4d73f`** «[FEAT] sale_commission: porcentaje de comisión por categoría de producto»:

1. **Permiso faltante (el error del ticket).** `SaleOrder.action_confirm` (`models/sale_order.py`) llama a `SaleOrderLine._get_commission_percent` (`models/sale_order_line.py`), que busca en el modelo nuevo `sale.commission.rule`. El commit creó ese modelo y en `security/ir.model.access.csv` le dio acceso **solo al gerente**; faltó la línea de lectura para el vendedor. La búsqueda corre con los permisos de quien confirma, y Odoo la rechaza.
2. **Porcentaje de quien confirma.** Si el producto no tiene regla de categoría, `_get_commission_percent` devolvía `self.env.user.commission_percent`, el usuario que confirma, en lugar de `self.order_id.user_id.commission_percent`, el vendedor del pedido. La versión 1.0 usaba el vendedor del pedido, y la docstring del método también lo dice.

La línea `access_sale_commission_report_salesman` del CSV **no es la culpable**, aunque sea la primera sospecha al mirar el archivo. Apunta a `model_sale_commission_report`, el permiso del vendedor para el análisis de comisiones (*Ventas › Reportes › Comisiones*). Existe desde la versión 1.0 (`ad51040`) y `3f4d73f` no la tocó. Cambiarla por el modelo de reglas destrabaría la confirmación, pero dejaría a los vendedores sin su reporte de comisiones.

## Corrección

| Commit | Cambio |
|---|---|
| `52477d2` | Línea **nueva** en `security/ir.model.access.csv`: lectura de `sale.commission.rule` para `sales_team.group_sale_salesman`. La línea del reporte no cambia. Versión 1.1.1. |
| `b33e995` | En `_get_commission_percent`, `self.env.user.commission_percent` pasa a `self.order_id.user_id.commission_percent`. |

**Por qué un permiso de lectura:**

- Confirmar un pedido necesita leer las reglas de comisión: es parte del trabajo del vendedor, no un caso excepcional. Con un permiso explícito, el acceso queda visible en la configuración de seguridad en lugar de esconderse en el código con `sudo()`.
- No se le da al vendedor el grupo del gerente, con el que podría crear y cambiar reglas y ver las comisiones de todos.
- Es solo lectura: el vendedor no puede crear, modificar ni borrar reglas. La prueba `test_salesman_cannot_modify_rules` lo verifica.
- **Riesgo aceptado:** el vendedor puede consultar los porcentajes por categoría, por ejemplo por la API. Son los mismos porcentajes que ya ve aplicados en sus líneas.

## Pruebas

La corrección va con pruebas que fallan antes del cambio y pasan después, y las pruebas corren **con un usuario vendedor**, no como administrador.

| Momento | Resultado |
|---|---|
| Suite original, con el error en producción | 4/4 pasan: no detectaban el error (ver *por qué pasó la revisión*) |
| `a2cb56f` [TEST] pruebas con el vendedor | 6 de 7 fallan con el error de acceso |
| `52477d2` [FIX] permiso de lectura | 7/7 |
| `6ac564e` [TEST] el gerente confirma el pedido de un vendedor | 7 de 8: falla con `7.0 != 5.0` |
| `b33e995` [FIX] porcentaje del vendedor del pedido | 8/8 |

Pruebas que agrega el hotfix:

- `test_t200_salesman_can_confirm` y `test_t200_salesman_can_confirm_with_category_rule`: el vendedor confirma su pedido, sin regla (5 %) y con regla de categoría (8 %).
- `test_salesman_cannot_modify_rules`: el permiso nuevo es solo de lectura.
- `test_manager_confirms_with_salesman_percent`: si el gerente confirma el pedido de un vendedor, la comisión es la del vendedor.

Además, `_create_order` vuelve a crear los pedidos como el usuario indicado, así que las pruebas anteriores también corren como vendedor.

## Contención: los primeros 15 minutos

Objetivo: que los vendedores puedan vender mañana a las 8:00 aunque la corrección todavía no esté desplegada.

1. **Minutos 0–5.** Confirmar en el log del servidor que el error es de acceso a `sale.commission.rule` y que empezó con el despliegue de las 12:00.
2. **Minutos 5–10.** En producción, sin desplegar código, crear a mano el mismo permiso que trae la corrección:
   - Ruta: *Ajustes › Técnico › Seguridad › Derechos de acceso › Nuevo* (requiere el modo desarrollador).
   - Nombre "TEMPORAL T-200", modelo *Comisión por categoría de producto*, grupo *Ventas / Usuario: solo mostrar documentos propios*.
   - Solo **Leer** marcado.
   - Se revierte borrando ese registro.
3. **Minutos 10–15.** Probar con un vendedor que confirma, y avisar al cliente (ver el mensaje más abajo).

Se probó en una base de desarrollo con el código de producción: sin el permiso, el vendedor recibe el error; con el permiso, confirma (8 % de comisión con regla de categoría); al borrarlo, el error vuelve.

**Riesgos de la contención:**

- Los vendedores pueden consultar los porcentajes por categoría (es el mismo riesgo aceptado de la corrección).
- Hasta desplegar la corrección sigue la segunda regresión: si alguien confirma un pedido que no es suyo y el producto no tiene regla, se guarda su propio porcentaje. Por eso, mientras tanto, cada vendedor confirma sus propios pedidos y el gerente deja de confirmar por ellos.

**Alternativas descartadas:**

- **Volver a la versión 1.0:** la 1.1 cambió el modelo de datos (la comisión dejó de ser un campo calculado y hay una tabla nueva de reglas). Bajar de versión no es reversible sin riesgo.
- **Seguir con el gerente confirmando todo:** no escala para el sábado, que es el día de más ventas, y además guarda comisiones equivocadas.
- **Dar a los vendedores el grupo del gerente:** son permisos de más.

## Qué commit introdujo el error y por qué pasó la revisión

`git log -p -- src/custom/prueba-tecnica/sale_commission` muestra tres commits:

- `ad51040` (versión 1.0);
- `3f4d73f` (versión 1.1, el despliegue de las 12:00);
- `87ac54d` (solo el README).

Para confirmarlo con una prueba se usó `git bisect` en modo `--no-checkout`, que no mueve el resto del repositorio. Un script pone el módulo en el commit a evaluar, le agrega `test_t200_salesman_can_confirm` (el vendedor confirma sin regla, un caso que ya existía en la 1.0) y corre solo esa prueba:

```bash
git bisect start --no-checkout 87ac54d ad51040   # malo, bueno
git bisect run <script que prueba BISECT_HEAD>
# 3f4d73f is the first bad commit
git bisect reset
```

En `ad51040` la prueba pasa; en `3f4d73f` falla con el error de acceso.

**Por qué pasó la revisión:**

- **El mismo commit debilitó las pruebas.** El helper `_create_order` dejó de crear los pedidos como el vendedor (`with_user(user)`), así que las pruebas corrían como superusuario, que no revisa permisos. Además se le puso al superusuario el mismo 5 % que al vendedor (`cls.env.user.commission_percent = 5.0`), lo que ocultó la segunda regresión. Las pruebas siguieron en verde, y el cambio en ellas pasó como un ajuste menor dentro de un commit grande.
- **El modelo nuevo recibió permisos para un solo grupo.** Nadie revisó quién más lo lee durante el flujo normal de venta.
- **Nadie lo probó con un usuario vendedor** antes de desplegar.

## Despliegue y verificación

Solo se actualiza el módulo **`sale_commission`**.

1. Respaldar la base de datos.
2. Poner el código de la rama `hotfix/T-200` (versión 1.1.1 del módulo).
3. Actualizar el módulo. Es necesario porque cambia la seguridad:
   ```bash
   ./odoo update <instancia> -d <base> -m sale_commission
   ```
4. Reiniciar Odoo, porque también cambia código Python: `./odoo restart <instancia>`.
5. Borrar el permiso "TEMPORAL T-200" de la contención; ahora lo trae el módulo.
6. Verificar:
   - **Un vendedor confirma un pedido:** con un producto de una categoría con regla, la línea guarda el porcentaje de la regla; sin regla, el del vendedor.
   - **El gerente confirma el pedido de un vendedor:** la línea guarda el porcentaje del vendedor, no el del gerente.
   - **Log:** sin errores de acceso a `sale.commission.rule`.
   - **Reporte:** en *Ventas › Reportes › Comisiones*, el vendedor sigue viendo solo sus comisiones.

**Reversión:** volver al código anterior y actualizar `sale_commission`. Vuelve el error de los vendedores, así que habría que restaurar el permiso temporal.

## Mensaje al cliente

> Buenas noches. Ya encontramos la causa del problema: la actualización de hoy al mediodía dejó a los vendedores sin un permiso que necesitan para confirmar pedidos. Activamos una solución temporal y cada vendedor ya puede confirmar sus pedidos, así que mañana a las 8:00 pueden vender con normalidad. Esta noche instalamos la corrección definitiva y revisaremos las comisiones de los pedidos que confirmó el gerente esta tarde, que pueden haber quedado con un porcentaje equivocado. Le avisamos apenas esté listo.

## Pendiente (tramo C, fuera de este hotfix)

- **Comisiones de esta tarde:** las de los pedidos que el gerente confirmó guardaron el porcentaje del gerente. Falta un script de solo lectura que las liste y un plan para corregirlas.
- **El mismo patrón en otro lugar:** `action_recompute_commissions` (*Recalcular comisiones*) calcula la comisión con otra lógica: solo la categoría exacta, sin categorías padre ni compañía. Hay que revisarlo.
- **Prevención:** las pruebas de flujos de venta deben correr con usuarios reales (no como superusuario), y la revisión de código debe exigir permisos para todos los grupos que usan un modelo nuevo.
