# Contrato de comportamiento local

Este corpus fue escrito independientemente de la implementación del intérprete. Sus 16 escenarios fijan expectativas sobre una política pequeña: autorización explícita, revocación prioritaria, suspensión, umbrales y una excepción de rol que no elimina los demás requisitos.

`decision`, `trace` y `effects` son datos simulados. Una traza `write` no ejecuta una escritura; el corpus no demuestra que un agente o API real respete la política. Los umbrales son ejemplos del contrato, no reglas universales.

Los negativos son esenciales: una política que deniega todo tampoco satisface el contrato. Conservar identificadores no preserva negación, cuantificadores u orden; por eso se comprueba la salida completa, incluidos efectos y secuencia.

## Ejecutar desde la raíz del checkout

```sh
PYTHONPATH=src python3 -m realign check --root examples/behavior --json
PYTHONPATH=src python3 -m realign mutate --root examples/behavior --policy policy.json --contract contract.json --mutations mutations.json --json
```

El corpus de mutaciones contiene nueve variantes declaradas: siete son detectadas, una numéricamente equivalente sobrevive y una es inválida. Son ocho variantes válidas, no nueve regresiones detectables. No presentar esta selección diseñada como cobertura general. La corrida no modifica la política ni el contrato.
