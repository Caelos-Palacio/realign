# Verificación local de Realign 0.2.0

Verificación local inicial: 2026-10-18; comprobación de compatibilidad y preparación de publicación: 2026-10-19. Los resultados remotos se consultan en GitHub Actions.

- `PYTHONPATH=src python3 -m unittest discover -s tests -q`: **95 pruebas aprobadas** en Python 3.11.16 y 3.14.
- `python3 -m compileall -q src tests` y `sh -n hooks/pre-commit`: aprobados.
- Hook real en repositorios Git temporales: índice desfasado/disco correcto bloqueado; índice correcto/disco desfasado permitido; configuración no preparada rechazada; nombres con espacios admitidos; enlaces ajenos omitidos y enlaces declarados rechazados. El contrato de comportamiento se toma del índice. El índice permanece intacto.
- Regresiones de aceptación y evidencia: cambiar contratos tras verificar el baseline bloquea la reparación; cambiar entradas tras comprobarlas impide adjuntar un resultado limpio a hashes nuevos; un fallo de evidencia posterior a una reparación informa que la reparación se aplicó.
- Demostración derivada en copia temporal: check drift/1, fix repaired/0, segundo fix clean/0. Se conserva el ejemplo desfasado del checkout.
- Corpus semántico: 16 escenarios explícitos. Mutaciones: **7 killed, 1 survived, 1 invalid**. El superviviente es una variante numérica equivalente dentro de esos escenarios. No es una prueba de equivalencia universal.

## Artefacto instalado y comprobado

Wheel construido offline con el Python bundled que contiene setuptools/wheel:

```sh
python -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .
```

- Archivo: `dist/realign_harness-0.2.0-py3-none-any.whl`.
- SHA-256: `2b31287b97a96580adcc31c582424e0c9d15166d04e74f78fd80e45a73385357`.

Ese mismo wheel se instaló con `pip install --no-index --no-deps` en un entorno virtual temporal. Desde fuera del checkout, sin PYTHONPATH, se comprobaron mediante `python -I -m realign`:

- `check --root <checkout> --json`: clean/0.
- `baseline --root <checkout> --baseline <ruta-temporal-nueva> --json`: clean/0.
- `check --root <checkout> --baseline <baseline-temporal> --evidence <expediente-temporal-nuevo> --json`: clean/0.
- `verify-evidence --evidence <expediente-temporal> --json`: clean/0.
- `mutate --root <checkout> --policy examples/behavior/policy.json --contract examples/behavior/contract.json --mutations examples/behavior/mutations.json --json`: complete/0, distribución 7/1/1 indicada arriba.
- El entrypoint instalado `realign check --root <checkout>`: clean/0.

El wheel distribuye módulos y entrypoint. La skill, el hook y los ejemplos se suministran en el checkout, sin instalación automática. La CI configurada comprueba Python 3.11/3.12/3.13 en Linux y añade baseline/evidencia, mutaciones e instalación de wheel; los resultados de ejecución remota se publican en GitHub Actions, sin inferirlos de la configuración.

El digest de un expediente comprueba integridad interna, no autenticidad. Los efectos de los contratos son datos declarados; no se invocaron herramientas reales ni proveedores externos durante estas pruebas.

Cobertura de líneas medida mediante `trace --count --missing --summary` sobre la suite anterior de 94 pruebas: contracts 89,5 %, harness 91,3 %, schema 84,7 %, evidence 91,0 % y CLI 50,0 %. Los procesos CLI iniciados como subprocesos no están instrumentados por esa medición. No se midió cobertura de ramas ni se presenta un porcentaje agregado.

La ejecución remota inicial detectó que Python 3.11 eleva RecursionError ante JSON excesivamente anidado. Se convirtió en un error de configuración controlado tanto en la lectura normal como en el índice Git, con una regresión real del hook; no se redujo ni omitió el criterio de aceptación.
