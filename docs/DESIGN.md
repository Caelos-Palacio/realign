# Diseño y garantías de Realign

Realign separa tres responsabilidades: las reglas declaran qué relaciones comprobar; el intérprete evalúa datos dentro de una gramática cerrada; el agente investiga intención y propone cambios. Una salida limpia demuestra acuerdo con las reglas disponibles, no verdad semántica general.

## Contrato independiente

Un contrato de comportamiento fija escenarios de entrada y salidas esperadas, incluyendo decisión, secuencia y efectos simulados. Las expectativas no se generan ejecutando la política evaluada. En una reparación, se preservan estos criterios. Cambiar un contrato es un cambio de intención que requiere justificación y revisión separadas, incluso si el cambio hace pasar pruebas.

Un baseline vincula bytes a una revisión; no demuestra que la revisión sea correcta, independiente o anterior a toda ejecución. No debe regenerarse automáticamente para resolver un desacuerdo. El historial de control de versiones y la revisión humana siguen importando.

## Preservación semántica acotada

La gramática explícita permite probar negación, conjunción/disyunción, comparaciones y prioridad de reglas. Las comparaciones sobre una ruta ausente devuelven falso, incluso `ne`; `exists` es verdadero para `null` presente. `not` es negación booleana, no un estado desconocido: puede invertir una comparación ausente a verdadero. Cuando la ausencia no deba permitir, declarar también existencia o igualdad positiva explícita. No interpreta libremente README ni demuestra que una política represente la intención del usuario. `trace` y `effects` son valores JSON: no ejecutan herramientas ni prueban efectos reales.

Los escenarios deben incluir límites, entradas ausentes, revocaciones, excepciones y ejemplos válidos. Un verificador que rechaza todo debe fallar por falta de resultados permitidos. Una mutación detectada significa que el corpus distingue esa alteración concreta; no mide por sí sola cobertura completa, calidad general o ausencia de mutantes equivalentes. Los resultados deben conservar denominadores y mutantes sobrevivientes.

## Coste e incrementalidad

No añadir un grafo genérico ni una caché antes de definir todas las dependencias de cada comprobación, incluida versión del intérprete, configuración, contrato y autoridad. Una caché incompleta puede convertir una regresión en un resultado limpio obsoleto. Medir por separado comprobación, evaluación, reparación y verificación, incluyendo reintentos. La inferencia libre del agente tiene un coste y garantías distintos de la evaluación determinista.

## Límites operativos

Las reparaciones automáticas siguen limitadas a bloques derivados declarados. Los contratos, autoridades y datos se verifican, nunca se modifican para conseguir verde. El bloqueo es cooperativo; no existe transacción durable multiarchivo ni aislamiento frente a un escritor adversario. El hook inspecciona una instantánea del índice, pero no impide cambios posteriores ni su omisión.

## Fundamento local

Este diseño aplica conclusiones acotadas de la investigación local: E6 mostró acuerdo de tests con un oráculo semánticamente incorrecto; E3 mostró que secuencias distintas pueden compartir estado final; E4 no demostró ahorro general por resumir; el modelo de flujo condiciona la invalidación a dependencias completas. No se reutiliza el intérprete experimental E6 como verificador validado.
