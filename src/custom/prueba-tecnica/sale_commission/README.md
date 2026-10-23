# Comisiones de vendedores (`sale_commission`)

Calcula la comisión del vendedor en cada línea de pedido de venta y ofrece un análisis mensual por vendedor.

## Estado por tramo (ticket T-200)

La versión 1.1.0 dejó a los vendedores sin poder confirmar pedidos. La versión **1.1.1** lo corrige con el cambio mínimo. El detalle completo está en [INCIDENT.md](INCIDENT.md).

| Tramo | Estado | Detalle |
|---|---|---|
| A | Completo | Error reproducido con un usuario vendedor. Causa raíz: faltaba el permiso de lectura de las reglas de comisión para el vendedor, y la comisión tomaba el porcentaje de quien confirma en lugar del vendedor del pedido. Corrección mínima con pruebas que fallan antes del cambio y pasan después. |
| B | Completo | Contención de los primeros 15 minutos, el commit que introdujo el error (`3f4d73f`, confirmado con `git bisect`) y por qué pasó la revisión, pasos de despliegue y verificación, y el mensaje al cliente. |
| C | Pendiente | Ver *Limitaciones conocidas y pendientes*. |

## Configuración

- **Porcentaje del vendedor:** Ajustes › Usuarios › pestaña *Comisiones* (solo gerentes de ventas).
- **Porcentaje por categoría (desde la 1.1):** Inventario/Ventas › Configuración › Categorías de producto,
  campo *Comisión (%)*. Si la categoría (o una categoría padre) tiene porcentaje, reemplaza al del vendedor.

## Cómo funciona

- Al confirmar el pedido se fija el porcentaje en cada línea y se calcula la comisión sobre el subtotal sin impuestos.
- El botón *Recalcular comisiones* del pedido vuelve a aplicar los porcentajes vigentes.
- Ventas › Reportes › *Comisiones*: tabla dinámica y gráfico por vendedor y mes. Cada vendedor ve solo lo suyo.

## Cómo probarlo

```bash
./odoo test prueba_tecnica sale_commission -d prueba_limpia
```

Son 8 pruebas y corren con usuarios reales, vendedor o gerente, no como superusuario:

- Las 4 originales, que ahora crean y confirman los pedidos como vendedor. Antes corrían como superusuario, que no revisa permisos, y por eso no detectaron el error.
- `test_t200_salesman_can_confirm` y `test_t200_salesman_can_confirm_with_category_rule`: el vendedor confirma su pedido, sin regla de categoría (5 %) y con regla (8 %).
- `test_salesman_cannot_modify_rules`: el permiso nuevo es solo de lectura.
- `test_manager_confirms_with_salesman_percent`: si el gerente confirma el pedido de un vendedor, la comisión es la del vendedor.

Para reproducir el error en la interfaz con la versión 1.1.0: entrar como vendedor (*Ventas: Usuario – solo mostrar documentos propios*), crear un pedido y pulsar **Confirmar**. Aparece el error de acceso a *Comisión por categoría de producto*. Con la 1.1.1 el pedido se confirma.

## Supuestos

- **Cambio mínimo:** es producción, así que no se reescribe el módulo. Solo se agrega el permiso de lectura y se vuelve a usar el porcentaje del vendedor del pedido.
- **La comisión es la del vendedor del pedido**, no la de quien lo confirma, como en la versión 1.0 y como dice la documentación del método.
- **El vendedor puede leer las reglas de comisión por categoría, sin modificarlas.** Es un riesgo aceptado: son los mismos porcentajes que ya ve aplicados en sus líneas. Se descartó darle el grupo del gerente o usar `sudo()`.
- **Solo se actualiza `sale_commission`.** La contención y el despliegue están en [INCIDENT.md](INCIDENT.md).

## Limitaciones conocidas y pendientes

El tramo C no está hecho:

- **Comisiones de la tarde del incidente:** los pedidos que el gerente confirmó por los vendedores guardaron el porcentaje del gerente. Falta el script de solo lectura que los liste y el plan para corregirlos.
- **El mismo patrón en otro lugar:** *Recalcular comisiones* (`action_recompute_commissions`) calcula con otra lógica: solo la categoría exacta, sin categorías padre ni compañía. No se revisó en este hotfix.
- **Prevención:** la propuesta (pruebas de flujos de venta con usuarios reales y revisar los permisos de todos los grupos que usan un modelo nuevo) está escrita en [INCIDENT.md](INCIDENT.md), pero no se aplicó como regla del equipo.
