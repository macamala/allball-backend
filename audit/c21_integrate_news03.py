"""Isolated source integration only. Does not run ingestion or contact production."""
from pathlib import Path
import hashlib
import json
import subprocess

CURRENT = 'ba0b70017fa2d96717ce4c4f8e40e2ac95ec3726'
BASE = '99cc5f0a1d0951e286c58bd1176d729141a28f02'
NEWS = 'f08633d0221fbf9d9850f291dbab4ffe927c11c7'
PATHS = '''bot/feeds.py bot/fetch_sources.py bot/news_budget.py bot/news_feed_http.py
bot/news_policy.py bot/news_source_catalog.py bot/news_verified_feeds.py bot/pipeline.py
bot/rewrite_ai.py repair_content.py tests/test_news03_budget.py tests/test_news03_http.py
tests/test_news03_integration.py tests/test_news03_policy.py'''.split()
EVIDENCE = Path('evidence')


def git(*args):
    return subprocess.check_output(['git', *args])


def apply():
    branch = git('symbolic-ref', '--short', 'HEAD').decode().strip()
    assert branch == 'integration/news03-c20-20260926-21', branch
    subprocess.run(['git', 'merge-base', '--is-ancestor', CURRENT, 'HEAD'], check=True)
    EVIDENCE.mkdir(exist_ok=True)
    # No News03 target path may have changed concurrently since its frozen base.
    subprocess.run(['git', 'diff', '--exit-code', BASE, CURRENT, '--', *PATHS], check=True)
    patch = git('diff', '--binary', BASE, NEWS, '--', *PATHS)
    assert patch and patch.count(b'diff --git ') == len(PATHS)
    (EVIDENCE / 'news03-exact-delta.patch').write_bytes(patch)
    subprocess.run(['git', 'apply', '--check', 'evidence/news03-exact-delta.patch'], check=True)
    subprocess.run(['git', 'apply', 'evidence/news03-exact-delta.patch'], check=True)
    expected = {}
    for name in PATHS:
        source = git('show', f'{NEWS}:{name}')
        assert Path(name).read_bytes() == source, name
        expected[name] = hashlib.sha256(source).hexdigest()
    protected = {}
    tracked = git('ls-tree', '-r', '--name-only', CURRENT).decode().splitlines()
    for name in tracked:
        if name in PATHS:
            continue
        source = git('show', f'{CURRENT}:{name}')
        assert Path(name).read_bytes() == source, name
        protected[name] = hashlib.sha256(source).hexdigest()
    (EVIDENCE / 'news03-source-SHA256.json').write_text(json.dumps(expected, indent=2))
    (EVIDENCE / 'protected-c20-SHA256.json').write_text(json.dumps(protected, indent=2))
    (EVIDENCE / 'integration-proof.json').write_text(json.dumps({
        'c20_base': CURRENT, 'news03_base': BASE, 'news03_candidate': NEWS,
        'changed_paths': PATHS, 'protected_files_unchanged': len(protected),
        'source_delta_sha256': hashlib.sha256(patch).hexdigest(),
        'production_updated': False, 'news_started': False,
    }, indent=2))
    subprocess.run(['git', 'diff', '--check'], check=True)


def verify():
    for manifest in ('news03-source-SHA256.json', 'protected-c20-SHA256.json'):
        for name, wanted in json.loads((EVIDENCE / manifest).read_text()).items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == wanted, name


if __name__ == '__main__':
    import sys
    if sys.argv[1:] == ['--verify']:
        verify()
    elif not sys.argv[1:]:
        apply()
    else:
        raise SystemExit('unsupported mode')
