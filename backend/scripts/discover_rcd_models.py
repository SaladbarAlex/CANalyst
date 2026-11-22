"""Snapshot the live campus model catalog without forwarding credentials on redirects.

python -m scripts.discover_rcd_models --out out/rcd_catalog_TIMESTAMP.json
Prints compatible online chat models; never calls inference or changes configuration.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def eligible_models(rows):
    return [r['id'] for r in rows
            if r.get('lifecycle') in ('active', 'active-lts', 'experimental')
            and r.get('instances_running', 0) > 0
            and 'chat_completions' in r.get('endpoints', [])]


def discover(base_url, key):
    endpoint = base_url.rstrip('/') + '/models?full=true'
    parsed = urlsplit(endpoint)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.query != 'full=true':
        raise ValueError('Use an HTTPS API base URL without credentials or query parameters')
    result = {'retrieved_at': datetime.now(timezone.utc).isoformat(), 'endpoint': endpoint}
    request = Request(endpoint, headers={'Authorization': 'Bearer ' + key})
    try:
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            catalog = json.load(response)
        # Persist only model metadata, never response headers or credential-bearing requests.
        fields = ('id', 'owned_by', 'lifecycle', 'instances_running', 'instances_pending',
                  'instances_starting', 'endpoints', 'features', 'retirement_date', 'license')
        rows = [{k: row[k] for k in fields if k in row} for row in catalog['data']]
        result.update(status='complete', models=rows, eligible_chat_models=eligible_models(rows))
    except HTTPError as error:
        target = urlsplit(error.headers.get('Location', ''))
        result.update(status='blocked', http_status=error.code,
                      redirect_host=target.hostname, redirect_path=target.path,
                      reason='Network access or authentication gate; connect to Clemson/CUVPN and retry.')
    except (URLError, TimeoutError):
        result.update(status='blocked', reason='Network connection failed; connect to Clemson/CUVPN and retry.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Output exists; choose a new snapshot filename')
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)
    key = os.environ.get('RCD_LLM_API_KEY')
    if not key:
        parser.error('RCD_LLM_API_KEY is not configured')
    result = discover(os.environ.get('RCD_LLM_BASE_URL', 'https://llm.rcd.clemson.edu/v1'), key)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if result['status'] != 'complete':
        raise SystemExit(2)
    print('RCD_LLM_MODELS=' + ','.join(result['eligible_chat_models']))


if __name__ == '__main__':
    main()
