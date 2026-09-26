"""Offline startup/storage checks; fixture paths/caps never authorize production."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import pytest

from bot.news_budget import configured_budget
from deploy.news.preflight import runtime_errors
import news_runtime as runtime


def settings(tmp_path=None):
    mount = str(tmp_path) if tmp_path else '/news-data'
    return {'NEWS_WORKER_ENABLED': '1', 'RAILWAY_SERVICE_ID': 'be857be7-a029-4663-81c7-bcde75efc482',
            'WORKER_DISABLED': '0', 'RESULTS_COLLECTION_ENABLED': '0',
            'RESULTS_SCHEDULER_ENABLED': '0', 'RESULTS_WRITE_ENABLED': '0',
            'DATABASE_URL': 'postgresql://test:NEVER_LOG_SECRET@fixture.invalid/news',
            'NEWS_FETCH_INTERVAL_MINUTES': '10', 'NEWS_MAX_AI_ARTICLES': '2',
            'NEWS_LEGACY_REPAIR_ACK': '1', 'NEWS_AI_MAX_REQUESTS_PER_RUN': '2',
            'NEWS_AI_MAX_REQUESTS_PER_DAY': '3', 'NEWS_HISTORICAL_REPAIR_ENABLED': '0',
            'NEWS_EXPANDED_FEEDS_ENABLED': '0', 'OPENAI_API_KEY': 'NEVER_LOG_KEY',
            'NEWS_AI_LEDGER_PATH': mount + '/budget.sqlite', 'RAILWAY_VOLUME_MOUNT_PATH': mount}


@pytest.mark.parametrize('missing', list(runtime.REQUEST_LIMITS))
def test_missing_explicit_limits_never_inherit_defaults(tmp_path, monkeypatch, missing):
    for key, value in settings(tmp_path).items(): monkeypatch.setenv(key, value)
    monkeypatch.delenv(missing)
    budget = configured_budget(10)
    assert budget.max_requests == 0
    assert not budget.can_start() and not budget.reserve()
    assert not (tmp_path / 'budget.sqlite').exists()


def test_legacy_ack_is_not_approval_of_missing_request_limits():
    env = settings()
    for key in runtime.REQUEST_LIMITS: env.pop(key)
    assert 'explicit_news_request_limits_required' in runtime_errors(env)


@pytest.mark.parametrize('key', list(runtime.REQUEST_LIMITS))
@pytest.mark.parametrize('value', ['', '-1', '1.0', '1_0', '９', True, None, '9' * 1000])
def test_invalid_explicit_limit_is_rejected(key, value):
    env = settings(); env[key] = value
    assert runtime.request_limits(env) is None
    assert 'explicit_news_request_limits_required' in runtime_errors(env)


@pytest.mark.parametrize('key,value', [('NEWS_AI_MAX_REQUESTS_PER_RUN','21'),
                                     ('NEWS_AI_MAX_REQUESTS_PER_DAY','201')])
def test_out_of_range_limits_are_not_clamped(key, value):
    env = settings(); env[key] = value
    assert runtime.request_limits(env) is None


@pytest.mark.parametrize('key', list(runtime.REQUEST_LIMITS))
def test_zero_limit_blocks_scheduler_before_database(key):
    env = settings(); env[key] = '0'
    assert 'news_request_allowance_disabled' in runtime_errors(env)


def test_valid_config_does_not_certify_storage_or_user_approval():
    assert runtime_errors(settings()) == []
    assert runtime.request_limits(settings()) == (2, 3)


@pytest.mark.parametrize('key', ['NEWS_HISTORICAL_REPAIR_ENABLED','NEWS_EXPANDED_FEEDS_ENABLED'])
@pytest.mark.parametrize('value', [None,'','true','false','yes','2'])
def test_history_and_expansion_flags_must_be_explicit(key, value):
    env = settings(); env[key] = value
    assert 'explicit_boolean_required:' + key in runtime_errors(env)


def mount_line(point, *, fs='ext4', options='rw,relatime', super_options='rw'):
    encoded = str(point).replace('\\', r'\134').replace(' ', r'\040')
    return f'36 25 8:1 / {encoded} {options} shared:1 - {fs} /dev/fixture {super_options}\n'


def test_existing_unmounted_directory_is_not_persistent_volume(tmp_path):
    env = settings(tmp_path)
    assert runtime.storage_errors(env, mountinfo=mount_line('/')) == ['news_volume_mount_unverified']
    assert not (tmp_path / 'budget.sqlite').exists()


def test_mounted_approved_path_is_read_only_inspection(tmp_path):
    before = set(tmp_path.iterdir())
    assert runtime.storage_errors(settings(tmp_path), mountinfo=mount_line(tmp_path)) == []
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize('fs', ['overlay', 'tmpfs', 'ramfs', 'squashfs'])
def test_ephemeral_filesystem_rejected(tmp_path, fs):
    assert runtime.storage_errors(settings(tmp_path), mountinfo=mount_line(tmp_path, fs=fs))


@pytest.mark.parametrize('options,super_options', [('ro,relatime','rw'),('rw','ro')])
def test_read_only_mount_rejected(tmp_path, options, super_options):
    assert runtime.storage_errors(settings(tmp_path), mountinfo=mount_line(tmp_path, options=options, super_options=super_options))


def test_symlinked_ledger_parent_and_file_rejected(tmp_path):
    approved = tmp_path/'approved'; approved.mkdir()
    elsewhere = tmp_path/'elsewhere'; elsewhere.mkdir()
    env = settings(approved)
    (approved/'link').symlink_to(elsewhere, target_is_directory=True)
    env['NEWS_AI_LEDGER_PATH'] = str(approved/'link'/'budget.sqlite')
    assert runtime.storage_errors(env, mountinfo=mount_line(approved))
    env['NEWS_AI_LEDGER_PATH'] = str(approved/'budget.sqlite')
    (approved/'budget.sqlite').symlink_to(elsewhere/'missing.sqlite')
    assert runtime.storage_errors(env, mountinfo=mount_line(approved))
    assert not (elsewhere/'missing.sqlite').exists()


def test_nested_mount_cannot_silently_redirect_accounting(tmp_path):
    child = tmp_path/'child'; child.mkdir()
    env = settings(tmp_path); env['NEWS_AI_LEDGER_PATH'] = str(child/'budget.sqlite')
    assert runtime.storage_errors(env, mountinfo=mount_line(tmp_path)+mount_line(child, fs='tmpfs'))


@pytest.mark.parametrize('relative', ['../outside.sqlite', 'sub/../../outside.sqlite'])
def test_parent_traversal_rejected(tmp_path, relative):
    env = settings(tmp_path); env['NEWS_AI_LEDGER_PATH'] = str(tmp_path)+'/'+relative
    assert runtime.configuration_errors(env)
    assert runtime.storage_errors(env, mountinfo=mount_line(tmp_path))


def test_similar_prefix_outside_mount_rejected(tmp_path):
    env = settings(tmp_path); env['NEWS_AI_LEDGER_PATH'] = str(tmp_path)+'-other/budget.sqlite'
    assert 'news_ledger_outside_volume' in runtime.configuration_errors(env)


def test_missing_ledger_directory_not_created(tmp_path):
    env = settings(tmp_path); env['NEWS_AI_LEDGER_PATH'] = str(tmp_path/'not-approved'/'budget.sqlite')
    assert runtime.storage_errors(env, mountinfo=mount_line(tmp_path))
    assert not (tmp_path/'not-approved').exists()


def test_escaped_mount_and_regular_file_work_without_mutation(tmp_path):
    mount = tmp_path/'with space'; mount.mkdir()
    env = settings(mount); ledger = Path(env['NEWS_AI_LEDGER_PATH']); ledger.write_bytes(b'fixture only')
    assert runtime.storage_errors(env, mountinfo=mount_line(mount)) == []
    assert ledger.read_bytes() == b'fixture only'  # No SQLite open or corruption reset.


def test_hardlinked_ledger_rejected(tmp_path):
    env = settings(tmp_path); ledger = Path(env['NEWS_AI_LEDGER_PATH']); ledger.touch()
    os.link(ledger, tmp_path/'other.sqlite')
    assert runtime.storage_errors(env, mountinfo=mount_line(tmp_path))


def test_mountinfo_unavailable_fails_closed(tmp_path, monkeypatch):
    import builtins
    def unavailable(*args, **kwargs): raise OSError('MUST_NOT_LEAK_PATH')
    monkeypatch.setattr(builtins, 'open', unavailable)
    errors = runtime.storage_errors(settings(tmp_path))
    assert errors == ['news_volume_mount_unverified']
    assert 'MUST_NOT_LEAK_PATH' not in json.dumps(errors)


def test_exceptions_do_not_leak_secrets():
    env = settings(); env['NEWS_AI_LEDGER_PATH'] = 'invalid:NEVER_LOG_SECRET'
    report = json.dumps(runtime_errors(env))
    assert 'NEVER_LOG' not in report and 'fixture.invalid' not in report


OWNER_SCRIPT = '''import sys
from news_runtime import news_owner,NewsOwnerUnavailable
try:
 with news_owner(sys.argv[1]): print('OWNED',flush=True)
except NewsOwnerUnavailable as exc:
 print(str(exc),flush=True);raise SystemExit(23)
'''


def test_shared_ledger_owner_prevents_second_process_and_releases(tmp_path):
    ledger = str(tmp_path/'ledger.sqlite')
    with runtime.news_owner(ledger):
        child = subprocess.run([sys.executable,'-c',OWNER_SCRIPT,ledger], capture_output=True,text=True,timeout=15)
        assert child.returncode == 23 and child.stdout.strip() == 'news_owner_lock_unavailable'
    assert Path(ledger+'.worker.lock').exists()  # Never unlink a flock inode.
    child = subprocess.run([sys.executable,'-c',OWNER_SCRIPT,ledger], capture_output=True,text=True,timeout=15)
    assert child.returncode == 0 and child.stdout.strip() == 'OWNED'
    assert not Path(ledger).exists()


def test_owner_released_on_exception_and_lock_symlink_rejected(tmp_path):
    ledger = str(tmp_path/'ledger.sqlite')
    with pytest.raises(ValueError):
        with runtime.news_owner(ledger): raise ValueError('test abort')
    with runtime.news_owner(ledger): pass
    second = str(tmp_path/'second.sqlite')
    Path(second+'.worker.lock').symlink_to(ledger+'.worker.lock')
    with pytest.raises(runtime.NewsOwnerUnavailable):
        with runtime.news_owner(second): pytest.fail('followed a lock symlink')


def test_unconfigured_direct_scheduler_import_and_main_do_not_import_database():
    code = '''import sys
from bot import scheduler
assert 'database' not in sys.modules
assert scheduler.main()==78
assert 'database' not in sys.modules and 'bot.fetch_sources' not in sys.modules
print('NO_DATABASE_IMPORT')'''
    env = {k:v for k,v in os.environ.items() if not k.startswith(('NEWS_','RAILWAY_','RESULTS_'))}
    env['DATABASE_URL'] = 'sqlite:///:memory:'
    child = subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True,timeout=20)
    assert child.returncode == 0, child.stderr
    assert child.stdout.strip() == 'NO_DATABASE_IMPORT'
