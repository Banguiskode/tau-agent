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


def _bit(path: Path) -> int | None:
    if not path.exists():
        return None
    lines = [line for line in path.read_text().splitlines() if line.strip()]
    if not lines or lines[0] not in {'0', '1'}:
        return None
    return int(lines[0])


def step(request: int, result: int, named: int, timeout: int = 20) -> dict | None:
    """Un pas. L'hôte écrit les signaux observés et lit l'indice 0. La ligne d'après n'est pas une directive."""
    law = (AGENT / 'step.tau').read_text()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        paths = {
            'REQUEST': folder / 'request.in',
            'RESULT': folder / 'result.in',
            'NAMED': folder / 'named.in',
            'CALL': folder / 'call.out',
            'TOOL_A': folder / 'tool_a.out',
            'TOOL_B': folder / 'tool_b.out',
            'STOP': folder / 'stop.out',
        }
        paths['REQUEST'].write_text(f'{request}\n')
        paths['RESULT'].write_text(f'{result}\n')
        paths['NAMED'].write_text(f'{named}\n')
        script = law
        for key, path in paths.items():
            script = script.replace(key, str(path))
        text = run_tau(script, timeout)
        if 'unsat' in text or 'Syntax Error' in text:
            return None
        printed = {name: _bit(paths[key]) for name, key in (
            ('call', 'CALL'), ('tool_a', 'TOOL_A'), ('tool_b', 'TOOL_B'), ('stop', 'STOP'),
        )}
        if any(value is None for value in printed.values()):
            return None
        return printed


def respond(request: int, named: int, timeout: int = 20) -> dict:
    """L'effet n'a lieu que si Tau a imprimé un seul outil. Le résultat revient comme signal."""
    printed = step(request, 0, named, timeout)
    if printed is None:
        return {'printed': None, 'ran': None, 'result': None, 'next': None, 'halted': False}
    ran = None
    result = 0
    if printed['call'] == 1 and printed['tool_a'] == 1 and printed['tool_b'] == 0:
        ran = 'a'
        result = 1
    elif printed['call'] == 1 and printed['tool_b'] == 1 and printed['tool_a'] == 0:
        ran = 'b'
        result = 1
    nxt = step(0, result, 0, timeout) if ran is not None else None
    return {
        'printed': printed,
        'ran': ran,
        'result': result if ran is not None else None,
        'next': nxt,
        'halted': nxt is not None and nxt['stop'] == 1 and nxt['call'] == 0,
    }
