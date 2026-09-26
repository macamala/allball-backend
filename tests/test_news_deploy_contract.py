import importlib.util
import json
from pathlib import Path
import sys
import pytest

SPEC = importlib.util.spec_from_file_location('news_deploy_preflight', Path(__file__).parents[1]/'deploy/news/preflight.py')
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


def artifact(tmp_path):
    for path in guard.REQUIRED_FILES:
        target=tmp_path/path
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text('# controlled backend source\n')
    return tmp_path


def good_env():
    return {'NEWS_WORKER_ENABLED':'1', 'RAILWAY_SERVICE_ID':guard.NEWS_SERVICE_ID,
            'WORKER_DISABLED':'0', 'RESULTS_COLLECTION_ENABLED':'0',
            'RESULTS_SCHEDULER_ENABLED':'0','RESULTS_WRITE_ENABLED':'0',
            'DATABASE_URL':'postgresql://user:DO_NOT_LOG@db.example/news',
            'NEWS_FETCH_INTERVAL_MINUTES':'10','NEWS_MAX_AI_ARTICLES':'2',
            'NEWS_LEGACY_REPAIR_ACK':'1',
            'NEWS_AI_MAX_REQUESTS_PER_RUN':'2','NEWS_AI_MAX_REQUESTS_PER_DAY':'3',
            'NEWS_HISTORICAL_REPAIR_ENABLED':'0','NEWS_EXPANDED_FEEDS_ENABLED':'0',
            'OPENAI_API_KEY':'FIXTURE_ONLY', 'NEWS_AI_LEDGER_PATH':'/news-data/budget.sqlite',
            'RAILWAY_VOLUME_MOUNT_PATH':'/news-data'}


def test_artifact_inspection_never_imports_backend_or_changes_env(tmp_path, monkeypatch):
    root=artifact(tmp_path)
    (root/'database.py').write_text('raise RuntimeError("MUST NOT EXECUTE")\n')
    before=set(sys.modules)
    report=guard.inspect_artifact(root, finder=lambda name: object())
    assert report['artifact_ready'] and not report['news_started']
    assert not report['runtime_health_verified']
    assert set(sys.modules)==before


def test_actual_backend_files_compile_without_a_database_configuration():
    report=guard.inspect_artifact(Path(__file__).parents[1], finder=lambda name: object())
    assert report['artifact_ready'],report


@pytest.mark.parametrize('filename',guard.REQUIRED_FILES)
def test_missing_backend_module_rejects_build(tmp_path,filename):
    root=artifact(tmp_path);(root/filename).unlink()
    assert not guard.inspect_artifact(root,finder=lambda n:object())['artifact_ready']


def test_node_context_is_not_a_news_worker(tmp_path):
    root=artifact(tmp_path)
    (root/'package.json').write_text('{"name":"allball-frontend"}')
    assert 'unexpected_node_build_context' in guard.inspect_artifact(root,finder=lambda n:object())['errors']


def test_baked_dotenv_rejected_without_reading_secret(tmp_path):
    root=artifact(tmp_path);(root/'.env').write_text('OPENAI_API_KEY=DO_NOT_LOG')
    report=guard.inspect_artifact(root,finder=lambda n:object())
    assert 'unexpected_baked_dotenv' in report['errors']
    assert 'DO_NOT_LOG' not in json.dumps(report)


def test_syntax_and_missing_dependency_fail_closed(tmp_path):
    root=artifact(tmp_path);(root/'bot/scheduler.py').write_text('def invalid(\n')
    report=guard.inspect_artifact(root,finder=lambda n:None)
    assert 'invalid_python:bot/scheduler.py' in report['errors']
    assert 'missing_dependency:apscheduler' in report['errors']


def test_disabled_default_never_executes_a_scheduler(tmp_path,capsys):
    root=artifact(tmp_path);calls=[]
    code=guard.main(['--run'],root=root,env={},finder=lambda n:object(),exec_fn=lambda *a:calls.append(a))
    assert code==78 and not calls
    report=json.loads(capsys.readouterr().out)
    assert 'news_worker_not_explicitly_enabled' in report['errors']


def test_check_does_not_require_or_echo_live_configuration(tmp_path,capsys):
    calls=[];env=good_env()
    assert guard.main(['--check'],root=artifact(tmp_path),env=env,finder=lambda n:object(),exec_fn=lambda *a:calls.append(a))==0
    text=capsys.readouterr().out
    assert 'DO_NOT_LOG' not in text and 'db.example' not in text and not calls


@pytest.mark.parametrize('key,value', [
    ('RAILWAY_SERVICE_ID','2c89eecf-b094-428a-8f7c-9642605a6baa'),
    ('RAILWAY_SERVICE_ID','c08822c6-e602-4f32-a2bc-87aedbbe9b05'),
    ('NEWS_WORKER_ENABLED','0'),('WORKER_DISABLED','true'),
    ('RESULTS_WRITE_ENABLED','true'),('RESULTS_COLLECTION_ENABLED','1'),
    ('RESULTS_SCHEDULER_ENABLED','true'),('NEWS_LEGACY_REPAIR_ACK','0'),
    ('DATABASE_URL','sqlite:///:memory:'),('DATABASE_URL','postgresql://missing-db'),
    ('NEWS_FETCH_INTERVAL_MINUTES','1'),('NEWS_FETCH_INTERVAL_MINUTES','bad'),
    ('NEWS_MAX_AI_ARTICLES',''),('NEWS_MAX_AI_ARTICLES','100'),
])
def test_unsafe_runtime_configuration_rejected(key,value):
    env=good_env();env[key]=value
    assert guard.runtime_errors(env)


@pytest.mark.parametrize('flag', ['WORKER_DISABLED','RESULTS_WRITE_ENABLED','RESULTS_COLLECTION_ENABLED','RESULTS_SCHEDULER_ENABLED'])
def test_missing_flags_do_not_inherit_dangerous_defaults(flag):
    env=good_env();del env[flag]
    assert f'must_be_explicitly_false:{flag}' in guard.runtime_errors(env)


def test_enabled_guard_executes_only_existing_news_entrypoint(tmp_path,monkeypatch,capsys):
    root=artifact(tmp_path);calls=[];dirs=[]
    monkeypatch.setattr(guard.os,'chdir',lambda path:dirs.append(path))
    # This remains an exec-target unit test; actual mounts have dedicated tests.
    import news_runtime
    monkeypatch.setattr(news_runtime,'storage_errors',lambda env:[])
    assert guard.main(['--run'],root=root,env=good_env(),finder=lambda n:object(),exec_fn=lambda *a:calls.append(a))==0
    assert calls==[(sys.executable,[sys.executable,'-m','bot.scheduler'])]
    assert dirs==[root] and 'DO_NOT_LOG' not in capsys.readouterr().out


def test_existing_api_and_scores_have_no_default_build_config_changes():
    root=Path(__file__).parents[1]
    assert not (root/'Dockerfile').exists()
    assert not (root/'railway.toml').exists()
    assert not (root/'railway.json').exists()
    recipe=(root/'deploy/news/Dockerfile').read_text()
    assert 'COPY . .' not in recipe and 'COPY collector' not in recipe
    assert 'preflight.py", "--run"' in recipe
