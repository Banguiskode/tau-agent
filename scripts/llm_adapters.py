#!/usr/bin/env python3
"""Adaptateurs minces Hermes/Claude Code vers la trace canonique du harness."""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def normalize_record(record: dict, source: str) -> list[dict]:
    if record.get('event') in {'session_start', 'session_end'}:
        event = record['event']
        return [{'type': event, 'status': record.get('status', 'UNKNOWN')}]
    if source == 'hermes':
        role = record.get('role')
        result = []
        if role == 'assistant':
            result.append({'type': 'assistant'})
            for call in record.get('tool_calls') or []:
                function = call.get('function') or {}
                result.append({'type': 'tool_call', 'call_id': call.get('id'),
                               'tool': function.get('name')})
            return result
        if role == 'tool':
            return [{'type': 'tool_result', 'call_id': record.get('tool_call_id'),
                     'ok': not bool(record.get('error'))}]
        if role == 'user':
            return [{'type': 'session_start'}]
        raise ValueError(f'unsupported Hermes record role: {role}')

    if source == 'claude_code':
        kind = record.get('type')
        message = record.get('message') or {}
        content = message.get('content') or []
        if kind == 'assistant':
            result = [{'type': 'assistant'}]
            result.extend({'type': 'tool_call', 'call_id': item.get('id'),
                           'tool': item.get('name')}
                          for item in content if item.get('type') == 'tool_use')
            return result
        if kind == 'user':
            result = []
            result.extend({'type': 'tool_result', 'call_id': item.get('tool_use_id'),
                           'ok': not bool(item.get('is_error'))}
                          for item in content if item.get('type') == 'tool_result')
            return result
        if kind == 'session_start':
            return [{'type': 'session_start'}]
        if kind == 'session_end':
            return [{'type': 'session_end', 'status': record.get('status', 'UNKNOWN')}]
        raise ValueError(f'unsupported Claude Code record type: {kind}')

    raise ValueError(f'unknown adapter: {source}')


def normalize_file(path: Path, source: str) -> list[dict]:
    events = []
    for line in path.read_text(errors='replace').splitlines():
        if line.strip():
            events.extend(normalize_record(json.loads(line), source))
    return events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('source', choices=['hermes', 'claude_code'])
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    events = normalize_file(args.input, args.source)
    with args.output.open('w', encoding='utf-8') as stream:
        for event in events:
            stream.write(json.dumps(event, ensure_ascii=False) + '\n')
    print(json.dumps({'source': args.source, 'events': len(events), 'output': str(args.output)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
