"""Read lossless API log entries without needing running AstrBot or API keys."""
import argparse
import base64
import gzip
import json
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'telegram'))
from api_log import decode_record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'logs/model-api.jsonl')
    parser.add_argument('--last', type=int, default=1)
    parser.add_argument('--id', help='Local call ID or API response ID')
    parser.add_argument('--part', choices=('all', 'request', 'response'), default='all')
    args = parser.parse_args()
    if args.last < 1:
        parser.error('--last must be positive')
    if not args.path.exists():
        print('No API calls recorded yet.', file=sys.stderr)
        return
    records = [decode_record(json.loads(line)) for line in args.path.read_bytes().splitlines() if line]
    if args.id:
        records = [r for r in records if args.id in (r.get('id'), r.get('response_id'))]
    if not records:
        print('No matching API log record (empty or already evicted).', file=sys.stderr)
        return
    for record in records[-args.last:]:
        if args.part == 'all':
            print(json.dumps(record, ensure_ascii=False, indent=2))
            continue
        part = record.get(args.part)
        if not part or 'body' not in part:
            print(json.dumps({'id': record['id'], 'state': record['state'],
                              'part': args.part, 'available': False}, ensure_ascii=False))
            continue
        raw = part['body'].encode('utf-8') if part['body_encoding'] == 'utf-8' else base64.b64decode(part['body'])
        headers = {k.lower(): v for k, v in part.get('headers', [])}
        if part.get('body_source') == 'httpx_raw_stream':
            encoding = headers.get('content-encoding', '').lower()
            if encoding == 'gzip':
                raw = gzip.decompress(raw)
            elif encoding == 'deflate':
                raw = zlib.decompress(raw)
        try:
            print(json.dumps(json.loads(raw), ensure_ascii=False, indent=2))
        except (ValueError, UnicodeError):
            print(raw.decode('utf-8', errors='replace'))


if __name__ == '__main__':
    main()
