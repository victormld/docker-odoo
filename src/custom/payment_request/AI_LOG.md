# AI_LOG — payment_request

## Herramientas

- **Claude Code** (app de escritorio, modelo Claude Opus 5.5). Fue la única herramienta de IA que usé en este ejercicio.

## Prompts clave

1. *«Revisa el último ejercicio y crea un plan de acción detallado. Recuerda que este ejercicio es sobre el análisis del negocio más que de una solución de código compleja»*.
   - Revisó en el contenedor qué trae Odoo 18 antes de proponer código: *Aprobaciones* es de Enterprise, la doble validación de Compras aprueba órdenes de compra y no pagos pero `account.payment`, el chatter y las actividades se podían reutilizar. Propuso escribir el análisis y las preguntas a Carolina en el README antes de programar. Decidí el alcance (tramos A y B), los textos en inglés con traducción al español, y revisé y aprobé los 14 supuestos antes de que escribiera código.
2. *«Revisé el flujo del tramo B y, si bien se crea el registro en account.payment, no hay forma de marcar como pagado el registro»*, y las preguntas que siguieron: si se podía replicar el botón *Pagar* de las facturas, si convenía crear una factura al pagar y cómo confirmar a mano un pago *En proceso*.
   - Leyó el código de pagos de Odoo 18 y probó cada camino en transacciones revertidas: en Community el pago queda *En proceso* hasta conciliarse, y el botón *Validar* solo aparece en pagos sin asiento. Me desaconsejó crear la factura automáticamente (es un documento fiscal del proveedor: duplicaría el gasto cuando llegue la real). Evalué las alternativas y elegí que la solicitud siga el estado contable de su pago y vuelva a *Aprobada* si el pago se cancela o se rechaza.
3. *«Hay una parte del enunciado que me llama la atención: wizard de pago con diario que crea el account.payment de proveedor vinculado a la solicitud. ¿La planificación y Odoo Community lo cubren?»*.
   - Al releer los criterios del tramo B contra lo implementado, sospeché que “vinculado a la solicitud” no estaba cubierto del todo y le pedí cruzar esa frase con el código y las pruebas. Confirmó dos huecos: el vínculo iba solo de la solicitud al pago, y ninguna prueba verificaba que el pago usara el diario y la fecha del asistente. Decidí corregirlos en el mismo cambio que el estado contable del pago.


## Lo que la IA hizo mal

- **Diseñó "pagada" sin pensar en lo que contabilidad hace después.** La solicitud pasaba a *Pagada* al registrar el pago y no se enteraba si contabilidad lo cancelaba o lo rechazaba, y no previó que en Community el pago se queda *En proceso*. Salió a la luz con mis pruebas funcionales: había rechazado un pago desde contabilidad y la solicitud seguía *Pagada*.
- **Dejó el vínculo con el pago en un solo sentido**, aunque el enunciado pide que quede "vinculado a la solicitud": desde el pago no se llegaba a la solicitud. Apareció cuando le pedí cruzar esa frase del enunciado con el código.
- **Confió en que Odoo suscribe solo al solicitante.** Las pruebas desactivan esa suscripción automática y la prueba del rechazo falló: el solicitante no seguía su solicitud y no habría recibido el motivo. Se corrigió suscribiéndolo de forma explícita al enviar, en un commit `[FIX]` aparte.
- **No previó que Odoo exige el correo del usuario** para registrar mensajes y avisar de actividades. Las pruebas pasaban porque sus usuarios de prueba tienen correo; la primera prueba en la base con el plan contable real falló al enviar. Quedó como requisito en la puesta en marcha.
- **Supuso que se podía eliminar cualquier pago en las pruebas.** Odoo no deja eliminar un pago que ya tomó número si no es el último de la secuencia; la prueba falló y se rehízo con un caso realista (rechazar y después cancelar), y quedó como limitación documentada.
- **Duplicó una entrada en la traducción.** Agregó el nombre del módulo como entrada nueva, pero es el mismo texto que el menú. Lo detectó su propia validación (el conteo de textos únicos no cuadraba) y lo unió en una sola entrada.

## Lo que escribí sin IA

- No escribí código a mano: lo generé con Claude Code y revisé cada cambio.
- Las decisiones de negocio fueron mías: el alcance, aprobar los supuestos, dejar al administrador como aprobador y tesorero, que la solicitud siga el estado contable del pago en vez de crear facturas automáticas o cambiar la configuración contable, y usar solo VES.
- Hice las pruebas funcionales por rol en la base con el plan contable venezolano. Con ellas aparecieron el pago que no se podía confirmar y la solicitud que seguía pagada con su pago rechazado.
- Leí el enunciado contra la implementación y señalé la frase del vínculo con el pago, que llevó a corregir el vínculo en un solo sentido.
