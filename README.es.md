# Realign

[![CI](https://github.com/Caelos-Palacio/realign/actions/workflows/ci.yml/badge.svg)](https://github.com/Caelos-Palacio/realign/actions/workflows/ci.yml)  
**Español** | [English](README.md)

![Demo: check detecta la deriva, fix repara el bloque derivado, check queda limpio](docs/media/demo.gif)

<sub>La salida de la demo está capturada de la CLI real. Para regenerarla: `python3 docs/media/demo.py capture && python3 docs/media/demo.py` (requiere Pillow y ffmpeg).</sub>

Comprueba relaciones declaradas entre archivos de un proyecto y repara únicamente bloques de texto derivados. Combina un harness determinista, una skill para investigar discrepancias y un hook de comprobación.

<!-- realign:example-version-es:start -->Versión del ejemplo: 1.0.0<!-- realign:example-version-es:end -->

## Inicio rápido

Requiere Python 3.11 o posterior. El runtime usa solo la biblioteca estándar.

```sh
PYTHONPATH=src python3 -m realign check --root .
PYTHONPATH=src python3 -m realign check --root examples --json
PYTHONPATH=src python3 -m realign fix --root examples --json
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

El ejemplo contiene deliberadamente una versión desfasada. `check` devuelve código 1; `fix` actualiza su bloque y devuelve 0. Otra ejecución debe quedar limpia (`fix` edita `examples/README.md` en sitio: ejecuta `git checkout examples/README.md` después para restaurar la demo desfasada). Para instalar el comando `realign`: `python3 -m pip install .`. Los comandos operan sobre archivos guardados, incluidos cambios locales aún sin commit.

## Configuración

La versión del paquete es 0.2.0. Cada raíz tiene un `realign.json` con `version: 1` y una lista `rules`. Las rutas se resuelven dentro de esa raíz. Las reglas son datos: no ejecutan comandos ni instrucciones del repositorio.

```json
{
  "version": 1,
  "rules": [
    {
      "id": "version",
      "kind": "derived",
      "source": "package.json",
      "pointer": "/version",
      "target": "README.md",
      "template": "Versión: {value}"
    },
    {
      "id": "api",
      "kind": "equal",
      "source": "api.json",
      "pointer": "/version",
      "target": "client.json",
      "targetPointer": "/apiVersion"
    },
    {
      "id": "payload",
      "kind": "contract",
      "source": "data.json",
      "schema": "schema.json"
    }
  ]
}
```

`derived` compara el valor JSON de una fuente con un bloque del destino. Para el id `version`, el destino debe contener exactamente estos delimitadores:

```html
<!-- realign:version:start -->Versión: 1.0.0<!-- realign:version:end -->
```

Solo el contenido entre delimitadores puede repararse. `equal` compara valores JSON sin elegir cuál cambiar. `contract` valida datos JSON locales con un subconjunto explícito de esquema; los keywords no soportados son errores. No es un validador completo de JSON Schema ni de OpenAPI. `behavior` relaciona `source` (política JSON) con `contract` (escenarios JSON) y nunca repara ninguno de esos archivos. Los contratos de API se representan mediante archivos y ejemplos locales: no se consulta ninguna API remota.

## Reparación y evidencia

`check` inspecciona; `fix` intenta reparar bloques derivados; `hook` comprueba archivos guardados; `hook --staged` comprueba una instantánea del índice Git y nunca repara. `--json` entrega `status` y `findings` con evidencia de cada discrepancia. Los códigos de salida son 0 para `clean`/`repaired`, 1 para `drift`/`blocked` y 2 para errores de configuración o ejecución.

Una discrepancia en una regla de igualdad o contrato bloquea la reparación. Las fuentes autoritativas, esquemas, datos y código no se modifican. Si faltan delimitadores, el sistema se detiene. Las rutas que escapan de la raíz y los enlaces simbólicos se rechazan. Las reparaciones usan un bloqueo cooperativo y vuelven a comprobar las huellas antes de escribir; no proporcionan exclusión frente a escritores que ignoren ese bloqueo; conserva control de versiones y revisa el diff.

## Hook y skill

Para instalar el paquete localmente en un entorno virtual:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

Copia `hooks/pre-commit` a tu hook Git local y configura `REALIGN_PYTHON` con la ruta absoluta del Python de ese entorno. Otra opción es configurar un `PYTHONPATH` absoluto al directorio `src` de Realign. El hook encuentra la raíz mediante Git; no instala dependencias ni lee comandos de stdin. No sobrescribas un hook existente: intégralo manualmente. El hook suministrado revisa exclusivamente el índice Git: los cambios sin preparar y los archivos no rastreados no pueden aprobar el commit. La configuración y los archivos necesarios deben estar preparados. Un `realign.json` ausente es un error. Lee blobs de un árbol Git inmutable sin ejecutar filtros de checkout, no altera el índice y materializa solamente la configuración y sus fuentes, destinos y esquemas declarados. Rechaza enlaces simbólicos o submódulos en esos inputs y limita sus blobs a 100 MiB/10 000 archivos; los archivos ajenos a las reglas se omiten. Git debe estar disponible. El código de Realign debe proceder de una instalación confiable; no configure `PYTHONPATH` hacia un repositorio objetivo no confiable. El hook usa Python `-P` para evitar importar accidentalmente módulos del directorio actual. Un proceso concurrente que cambie el índice después de la comprobación queda fuera de esta garantía; Git hooks también pueden omitirse con `--no-verify`, por lo que CI sigue siendo necesario.

La skill está en `.agents/skills/realign/SKILL.md`. Guía la investigación y exige preservar los criterios de aceptación; su ejecución depende del agente anfitrión. El harness también funciona sin agente ni modelo.

## Contratos de comportamiento y mutaciones

`examples/behavior/` contiene una política y escenarios finitos con `requirementId`, `given` y `expected` (decisión, traza ordenada y efectos declarados). La configuración admite:

```json
{"id":"publication-policy","kind":"behavior","source":"examples/behavior/policy.json","contract":"examples/behavior/contract.json"}
```

El intérprete usa condiciones JSON explícitas y orden de reglas; no entiende prosa libre ni ejecuta herramientas o efectos. Comprueba únicamente los escenarios declarados. No enumera automáticamente todos los estados posibles ni demuestra equivalencia universal. Un fallo informa escenario, requisito, rutas diferentes y hashes, sin copiar los valores del escenario.

```sh
PYTHONPATH=src python3 -m realign mutate --root . --policy examples/behavior/policy.json --contract examples/behavior/contract.json --mutations examples/behavior/mutations.json --json
```

El corpus reemplaza un campo existente de la política por mutante; no ejecuta código. La política original debe aprobar primero. Cada mutación termina `killed` (un escenario la detecta), `survived` (ningún escenario la distingue) o `invalid` (política inválida). Un superviviente puede ser equivalente o revelar cobertura insuficiente. Los inválidos no cuentan como detecciones. `complete` devuelve 0 aunque haya supervivientes: es un informe de cobertura, no un umbral de calidad. `mutate` requiere un `realign.json` válido en la raíz y no admite `--baseline` ni `--evidence`.

## Congelar aceptación y guardar evidencia

```sh
PYTHONPATH=src python3 -m realign baseline --root . --baseline /ruta/nueva/acceptance.json --json
PYTHONPATH=src python3 -m realign check --root . --baseline /ruta/nueva/acceptance.json --evidence /ruta/nueva/run-001.json --json
PYTHONPATH=src python3 -m realign fix --root . --baseline /ruta/nueva/acceptance.json --json
PYTHONPATH=src python3 -m realign verify-evidence --evidence /ruta/nueva/run-001.json --json
```

La carpeta de salida debe existir. La captura de baseline es explícita: congela hashes de `realign.json`, esquemas y contratos; no congela datos ni políticas de implementación. Cambiar criterios bloquea la comprobación o reparación protegida. Añadir una regla también cambia el baseline porque se congela la configuración completa. Para aceptar un cambio de intención, revisar el diff y capturar otro baseline en una ruta nueva; `fix` nunca lo actualiza. La revisión y custodia de ese baseline son responsabilidad del usuario.

`--evidence` es optativo para `check`, `fix` y `hook`, incluido el índice con `--staged`. El hook instalado no escribe expedientes por defecto. El expediente contiene versión del formato y de la herramienta, hashes de entradas antes/después, tipos de reglas, cobertura finita y códigos/hashes de hallazgos. Omite mensajes y valores de datos, hechos, trazas y efectos; los nombres de archivos e identificadores siguen siendo metadatos potencialmente sensibles. No debe publicarse sin revisión.

Los artefactos son JSON canónico con digest SHA-256, se publican completos con permisos 0600 y nunca sobrescriben archivos existentes ni entradas. `verify-evidence` comprueba integridad interna de expedientes o baselines, no autenticidad: alguien que pueda modificarlos puede recalcular el digest. No son firmas ni certificados de verdad. Si falla guardar evidencia después de una reparación, la salida indica `operationStatus` y `repairApplied`; ese fallo no revierte la reparación ya realizada. Se comparan huellas durante la captura, pero un escritor adversario concurrente queda fuera de las garantías.

## TDD, BDD y alcance

Los escenarios Given/When/Then se implementan con `unittest` y contratos JSON; no hay motor Gherkin. Para reparar comportamiento: reproducir el defecto mediante una prueba que falle, aplicar un cambio mínimo y conservar los criterios de aceptación durante la verificación. La configuración declara autoridad; no demuestra por sí sola que esa autoridad describa la intención correcta. Los contratos y corpus provienen de ejemplos explícitos, no de respuestas de un proveedor en producción.

Este alcance no detecta toda divergencia semántica, no repara lógica de negocio, no migra datos y no descarga documentación externa. No incluye caché ni comprobación incremental. Los números JSON decimales cuya conversión a float pierde precisión se rechazan (por ejemplo, `9007199254740993.0`); no se normalizan silenciosamente. Una salida limpia significa que las reglas declaradas aprobaron; no certifica la coherencia completa del proyecto.

Licencia MIT.

El lock es cooperativo y cada reemplazo es atómico por archivo. No hay transacción durable entre varios archivos frente a una caída del proceso. El rollback solo restaura contenido si no detecta una modificación externa posterior. Las comprobaciones de rutas y fingerprints reducen carreras, pero no eliminan TOCTOU ni aíslan un escritor adversario con el mismo usuario; este harness no es un sandbox de seguridad.
