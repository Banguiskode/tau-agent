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


def _effect_bit(command: list[str], path: Path, timeout: int = 5) -> int | None:
    result = subprocess.run([*command, str(path)], capture_output=True, text=True, timeout=timeout)
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines or lines[0] not in {'0', '1'}:
        return None
    return int(lines[0])


def _index(path: Path, index: int) -> int | None:
    if not path.exists():
        return None
    lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    if len(lines) <= index or lines[index] not in {'0', '1'}:
        return None
    return int(lines[index])


def perform(request: int, named: int, world_a: Path, world_b: Path, timeout: int = 20, effects: dict | None = None) -> dict:
    """Un seul r. On lance l'outil imprimé, puis on envoie sa sortie.
    On ne lance pas l'autre. Une sortie qui n'est pas un bit n'est pas convertie."""
    import threading
    import time

    tools = effects or {
        'a': ['python3', str(AGENT / 'tools' / 'file_nonempty.py')],
        'b': ['python3', str(AGENT / 'tools' / 'path_is_dir.py')],
    }

    law = (AGENT / 'live.tau').read_text()
    empty = {'printed': None, 'ran': None, 'result': None, 'next': None, 'halted': False}
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        paths = {
            'REQUEST': folder / 'request.in',
            'NAMED': folder / 'named.in',
            'CALL': folder / 'call.out',
            'TOOL_A': folder / 'tool_a.out',
            'TOOL_B': folder / 'tool_b.out',
            'STOP': folder / 'stop.out',
        }
        paths['REQUEST'].write_text(f'{request}\n0\n')
        paths['NAMED'].write_text(f'{named}\n0\n')
        script = law
        for key, path in paths.items():
            script = script.replace(key, str(path))
        proc = subprocess.Popen(
            ['tau', '-X', '-q', '-c', 'false'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        out: list[str] = []

        def read() -> None:
            assert proc.stdout
            for line in proc.stdout:
                out.append(line)

        threading.Thread(target=read, daemon=True).start()
        assert proc.stdin
        try:
            proc.stdin.write(script)
            proc.stdin.flush()

            def seen(marker: str) -> bool:
                return any(marker in line for line in out)

            deadline = time.time() + timeout
            while time.time() < deadline and not seen('Execution step: 0'):
                if seen('unsat') or seen('Syntax Error'):
                    return empty
                time.sleep(0.05)
            if not seen('Execution step: 0'):
                return empty
            proc.stdin.write('0\n')
            proc.stdin.flush()
            while time.time() < deadline and not seen('Execution step: 1'):
                if seen('unsat') or seen('Syntax Error'):
                    return empty
                time.sleep(0.05)
            if not seen('Execution step: 1'):
                return empty
            printed = {
                'call': _index(paths['CALL'], 0),
                'tool_a': _index(paths['TOOL_A'], 0),
                'tool_b': _index(paths['TOOL_B'], 0),
                'stop': _index(paths['STOP'], 0),
            }
            if any(value is None for value in printed.values()):
                return empty
            ran = None
            result = None
            answer = 0
            if printed['call'] == 1 and printed['tool_a'] == 1 and printed['tool_b'] == 0:
                ran = 'a'
                result = _effect_bit(tools['a'], world_a)
            elif printed['call'] == 1 and printed['tool_b'] == 1 and printed['tool_a'] == 0:
                ran = 'b'
                result = _effect_bit(tools['b'], world_b)
            if ran is not None:
                if result is None:
                    return empty
                answer = result
            proc.stdin.write(f'{answer}\n')
            proc.stdin.flush()
            while time.time() < deadline and not seen('Execution step: 2'):
                if seen('unsat') or seen('Syntax Error'):
                    return empty
                time.sleep(0.05)
            if not seen('Execution step: 2'):
                return empty
            nxt = {
                'call': _index(paths['CALL'], 1),
                'tool_a': _index(paths['TOOL_A'], 1),
                'tool_b': _index(paths['TOOL_B'], 1),
                'stop': _index(paths['STOP'], 1),
            }
            if any(value is None for value in nxt.values()):
                return empty
            proc.stdin.write('q\nquit\n')
            proc.stdin.flush()
            proc.wait(timeout=5)
            return {
                'printed': printed,
                'ran': ran,
                'result': result,
                'next': nxt,
                'halted': nxt['stop'] == 1 and nxt['call'] == 0,
            }
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=2)
            if proc.stdin:
                proc.stdin.close()
            if proc.stdout:
                proc.stdout.close()
