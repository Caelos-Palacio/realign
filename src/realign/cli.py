"""Command-line entry point for reproducible coherence checks."""
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from .harness import ConfigError, Harness, _json
from .evidence import (build_evidence, capture_baseline, input_hashes, read_artifact,
                       verify_baseline, write_artifact, validate_destination)


def _staged_report(root, operation=None):
    """Read immutable Git blobs, without checkout filters or repository code."""
    root = root.resolve()
    def git(*args):
        return subprocess.run(
            ["git", "--no-replace-objects", "-C", str(root), *args],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
        ).stdout
    tree = git("write-tree").strip().decode("ascii")
    entries = {}
    for entry in git("ls-tree", "-r", "-z", tree).split(b"\0"):
        if entry:
            metadata, name = entry.split(b"\t", 1)
            entries[os.fsdecode(name)] = metadata.split()
    with tempfile.TemporaryDirectory(prefix="realign-index-") as directory:
        snapshot = Path(directory)
        total = 0
        count = 0
        def materialize(name):
            nonlocal total, count
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ConfigError("unsafe staged path")
            if name not in entries:
                raise ConfigError(f"required file missing from index: {name}")
            mode, kind, oid = entries[name]
            if mode not in (b"100644", b"100755") or kind != b"blob":
                raise ConfigError(f"unsupported staged entry: {relative}")
            size = int(git("cat-file", "-s", oid.decode("ascii")))
            total += size
            count += 1
            if total > 100 * 1024 * 1024 or count > 10000:
                raise ConfigError("staged inputs exceed 100 MiB or 10000 files")
            content = git("cat-file", "blob", oid.decode("ascii"))
            target = snapshot / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            return content
        config = _json(materialize("realign.json"))
        needed = set()
        if isinstance(config, dict) and isinstance(config.get("rules"), list):
            for rule in config["rules"]:
                if isinstance(rule, dict):
                    for key in ("source", "target", "schema", "contract"):
                        if isinstance(rule.get(key), str):
                            needed.add(rule[key])
        for name in sorted(needed - {"realign.json"}):
            materialize(name)
        harness = Harness(snapshot)
        return operation(harness) if operation else harness.check()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="realign", description="Check project coherence and repair declared derived text.")
    parser.add_argument("command", choices=("check", "fix", "hook", "baseline", "mutate", "verify-evidence"))
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root (default: current directory)")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print JSON evidence")
    parser.add_argument("--staged", action="store_true", help="Check the Git index (hook only)")
    parser.add_argument("--baseline", type=Path, help="Capture or verify acceptance criteria")
    parser.add_argument("--evidence", type=Path, help="New evidence file, never overwritten")
    parser.add_argument("--policy", help="JSON policy relative to root, for mutate")
    parser.add_argument("--contract", help="JSON contract relative to root, for mutate")
    parser.add_argument("--mutations", help="JSON mutations relative to root, for mutate")
    args = parser.parse_args(argv)
    if args.staged and args.command != "hook":
        parser.error("--staged is only allowed with hook")
    if args.command == "baseline" and (args.baseline is None or args.evidence is not None):
        parser.error("baseline requires --baseline and does not accept --evidence")
    if args.command == "mutate" and (not all((args.policy,args.contract,args.mutations)) or args.baseline or args.evidence):
        parser.error("mutate requires --policy --contract --mutations; it does not accept baseline/evidence")
    if args.command != "mutate" and any((args.policy,args.contract,args.mutations)):
        parser.error("policy/contract/mutations are only allowed with mutate")
    if args.command == "verify-evidence" and (args.evidence is None or args.baseline):
        parser.error("verify-evidence requires --evidence and does not accept --baseline")
    try:
        def operate(harness):
            if args.command == "baseline":
                write_artifact(args.baseline, capture_baseline(harness), harness)
                return {"status":"clean","findings":[]}
            if args.baseline:
                verify_baseline(harness, read_artifact(args.baseline))
            before = input_hashes(harness) if args.evidence else None
            blocked = [args.root / name for name in (before or {})]
            if args.baseline:
                blocked.append(args.baseline)
            if args.evidence:
                validate_destination(args.evidence, harness, blocked)
            report = harness.fix() if args.command == "fix" else harness.check()
            if args.evidence:
                try:
                    after = input_hashes(harness)
                    allowed = {r['target'] for r in harness.rules if r['kind'] == 'derived'} if report['status'] == 'repaired' else set()
                    if any(after.get(name) != digest for name,digest in before.items() if name not in allowed):
                        raise ConfigError('inputs changed during evidence capture')
                    write_artifact(args.evidence, build_evidence(harness, report, before), harness, blocked)
                except (ConfigError, OSError, ValueError) as exc:
                    return {'status':'error', 'operationStatus':report['status'],
                            'repairApplied':report['status'] == 'repaired',
                            'findings':[{'code':'EVIDENCE_ERROR','message':str(exc)}]}
            return report
        if args.command == "verify-evidence":
            read_artifact(args.evidence)
            report = {"status":"clean","findings":[]}
        elif args.command == "mutate":
            from .contracts import evaluate_mutations
            # The Harness path policy rejects escaping paths and symlink inputs.
            harness = Harness(args.root)
            inputs = [_json(harness._read(harness._path(name))) for name in (args.policy,args.contract,args.mutations)]
            report = evaluate_mutations(*inputs)
        elif args.staged:
            report = _staged_report(args.root, operate)
        else:
            report = operate(Harness(args.root))
    except (ConfigError, OSError, ValueError, subprocess.SubprocessError) as exc:
        report = {"status": "error", "findings": [{"code": "ERROR", "message": str(exc)}]}
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Realign: {report['status']}")
        if args.command == "mutate":
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        for finding in report.get("findings", []):
            print(json.dumps(finding, ensure_ascii=False, sort_keys=True))
    return {"clean": 0, "repaired": 0, "drift": 1, "blocked": 1, "complete": 0}.get(report["status"], 2)
