# AI_LOG — fleet_inspection

## Herramientas

- **Claude Code** (app de escritorio, modelo Claude Opus 5.5). Fue la única herramienta de IA que usé en este ejercicio.

## Prompts clave

1. *«Concéntrate en el segundo ejercicio… realiza un plan de acción detallado que resuelva los tramos A y B. Genera únicamente el plan, así lo revisamos juntos antes de que lo ejecutes»*.
   - Comparó el módulo con el código de Odoo 18 y armó una tabla de lo que impedía instalarlo y de lo que fallaba sin error, como `name_get`. Revisé el plan en tres versiones antes de aprobarlo: cerré las decisiones de diseño y le pedí más detalle.
2. *«Quiero poder probar el módulo de Odoo 16 antes de ejecutar cualquier cambio… ayúdame a crear otra instancia que use Odoo 16»*.
   - Levantó la instancia con su propio servicio de Postgres y midió la línea base: 9/9 pruebas y 94% de cobertura. Con eso hice pruebas funcionales en 16 y luego en 18 para comparar.
3. *«Procede con el plan»*, con puntos de control para revisar.
   - Ejecutó la migración paso a paso: pruebas que fallan antes del cambio (`'INS/2026/0004' != 'INS/2026/0004 - AB123CD'`) y pasan después, scripts de migración con pruebas, y el escenario real de actualización con 18 inspecciones, que dio 0 diferencias contra la foto previa.

## Lo que la IA hizo mal

- **Predijo mal una prueba.** Anticipó que una prueba original fallaría en Odoo 18 por el campo de solo lectura, pero pasó: el `readonly` ya estaba en la vista. Lo mostró la corrida de pruebas.
- **Se le escapó un cambio de Odoo 18 en las listas.** Pasó `<tree>` a `<list>` pero dejó `invisible="1"`, que en 18 ya no oculta la columna: las listas mostraban columnas vacías. Lo detectó más tarde, al leer el código de las listas de Odoo para la vista del catálogo, y lo corrigió en un commit aparte.
- **Versionó archivos compilados.** Un `git add -f` sobre la carpeta del módulo incluyó `__pycache__` en un commit. Lo vio en la salida de git y corrigió el commit antes de subirlo.
- **Armó mal un dato del escenario.** Cambió el tipo de una inspección en la misma transacción en que la creó, y Odoo no registra ese cambio en el chatter. Lo detectó al revisar el historial antes de migrar y lo repitió en transacciones separadas.

## Lo que escribí sin IA

- No escribí código a mano: lo generé con Claude Code.
- Las decisiones fueron mías: dónde vive el módulo, levantar Odoo 16 para tener una línea base antes de tocar nada, los textos en inglés con traducción al español, mantener la lógica original en una migración y tratar como limitación lo heredado del módulo original.
- Hice las pruebas funcionales en Odoo 16 y en Odoo 18. Con ellas encontré los problemas de visibilidad del supervisor y de acceso a los vehículos.
- Renombré a mano la copia original para comprobar que la cobertura en 0% venía del script de pruebas del repositorio y no del módulo: sin la copia duplicada, la cobertura dio 94%.
