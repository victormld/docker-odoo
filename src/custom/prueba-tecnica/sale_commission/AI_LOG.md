# AI_LOG — sale_commission (ticket T-200)

## Herramientas

- **Claude Code** (app de escritorio, modelo Claude Opus 5.5). Fue la única herramienta de IA que usé en este ejercicio.

## Prompts clave

1. *«Continuemos con el ejercicio 3»*, en modo de planificación: primero el plan, sin tocar nada.
   - Leyó el módulo y el historial de git y encontró la causa en el commit `3f4d73f`: la confirmación lee el modelo nuevo de reglas de comisión, que solo el gerente podía leer. También encontró una segunda regresión del mismo commit (la comisión se tomaba de quien confirma) y que ese commit había cambiado las pruebas para que corrieran como superusuario. Con eso decidí el alcance (tramos A y B), cómo corregir y que la segunda regresión fuera en un commit aparte.
2. *«Agrega que el error está en la línea de permisos del vendedor: escribió `model_sale_commission_report` en vez de `model_sale_commission_rule`»*, y después *«¿`model_sale_commission_report` ya existía antes del cambio de las 12?»*.
   - Esa era mi primera hipótesis. Antes de incluirla en el plan, la comparó con el historial: la línea es el permiso del reporte de comisiones, existe desde la versión 1.0 y el commit de las 12:00 no la tocó. Le pedí que me lo mostrara en el commit de la versión 1.0 y lo comprobé. Cambiarla habría dejado a los vendedores sin su reporte; el error real era que faltaba una línea, no que estuviera mal escrita.
3. *«Sigue con las correcciones y el INCIDENT.md, y para en el punto de control 2»*.
   - Hizo cada corrección precedida de una prueba que falla (6 de 7 con el error del ticket; luego `7.0 != 5.0` para el gerente), probó la contención en una base con el código de producción, identificó el commit culpable con `git bisect` y escribió el `INCIDENT.md`. Revisé los resultados en cada punto de control antes de seguir.
4. *«Prepara el push de hotfix/T-200 y el pull request»*.
   - Dejó el push listo en mi terminal y la página del pull request con título y descripción precargados. Lo creé yo y le pedí que verificara que había quedado bien.

## Lo que la IA hizo mal

- **El `git bisect` no evaluó el commit bueno.** Como lo marcamos como bueno al iniciar, solo probó `3f4d73f`. Para poder afirmar que la versión 1.0 pasaba, corrió la misma prueba aparte sobre `ad51040`.
- **El primer borrador del `INCIDENT.md` citaba un script que no está en el repositorio** (el del `git bisect`). Lo notó al revisarlo y lo reemplazó por la descripción del comando antes del commit.

## Lo que escribí sin IA

- No escribí código a mano: lo generé con Claude Code.
- Las decisiones fueron mías: el alcance (tramos A y B), corregir también la segunda regresión y en qué orden avanzar. La IA recomendaba usar `sudo()` solo en la búsqueda de reglas; preferí un permiso de lectura explícito, visible en la configuración de seguridad y con una prueba que demuestra que el vendedor no puede modificar las reglas.
- Reproduje el error en la interfaz con un usuario vendedor, también el 7 % que guardaba el gerente, y verifiqué la corrección en la misma base antes de subirla.
- Cuestioné el diagnóstico con mi propia hipótesis sobre la línea de permisos y la descarté después de revisar el historial.
- Creé el pull request en GitHub.
