# Realign 0.2.0 local verification

Initial local verification: 2026-10-18; compatibility and release-readiness check: 2026-10-19. Remote results are in GitHub Actions.

- `PYTHONPATH=src python3 -m unittest discover -s tests -q`: **95 tests passed** on Python 3.11.16 and 3.14.
- `python3 -m compileall -q src tests` and `sh -n hooks/pre-commit`: passed.
- Real hook in temporary Git repositories: stale index / correct disk blocked; correct index / stale disk allowed; unstaged configuration rejected; names with spaces accepted; unrelated links skipped and declared links rejected. The behavior contract is read from the index. The index stays intact.
- Acceptance and evidence regressions: changing contracts after verifying the baseline blocks the repair; changing inputs after checking them prevents attaching a clean result to new hashes; an evidence failure after a repair reports that the repair was applied.
- Derived-block demo on a temporary copy: check drift/1, fix repaired/0, second check clean/0. The stale example in the checkout is kept.
- Semantic corpus: 16 explicit scenarios. Mutations: **7 killed, 1 survived, 1 invalid**. The survivor is a numerically equivalent variant within those scenarios. It is not a proof of universal equivalence.

## Installed and verified artifact

Wheel built offline with the bundled Python that contains setuptools/wheel:

```sh
python -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .
```

- File: `dist/realign_harness-0.2.0-py3-none-any.whl`.
- SHA-256: `2b31287b97a96580adcc31c582424e0c9d15166d04e74f78fd80e45a73385357`.

That same wheel was installed with `pip install --no-index --no-deps` in a temporary virtual environment. From outside the checkout, with no PYTHONPATH, the following were verified through `python -I -m realign`:

- `check --root <checkout> --json`: clean/0.
- `baseline --root <checkout> --baseline <new-temp-path> --json`: clean/0.
- `check --root <checkout> --baseline <temp-baseline> --evidence <new-temp-evidence> --json`: clean/0.
- `verify-evidence --evidence <temp-evidence> --json`: clean/0.
- `mutate --root <checkout> --policy examples/behavior/policy.json --contract examples/behavior/contract.json --mutations examples/behavior/mutations.json --json`: complete/0, distribution 7/1/1 as above.
- The installed entrypoint `realign check --root <checkout>`: clean/0.

The wheel ships modules and the entrypoint. The skill, the hook and the examples are provided in the checkout, with no automatic installation. The configured CI checks Python 3.11/3.12/3.13 on Linux and adds baseline/evidence, mutations and wheel installation; remote run results are published in GitHub Actions and not inferred from the configuration.

An evidence file's digest checks internal integrity, not authenticity. Contract effects are declared data; no real tools or external providers were invoked during these tests.

Line coverage measured with `trace --count --missing --summary` over the previous 94-test suite: contracts 89.5 %, harness 91.3 %, schema 84.7 %, evidence 91.0 % and CLI 50.0 %. CLI processes started as subprocesses are not instrumented by that measurement. Branch coverage was not measured and no aggregate percentage is presented.

The initial remote run found that Python 3.11 raises RecursionError on excessively nested JSON. It was turned into a controlled configuration error in both the normal read and the Git index read, with a real hook regression; the acceptance criterion was not reduced or skipped.
