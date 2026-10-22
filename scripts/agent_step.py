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


def _tau_bit(spec: Path, mapping: dict[str, Path], timeout: int = 20) -> int | None:
    script = spec.read_text()
    for key, path in mapping.items():
        script = script.replace(key, str(path))
    text = run_tau(script, timeout)
    if 'unsat' in text or 'Syntax Error' in text:
        return None
    return _index(mapping['BIT'], 0)


def _printed_tool(which: str, world_a: Path, world_b: Path, folder: Path) -> int | None:
    bit = folder / f'bit_{which}.out'
    if bit.exists():
        bit.unlink()
    if which == 'a':
        exists = folder / 'exists.in'
        size = folder / 'size.in'
        subprocess.run(
            ['python3', str(AGENT / 'tools' / 'observe_file.py'), str(world_a), str(exists), str(size)],
            check=False,
        )
        return _tau_bit(AGENT / 'tools' / 'file_nonempty.tau', {
            'EXISTS': exists, 'SIZE': size, 'BIT': bit,
        })
    if which == 'b':
        directory = folder / 'dir.in'
        subprocess.run(
            ['python3', str(AGENT / 'tools' / 'observe_dir.py'), str(world_b), str(directory)],
            check=False,
        )
        return _tau_bit(AGENT / 'tools' / 'path_is_dir.tau', {
            'DIR': directory, 'BIT': bit,
        })
    return None


def trace_of(done: dict) -> list[dict] | None:
    """Le trajet ne contient que les outils imprimés. Pas de fin si Tau n'a pas arrêté."""
    if done.get('printed') is None:
        return None
    events = [{'type': 'session_start'}]
    names = {'a': 'file_nonempty', 'b': 'path_is_dir'}
    if done.get('decided'):
        events.append({'type': 'assistant'})
    if done.get('ran') in names:
        events.append({'type': 'tool_call', 'tool': names[done['ran']], 'call_id': 'c0'})
        events.append({'type': 'tool_result', 'call_id': 'c0', 'ok': done.get('result') == 1})
    if done.get('followed') in names:
        events.append({'type': 'tool_call', 'tool': names[done['followed']], 'call_id': 'c1'})
        events.append({'type': 'tool_result', 'call_id': 'c1', 'ok': done.get('followed_result') == 1})
    if done.get('halted'):
        events.append({'type': 'session_end'})
    return events


def _index(path: Path, index: int) -> int | None:
    if not path.exists():
        return None
    lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    if len(lines) <= index or lines[index] not in {'0', '1'}:
        return None
    return int(lines[index])


def perform(request: int, named: int, world_a: Path, world_b: Path, timeout: int = 20) -> dict:
    """Un seul r. Ensuite, la spec de l'outil imprimé calcule le bit.
    L'hôte rapporte les faits bruts. Il ne les conjoint pas."""
    import threading
    import time

    law = (AGENT / 'live.tau').read_text()
    empty = {'printed': None, 'ran': None, 'result': None, 'next': None, 'halted': False}
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        paths = {
            'REQUEST': folder / 'request.in',
            'NAMED': folder / 'named.in',
            'DECIDE': folder / 'decide.out',
            'CALL': folder / 'call.out',
            'TOOL_A': folder / 'tool_a.out',
            'TOOL_B': folder / 'tool_b.out',
            'STOP': folder / 'stop.out',
        }
        paths['REQUEST'].write_text('1\n1\n1\n1\n' if request else '0\n0\n0\n0\n')
        paths['NAMED'].write_text(f'{named}\n0\n0\n0\n')
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
            decided = _index(paths['DECIDE'], 0) == 1
            proc.stdin.write('0\n')
            proc.stdin.flush()
            while time.time() < deadline and not seen('Execution step: 2'):
                if seen('unsat') or seen('Syntax Error'):
                    return empty
                time.sleep(0.05)
            if not seen('Execution step: 2'):
                return empty
            printed = {
                'call': _index(paths['CALL'], 1),
                'tool_a': _index(paths['TOOL_A'], 1),
                'tool_b': _index(paths['TOOL_B'], 1),
                'stop': _index(paths['STOP'], 1),
            }
            if any(value is None for value in printed.values()):
                return empty
            ran = None
            result = None
            answer = 0
            if printed['call'] == 1 and printed['tool_a'] == 1 and printed['tool_b'] == 0:
                ran = 'a'
                result = _printed_tool('a', world_a, world_b, folder)
            elif printed['call'] == 1 and printed['tool_b'] == 1 and printed['tool_a'] == 0:
                ran = 'b'
                result = _printed_tool('b', world_a, world_b, folder)
            if ran is None:
                proc.stdin.write('q\nquit\n')
                proc.stdin.flush()
                proc.stdin.close()
                proc.wait(timeout=5)
                return {
                    'printed': printed,
                    'decided': decided,
                    'ran': None,
                    'result': None,
                    'next': None,
                    'followed': None,
                    'followed_result': None,
                    'after': None,
                    'halted': False,
                }
            if result is None:
                return empty
            proc.stdin.write(f'{result}\n')
            proc.stdin.flush()
            while time.time() < deadline and not seen('Execution step: 3'):
                if seen('unsat') or seen('Syntax Error'):
                    return empty
                time.sleep(0.05)
            if not seen('Execution step: 3'):
                return empty
            nxt = {
                'call': _index(paths['CALL'], 2),
                'tool_a': _index(paths['TOOL_A'], 2),
                'tool_b': _index(paths['TOOL_B'], 2),
                'stop': _index(paths['STOP'], 2),
            }
            if any(value is None for value in nxt.values()):
                return empty
            if nxt['stop'] == 1 and nxt['call'] == 0:
                proc.stdin.write('q\nquit\n')
                proc.stdin.flush()
                proc.stdin.close()
                proc.wait(timeout=5)
                return {
                    'printed': printed,
                    'decided': decided,
                    'ran': ran,
                    'result': result,
                    'next': nxt,
                    'followed': None,
                    'followed_result': None,
                    'after': None,
                    'halted': True,
                }
            followed = None
            followed_result = None
            second_answer = 0
            if nxt['call'] == 1 and nxt['tool_a'] == 1 and nxt['tool_b'] == 0:
                followed = 'a'
                followed_result = _printed_tool('a', world_a, world_b, folder)
            elif nxt['call'] == 1 and nxt['tool_b'] == 1 and nxt['tool_a'] == 0:
                followed = 'b'
                followed_result = _printed_tool('b', world_a, world_b, folder)
            if followed is None or followed_result is None:
                if followed is not None:
                    return empty
                proc.stdin.write('q\nquit\n')
                proc.stdin.flush()
                proc.stdin.close()
                proc.wait(timeout=5)
                return {
                    'printed': printed,
                    'decided': decided,
                    'ran': ran,
                    'result': result,
                    'next': nxt,
                    'followed': None,
                    'followed_result': None,
                    'after': None,
                    'halted': False,
                }
            proc.stdin.write(f'{followed_result}\n')
            proc.stdin.flush()
            while time.time() < deadline and not seen('Execution step: 4'):
                if seen('unsat') or seen('Syntax Error'):
                    return empty
                time.sleep(0.05)
            if not seen('Execution step: 4'):
                return empty
            after = {
                'call': _index(paths['CALL'], 3),
                'tool_a': _index(paths['TOOL_A'], 3),
                'tool_b': _index(paths['TOOL_B'], 3),
                'stop': _index(paths['STOP'], 3),
            }
            if any(value is None for value in after.values()):
                return empty
            proc.stdin.write('q\nquit\n')
            proc.stdin.flush()
            proc.wait(timeout=5)
            halted = nxt['stop'] == 1 and nxt['call'] == 0
            if followed is not None:
                halted = after['stop'] == 1 and after['call'] == 0
            return {
                'printed': printed,
                'decided': decided,
                'ran': ran,
                'result': result,
                'next': nxt,
                'followed': followed,
                'followed_result': followed_result,
                'after': after,
                'halted': halted,
            }
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=2)
            for stream in (proc.stdin, proc.stdout):
                if stream:
                    try:
                        stream.close()
                    except Exception:
                        pass
