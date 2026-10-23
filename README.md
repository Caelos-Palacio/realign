# Realign

[![CI](https://github.com/Caelos-Palacio/realign/actions/workflows/ci.yml/badge.svg)](https://github.com/Caelos-Palacio/realign/actions/workflows/ci.yml)  
**English** | [Español](README.es.md)

Stop your docs and config from silently drifting away from the files they describe: Realign checks declared relations between project files and repairs only the text blocks derived from a source of truth.

![Demo: check detects drift, fix repairs the derived block, check is clean](docs/media/demo.gif)

<sub>The demo output is captured from the real CLI. Regenerate it with `python3 docs/media/demo.py capture && python3 docs/media/demo.py` (needs Pillow and ffmpeg; the generator is not part of the installed package).</sub>

<!-- realign:example-version:start -->Example version: 1.0.0<!-- realign:example-version:end -->

## Why

A version number lives in `package.json` and is copied into a README; an API version appears in two JSON files; a payload is supposed to match a schema; an agent policy is supposed to behave as specified. These relations break quietly. Realign combines a deterministic harness, a skill for investigating discrepancies, and a Git hook. Rules are data, never commands: nothing in the repository is executed.

## Quick start

Requires Python 3.11 or later. The runtime uses only the standard library.

```sh
PYTHONPATH=src python3 -m realign check --root .
PYTHONPATH=src python3 -m realign check --root examples --json
PYTHONPATH=src python3 -m realign fix --root examples --json
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The example intentionally contains a stale version block. `check` exits 1; `fix` updates the block and exits 0; running `check` again is clean. (`fix` edits `examples/README.md` in place: run `git checkout examples/README.md` afterwards to restore the stale demo.) Commands operate on saved files, including local changes not yet committed.

To install the `realign` command: `python3 -m pip install .` (package name `realign-harness`, version 0.2.0).

## Features

### Configuration

Each root has a `realign.json` with `version: 1` and a list of `rules`. Paths resolve inside that root.

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
      "template": "Version: {value}"
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

`derived` compares the JSON value of a source with a block in the target. For the id `version`, the target must contain exactly these delimiters:

```html
<!-- realign:version:start -->Version: 1.0.0<!-- realign:version:end -->
```

Only the content between delimiters may be repaired. `equal` compares JSON values without choosing which one to change. `contract` validates local JSON data against an explicit subset of JSON Schema; unsupported keywords are errors. It is not a full JSON Schema or OpenAPI validator. `behavior` relates `source` (a JSON policy) to `contract` (JSON scenarios) and never repairs either file. API contracts are represented by local files and examples: no remote API is queried.

### Repair and evidence

`check` inspects; `fix` tries to repair derived blocks; `hook` checks saved files; `hook --staged` checks a snapshot of the Git index and never repairs. `--json` returns `status` and `findings` with evidence for each discrepancy. Exit codes: 0 for `clean`/`repaired`/`complete`, 1 for `drift`/`blocked`, 2 for configuration or runtime errors.

A discrepancy in an equality or contract rule blocks repair. Authoritative sources, schemas, data and code are never modified. If delimiters are missing, the tool stops. Paths that escape the root and symbolic links are rejected. Repairs use a cooperative lock and re-check fingerprints before writing; they give no exclusion against writers that ignore the lock, so keep version control and review the diff.

### Hook and skill

To install the package locally in a virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

Copy `hooks/pre-commit` into your local Git hooks and set `REALIGN_PYTHON` to the absolute path of that environment's Python. Alternatively, set an absolute `PYTHONPATH` to Realign's `src` directory. The hook finds the root through Git; it installs no dependencies and reads no commands from stdin. Do not overwrite an existing hook: integrate it manually.

The supplied hook checks the Git index only: unstaged changes and untracked files cannot approve a commit, so the configuration and every required file must be staged. A missing `realign.json` is an error. It reads blobs from an immutable Git tree without running checkout filters, does not modify the index, and materializes only the configuration and its declared sources, targets and schemas. It rejects symbolic links or submodules in those inputs and limits them to 100 MiB / 10,000 files; files unrelated to the rules are skipped. Git must be available. The Realign code must come from a trusted installation; never point `PYTHONPATH` at an untrusted target repository (the hook runs Python with `-P` so it does not import modules from the current directory by accident). A concurrent process that changes the index after the check is outside this guarantee, and Git hooks can be skipped with `--no-verify`, so CI is still necessary.

The skill lives at `.agents/skills/realign/SKILL.md`. It guides investigation and requires acceptance criteria to be preserved; its execution depends on the host agent. The harness also works with no agent or model.

### Behavior contracts and mutations

`examples/behavior/` contains a policy and finite scenarios with `requirementId`, `given` and `expected` (decision, ordered trace and declared effects). The configuration accepts:

```json
{"id":"publication-policy","kind":"behavior","source":"examples/behavior/policy.json","contract":"examples/behavior/contract.json"}
```

The interpreter uses explicit JSON conditions and rule order; it does not understand free prose and does not run tools or effects. It checks only the declared scenarios: it does not enumerate all possible states or prove universal equivalence. A failure reports scenario, requirement, differing paths and hashes, without copying scenario values.

```sh
PYTHONPATH=src python3 -m realign mutate --root . --policy examples/behavior/policy.json --contract examples/behavior/contract.json --mutations examples/behavior/mutations.json --json
```

The corpus replaces one existing policy field per mutant; it executes no code. The original policy must pass first. Each mutation ends `killed` (a scenario detects it), `survived` (no scenario tells it apart) or `invalid` (invalid policy). A survivor may be equivalent or reveal insufficient coverage. Invalid mutants do not count as detections. `complete` exits 0 even with survivors: it is a coverage report, not a quality threshold. `mutate` requires a valid `realign.json` in the root and accepts neither `--baseline` nor `--evidence`. The bundled corpus yields 7 killed, 1 survived, 1 invalid over 16 scenarios.

### Freezing acceptance and saving evidence

```sh
PYTHONPATH=src python3 -m realign baseline --root . --baseline /path/new/acceptance.json --json
PYTHONPATH=src python3 -m realign check --root . --baseline /path/new/acceptance.json --evidence /path/new/run-001.json --json
PYTHONPATH=src python3 -m realign fix --root . --baseline /path/new/acceptance.json --json
PYTHONPATH=src python3 -m realign verify-evidence --evidence /path/new/run-001.json --json
```

The output directory must exist. Baseline capture is explicit: it freezes hashes of `realign.json`, schemas and contracts; it does not freeze data or implementation policies. Changing criteria blocks the protected check or repair. Adding a rule also changes the baseline because the whole configuration is frozen. To accept a change of intent, review the diff and capture another baseline at a new path; `fix` never updates it. Reviewing and safekeeping that baseline is the user's responsibility.

`--evidence` is optional for `check`, `fix` and `hook`, including the index with `--staged`. The installed hook writes no evidence files by default. An evidence file holds the format and tool versions, before/after input hashes, rule kinds, finite coverage, and finding codes/hashes. It omits messages and data values, facts, traces and effects; file names and identifiers remain potentially sensitive metadata. Do not publish it without review.

Artifacts are canonical JSON with a SHA-256 digest, are written whole with 0600 permissions, and never overwrite existing files or inputs. `verify-evidence` checks internal integrity of evidence files or baselines, not authenticity: anyone who can modify them can recompute the digest. They are not signatures or certificates of truth. If saving evidence fails after a repair, the output reports `operationStatus` and `repairApplied`; that failure does not roll back the repair. Fingerprints are compared during capture, but a concurrent adversarial writer is outside the guarantees.

### TDD, BDD and scope

Given/When/Then scenarios are implemented with `unittest` and JSON contracts; there is no Gherkin engine. To repair behavior: reproduce the defect with a failing test, apply a minimal change, and keep the acceptance criteria during verification. The configuration declares authority; it does not by itself prove that the authority describes the right intent. Contracts and corpora come from explicit examples, not from production provider responses.

## Limitations

- Realign does not detect every semantic divergence, does not repair business logic, does not migrate data and does not download external documentation. There is no cache or incremental checking.
- JSON decimal numbers whose conversion to float loses precision are rejected (for example `9007199254740993.0`), not silently normalized.
- A clean result means the declared rules passed; it does not certify the overall coherence of the project.
- The lock is cooperative and each replacement is atomic per file. There is no durable multi-file transaction across a process crash. Rollback restores content only if it detects no later external modification. Path and fingerprint checks reduce races but do not eliminate TOCTOU or isolate an adversarial writer running as the same user; this harness is not a security sandbox.

See also [SECURITY.md](SECURITY.md), [VERIFICATION.md](VERIFICATION.md) and [docs/DESIGN.md](docs/DESIGN.md).

## License

MIT.
