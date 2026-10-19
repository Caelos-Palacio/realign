# Seguridad

Realign comprueba archivos declarados y contratos finitos. No es un sandbox ni una garantía de corrección semántica general. Los efectos de las políticas son datos: no ejecuta herramientas, migraciones ni comandos del proyecto.

Usa una instalación confiable del harness, revisa los contratos y conserva el baseline bajo control de cambios. Un digest detecta cambios internos, pero quien pueda sustituir el archivo también puede recalcularlo. Los bloqueos son cooperativos; los reemplazos son atómicos por archivo, sin transacción durable de varios archivos. Un escritor adversario del mismo usuario y las carreras de rutas quedan fuera de estas garantías.

El hook comprueba el índice Git y puede omitirse; complementa su uso con CI. Los expedientes omiten valores de datos, pero contienen nombres de archivos e identificadores que podrían ser sensibles. Revísalos antes de compartirlos.

## Reportar una vulnerabilidad

Usa **Security → Report a vulnerability** si GitHub muestra ese canal privado en el repositorio. Si no está disponible, abre únicamente una solicitud de contacto privado sin detalles de explotación ni datos sensibles. No publiques secretos, credenciales, archivos privados ni una reproducción que los contenga en issues o comentarios.

Incluye versión, alcance afectado y una reproducción mínima con datos ficticios por el canal privado disponible. No se promete un plazo de respuesta ni cobertura de versiones distintas de la versión más reciente.
