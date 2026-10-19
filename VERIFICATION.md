# Verificación local de Realign 0.2.0

Fecha: 2026-10-18. No se ha publicado el paquete ni ejecutado remotamente la matriz de CI.

- `PYTHONPATH=src python3 -m unittest discover -s tests -q`: **94 pruebas aprobadas**.
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
- SHA-256: `610f810c0ffdfecb6d3efc7c10741dd42ce0de05fa54cf7a475ab342d06507f8`.

Ese mismo wheel se instaló con `pip install --no-index --no-deps` en un entorno virtual temporal. Desde fuera del checkout, sin PYTHONPATH, se comprobaron mediante `python -I -m realign`:

- `check --root <checkout> --json`: clean/0.
- `baseline --root <checkout> --baseline <ruta-temporal-nueva> --json`: clean/0.
- `check --root <checkout> --baseline <baseline-temporal> --evidence <expediente-temporal-nuevo> --json`: clean/0.
- `verify-evidence --evidence <expediente-temporal> --json`: clean/0.
- `mutate --root <checkout> --policy examples/behavior/policy.json --contract examples/behavior/contract.json --mutations examples/behavior/mutations.json --json`: complete/0, distribución 7/1/1 indicada arriba.
- El entrypoint instalado `realign check --root <checkout>`: clean/0.

El wheel distribuye módulos y entrypoint. La skill, el hook y los ejemplos se suministran en el checkout, sin instalación automática. La CI configurada comprueba Python 3.11/3.12/3.13 en Linux y añade baseline/evidencia, mutaciones e instalación de wheel; esta configuración no equivale a resultados remotos ejecutados.

El digest de un expediente comprueba integridad interna, no autenticidad. Los efectos de los contratos son datos declarados; no se invocaron herramientas reales ni proveedores externos durante estas pruebas.

Cobertura de líneas medida mediante `trace --count --missing --summary` sobre esas 94 pruebas: contracts 89,5 %, harness 91,3 %, schema 84,7 %, evidence 91,0 % y CLI 50,0 %. Los procesos CLI iniciados como subprocesos no están instrumentados por esa medición. No se midió cobertura de ramas ni se presenta un porcentaje agregado.
