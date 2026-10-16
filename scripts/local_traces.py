#!/usr/bin/env python3
"""Recense les sessions Hermes locales. Aucun texte, aucun argument d'outil."""
from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
import time
from collections import Counter
from pathlib import Path

from emit_tau_trace import order_packs, render_spec, render_streams, slim_kernel
from llm_adapters import normalize_hermes_session
from llm_harness import validate_trace
from run_tau_gate import run

ROOT = Path(__file__).resolve().parents[1]


def classify_errors(errors: list[str]) -> str:
    if not errors:
        return 'ok'
    first = errors[0]
    for prefix in ('trace must start', 'disallowed tool', 'missing call_id', 'duplicate call_id',
                   'orphan tool_result', 'max tool steps', 'unresolved tool_call',
                   'trace has no terminal', 'events after session_end', 'unknown event'):
        if first.startswith(prefix):
            return prefix
    return 'other'


def summarize_census(rows: list[dict]) -> dict:
    harness = Counter(row.get('harness') for row in rows)
    kernels = Counter(row.get('kernel') for row in rows)
    reasons = Counter(row.get('reason') for row in rows if row.get('harness') != 'PASS')
    judged = [row for row in rows if row.get('kernel') in {'SAT', 'UNSAT'}]
    return {
        'sessions': len(rows),
        'harness_pass': harness.get('PASS', 0),
        'harness_fail': harness.get('FAIL', 0),
        'kernel_sat': kernels.get('SAT', 0),
        'kernel_unsat': kernels.get('UNSAT', 0),
        'kernel_not_run': kernels.get('NOT_RUN', 0),
        'reasons': dict(sorted(reasons.items())),
        'status': 'PASS' if rows and judged and kernels.get('UNSAT', 0) + kernels.get('SAT', 0) == len(judged) else 'FAIL',
    }


def load_sessions(db: Path) -> list[dict]:
    uri = f'file:{db}?mode=ro'
    con = sqlite3.connect(uri, uri=True, timeout=30)
    cur = con.cursor()
    sessions = cur.execute('''
        SELECT id, ended_at IS NOT NULL, end_reason, tool_call_count
        FROM sessions WHERE tool_call_count > 0
        ORDER BY id
    ''').fetchall()
    rows = []
    for session_id, ended, end_reason, tool_count in sessions:
        messages = cur.execute('''
            SELECT role, tool_call_id, tool_calls
            FROM messages WHERE session_id=? AND active=1
            ORDER BY id
        ''', (session_id,)).fetchall()
        records = []
        for role, tool_call_id, tool_calls in messages:
            record = {'role': role, 'tool_call_id': tool_call_id}
            if tool_calls:
                record['tool_calls'] = json.loads(tool_calls)
            records.append(record)
        events = normalize_hermes_session(records, ended=bool(ended), end_reason=end_reason)
        tools = {event.get('tool') for event in events if event.get('type') == 'tool_call' and event.get('tool')}
        harness = validate_trace(events, tools, max_steps=10000)
        rows.append({
            'session_id': session_id,
            'ended': bool(ended),
            'end_reason': end_reason,
            'tool_calls': tool_count,
            'events': len(events),
            'harness': harness['status'],
            'reason': classify_errors(harness['errors']),
            'kernel': 'NOT_RUN',
            'events_data': events,
        })
    con.close()
    return rows


def judge_kernels(rows: list[dict], timeout: int, ceiling: int) -> None:
    for row in rows:
        if row['harness'] != 'PASS':
            row['kernel'] = 'NOT_RUN'
            continue
        if row['tool_calls'] > ceiling:
            row['kernel'] = 'NOT_RUN'
            row['kernel_reason'] = f'scale>{ceiling}'
            continue
        try:
            conjuncts = slim_kernel(row['events_data'])
        except ValueError as exc:
            row['kernel'] = 'NO_SPEC'
            row['kernel_error'] = str(exc)
            continue
        with tempfile.TemporaryDirectory(prefix='tau-local-') as directory:
            path = Path(directory) / 'kernel.tau'
            path.write_text(render_spec(conjuncts))
            obtained = run(path, timeout)
        row['kernel'] = obtained['obtained']
        row['wall_s'] = obtained['wall_s']
        row['tau_claim'] = 'slim_all_links'


def judge_packed(events: list[dict], timeout: int, pack: int = 24) -> dict:
    packs = order_packs(events, pack=pack)
    if not packs:
        return {'kernel': 'SAT', 'wall_s': 0.0, 'packs': 0}
    wall = 0.0
    with tempfile.TemporaryDirectory(prefix='tau-pack-') as directory:
        folder = Path(directory)
        for index, (streams, conjuncts) in enumerate(packs):
            path = folder / f'pack_{index}.tau'
            path.write_text(render_streams(streams, conjuncts))
            obtained = run(path, timeout)
            wall += obtained['wall_s']
            if obtained['obtained'] != 'SAT':
                return {'kernel': obtained['obtained'], 'wall_s': round(wall, 3), 'packs': index + 1}
    return {'kernel': 'SAT', 'wall_s': round(wall, 3), 'packs': len(packs)}


def publish(rows: list[dict]) -> dict:
    public = []
    for row in rows:
        item = {key: row[key] for key in ('session_id', 'ended', 'end_reason', 'tool_calls', 'events', 'harness', 'reason', 'kernel') if key in row}
        if 'wall_s' in row:
            item['wall_s'] = row['wall_s']
        if 'kernel_error' in row:
            item['kernel_error'] = row['kernel_error']
        if 'kernel_reason' in row:
            item['kernel_reason'] = row['kernel_reason']
        if 'tau_claim' in row:
            item['tau_claim'] = row['tau_claim']
        if 'packs' in row:
            item['packs'] = row['packs']
        public.append(item)
    summary = summarize_census(public)
    return {**summary, 'rows': public, 'content': 'absent', 'allowlist': 'observed'}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, default=Path('/root/.hermes/state.db'))
    parser.add_argument('--output', type=Path, default=ROOT / 'local_traces.json')
    parser.add_argument('--tau', action='store_true')
    parser.add_argument('--ceiling', type=int, default=6)
    parser.add_argument('--packed-ceiling', type=int, default=0)
    parser.add_argument('--timeout', type=int, default=20)
    args = parser.parse_args()
    if args.packed_ceiling and args.output.exists() and not args.tau:
        rows = json.loads(args.output.read_text())['rows']
    else:
        rows = load_sessions(args.db)
        if args.tau:
            judge_kernels(rows, args.timeout, args.ceiling)
    if args.packed_ceiling:
        fresh = {row['session_id']: row for row in load_sessions(args.db)}
        done = 0
        target = [row for row in rows if row.get('harness') == 'PASS' and row.get('kernel') == 'NOT_RUN'
                  and row['tool_calls'] <= args.packed_ceiling]
        started = time.time()
        for row in target:
            verdict = judge_packed(fresh[row['session_id']]['events_data'], args.timeout)
            row['kernel'] = verdict['kernel']
            row['wall_s'] = verdict['wall_s']
            row['packs'] = verdict['packs']
            row['tau_claim'] = 'packed_order'
            row.pop('kernel_reason', None)
            done += 1
            if done % 50 == 0 or done == len(target):
                elapsed = time.time() - started
                print(f'packed {done}/{len(target)} elapsed {elapsed:.0f}s', flush=True)
                partial = publish(rows)
                partial['packed_ceiling'] = args.packed_ceiling
                args.output.write_text(json.dumps(partial, ensure_ascii=False, indent=2) + '\n')
    report = publish(rows)
    report['ceiling'] = args.ceiling
    report['packed_ceiling'] = args.packed_ceiling
    report['kernel_form'] = 'slim<=6; packed_order' if args.packed_ceiling else 'slim'
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'sessions', 'harness_pass', 'harness_fail', 'kernel_sat', 'kernel_unsat', 'reasons')}))
    return 0 if report['harness_pass'] or report['harness_fail'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
