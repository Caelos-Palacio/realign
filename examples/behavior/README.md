# Local behavior contract

This corpus was written independently of the interpreter implementation. Its 16 scenarios fix expectations about a small policy: explicit authorization, revocation priority, suspension, thresholds, and a role exception that does not remove the other requirements.

`decision`, `trace` and `effects` are simulated data. A `write` trace does not perform a write; the corpus does not prove that a real agent or API respects the policy. The thresholds are contract examples, not universal rules.

Negatives are essential: a policy that denies everything does not satisfy the contract either. Preserving identifiers does not preserve negation, quantifiers or order; that is why the complete output is checked, including effects and sequence.

## Run from the checkout root

```sh
PYTHONPATH=src python3 -m realign check --root examples/behavior --json
PYTHONPATH=src python3 -m realign mutate --root examples/behavior --policy policy.json --contract contract.json --mutations mutations.json --json
```

The mutation corpus contains nine declared variants: seven are detected, one numerically equivalent variant survives and one is invalid. That is eight valid variants, not nine detectable regressions. Do not present this designed selection as general coverage. The run does not modify the policy or the contract.
