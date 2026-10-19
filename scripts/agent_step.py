#!/usr/bin/env python3
"""Hôte de l'agent Tau. Il substitue les chemins, lance la spec, lit le fichier.
Il ne choisit pas la directive."""
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / 'agent'


def run_tau(script: str, timeout: int = 20) -> str:
    result = subprocess.run(
        ['tau', '-X', '-q', '-c', 'false'],
        input=script,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout + result.stderr


def stop_after_result(signal: list[int], timeout: int = 20) -> list[int] | None:
    law = (AGENT / 'stop_after_result.tau').read_text()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        signal_path = folder / 'result.in'
        directive_path = folder / 'stop.out'
        signal_path.write_text(''.join(f'{bit}\n' for bit in signal))
        script = law.replace('SIGNAL', str(signal_path)).replace('DIRECTIVE', str(directive_path))
        text = run_tau(script, timeout)
        if 'unsat' in text or 'Syntax Error' in text or not directive_path.exists():
            return None
        return [int(line) for line in directive_path.read_text().splitlines() if line.strip()]


def gate(name: str, timeout: int = 20) -> str:
    return run_tau((AGENT / name).read_text(), timeout)
