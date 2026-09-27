"""News-only startup checks. No app, database, scheduler or network imports.

A mounted filesystem check is not evidence of operator approval, persistence
across deployment, an approved monetary budget or cluster-wide single ownership.
Those remain release checks. No directories/volumes or ledger are created here.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit

REQUEST_LIMITS = {'NEWS_AI_MAX_REQUESTS_PER_RUN': 20,
                  'NEWS_AI_MAX_REQUESTS_PER_DAY': 200}


def request_limits(env):
    """No implicit spend allowance from article count or a daily default."""
    values = []
    for key, maximum in REQUEST_LIMITS.items():
        value = env.get(key)
        if not isinstance(value, str):
            return None
        value = value.strip()
        if (not value or not value.isascii() or not value.isdigit()
                or len(value) > 3 or int(value) > maximum):
            return None
        values.append(int(value))
    return tuple(values)


def _absolute_path(value):
    if not isinstance(value, str) or not value or '\x00' in value:
        return None
    path = Path(value)
    if (not path.is_absolute() or '..' in path.parts or str(path) == '/'
            or value.startswith('//')):
        return None
    return path


def accounting_backend(env):
    value = str(env.get('NEWS_ACCOUNTING_BACKEND') or '').strip().lower()
    return value if value in {'file', 'postgres'} else None


def postgres_dsn(env):
    value = str(env.get('DATABASE_URL') or '').strip()
    if value.startswith('postgresql+psycopg2://'):
        value = 'postgresql://' + value[len('postgresql+psycopg2://'):]
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme not in {'postgres', 'postgresql'} or not parsed.hostname or not parsed.path.strip('/'):
        return None
    return value


def configuration_errors(env):
    errors = []
    for key in ('NEWS_HISTORICAL_REPAIR_ENABLED', 'NEWS_EXPANDED_FEEDS_ENABLED',
                'NEWS_DATA_NEWS_ENABLED', 'NEWS_TRANSLATIONS_ENABLED'):
        if env.get(key) not in ('0', '1'):
            errors.append('explicit_boolean_required:' + key)

    per_cycle = str(env.get('NEWS_TRANSLATIONS_PER_CYCLE') or '').strip()
    if (not per_cycle.isascii() or not per_cycle.isdigit()
            or not 0 <= int(per_cycle) <= 3):
        errors.append('missing_or_invalid_integer:NEWS_TRANSLATIONS_PER_CYCLE')

    try:
        max_articles = int(str(env.get('NEWS_MAX_AI_ARTICLES') or '').strip())
    except (TypeError, ValueError):
        max_articles = 0
    ai_required = bool(
        max_articles > 0
        or env.get('NEWS_TRANSLATIONS_ENABLED') == '1'
        or env.get('NEWS_HISTORICAL_REPAIR_ENABLED') == '1'
    )
    data_required = env.get('NEWS_DATA_NEWS_ENABLED') == '1'
    if not ai_required and not data_required:
        errors.append('no_news_lane_enabled')

    limits = request_limits(env)
    if ai_required:
        if limits is None:
            errors.append('explicit_news_request_limits_required')
        elif 0 in limits:
            errors.append('news_request_allowance_disabled')

        mode = str(env.get('NEWS_AI_PROVIDER_MODE') or 'xkiro_free').strip().lower()
        if mode == 'xkiro_free':
            if not str(env.get('XKIRO_API_KEY') or '').strip():
                errors.append('news_ai_key_missing')
            for key in ('NEWS_XKIRO_WRITER_MODEL', 'NEWS_XKIRO_VALIDATOR_MODEL'):
                model = str(env.get(key) or '').strip()
                if model and (not model.endswith(':free') or not re.fullmatch(r'[A-Za-z0-9._/+:-]{3,160}:free', model)):
                    errors.append('non_free_news_model_refused:' + key)
        elif mode == 'openai_legacy':
            if env.get('NEWS_ALLOW_PAID_AI') != '1' or not str(env.get('OPENAI_API_KEY') or '').strip():
                errors.append('legacy_paid_ai_not_explicitly_allowed')
        else:
            errors.append('unsupported_news_ai_provider_mode')

    backend = accounting_backend(env)
    if backend is None:
        errors.append('explicit_news_accounting_backend_required')
    elif backend == 'file':
        ledger = _absolute_path(env.get('NEWS_AI_LEDGER_PATH'))
        mount = _absolute_path(env.get('RAILWAY_VOLUME_MOUNT_PATH'))
        if ledger is None or mount is None:
            errors.append('absolute_news_ledger_and_volume_paths_required')
        elif ledger == mount or not ledger.is_relative_to(mount):
            errors.append('news_ledger_outside_volume')
    elif postgres_dsn(env) is None:
        errors.append('news_postgres_accounting_configuration_invalid')
    return errors


def storage_errors(env, *, mountinfo=None):
    """Read-only Linux mount/path checks; does not consume an AI reservation.

    mountinfo is injectable only by tests, not through an environment bypass.
    Bind mounts are read from mountinfo because ismount misses same-device binds.
    A read-only/ephemeral filesystem or an unverified nested mount fails closed.
    """
    backend = accounting_backend(env)
    if backend == 'postgres':
        return [] if postgres_dsn(env) is not None else ['news_postgres_accounting_configuration_invalid']
    if backend != 'file':
        return ['news_accounting_backend_unverified']
    ledger = _absolute_path(env.get('NEWS_AI_LEDGER_PATH'))
    mount = _absolute_path(env.get('RAILWAY_VOLUME_MOUNT_PATH'))
    if ledger is None or mount is None or ledger == mount or not ledger.is_relative_to(mount):
        return ['news_ledger_path_not_verified']
    try:
        if (not mount.is_dir() or not ledger.parent.is_dir()
                or mount.resolve(strict=True) != mount
                or ledger.parent.resolve(strict=True) != ledger.parent
                or ledger.is_symlink()):
            return ['news_ledger_path_not_verified']
        if ledger.exists():
            observed = ledger.stat()
            if not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
                return ['news_ledger_not_regular_single_file']
        if mountinfo is None:
            with open('/proc/self/mountinfo', encoding='utf-8') as handle:
                mountinfo = handle.read(1024 * 1024 + 1)
        if not isinstance(mountinfo, str) or len(mountinfo) > 1024 * 1024:
            return ['news_volume_mount_unverified']
        covering = []
        for line in mountinfo.splitlines():
            fields = line.split()
            if len(fields) < 10 or '-' not in fields:
                continue
            separator = fields.index('-')
            if separator < 6 or len(fields) <= separator + 3:
                continue
            point = Path(re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), fields[4]))
            if point.is_absolute() and ledger.is_relative_to(point):
                covering.append((point, fields[5].split(','), fields[separator + 1],
                                 fields[separator + 3].split(',')))
        if not covering:
            return ['news_volume_mount_unverified']
        longest = max(len(entry[0].parts) for entry in covering)
        selected = [entry for entry in covering if len(entry[0].parts) == longest]
        if len(selected) != 1 or selected[0][0] != mount:
            return ['news_volume_mount_unverified']
        _, options, filesystem, super_options = selected[0]
        if ('rw' not in options or 'ro' in options or 'ro' in super_options
                or filesystem in {'tmpfs', 'ramfs', 'overlay', 'squashfs'}):
            return ['news_volume_not_writable_persistent_filesystem']
        if not os.access(ledger.parent, os.W_OK | os.X_OK):
            return ['news_ledger_directory_not_writable']
    except (OSError, ValueError, RuntimeError):
        return ['news_volume_mount_unverified']
    return []


class NewsOwnerUnavailable(RuntimeError):
    """Fixed diagnostic code only; never include paths, credentials or URLs."""


@contextmanager
def _file_news_owner(ledger_path):
    path = _absolute_path(ledger_path)
    if path is None or not path.parent.is_dir() or path.parent.resolve() != path.parent:
        raise NewsOwnerUnavailable('news_owner_path_unverified')
    fd = None
    try:
        import fcntl
        fd = os.open(str(path) + '.worker.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise NewsOwnerUnavailable('news_owner_lock_not_regular')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except NewsOwnerUnavailable:
        if fd is not None:
            os.close(fd)
        raise
    except (ImportError, AttributeError, OSError):
        if fd is not None:
            os.close(fd)
        raise NewsOwnerUnavailable('news_owner_lock_unavailable') from None
    try:
        yield
    finally:
        os.close(fd)


@contextmanager
def _postgres_news_owner(env):
    dsn = postgres_dsn(env)
    if not dsn:
        raise NewsOwnerUnavailable('news_owner_postgres_unavailable')
    connection = cursor = None
    try:
        import psycopg2
        connection = psycopg2.connect(
            dsn,
            connect_timeout=5,
            application_name='ninkosports-news-owner',
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=3,
        )
        connection.autocommit = True
        cursor = connection.cursor()
        cursor.execute('SELECT pg_try_advisory_lock(%s, %s)', (240927, 1))
        row = cursor.fetchone()
        if not row or row[0] is not True:
            raise NewsOwnerUnavailable('news_owner_lock_unavailable')
        yield
    except NewsOwnerUnavailable:
        raise
    except Exception:
        raise NewsOwnerUnavailable('news_owner_postgres_unavailable') from None
    finally:
        if cursor is not None:
            try:
                cursor.execute('SELECT pg_advisory_unlock(%s, %s)', (240927, 1))
            except Exception:
                pass
            try:
                cursor.close()
            except Exception:
                pass
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


@contextmanager
def news_owner(ledger_path=None):
    """One News write owner per cycle; file mode remains for offline fixtures."""
    if ledger_path is not None:
        with _file_news_owner(ledger_path):
            yield
        return
    backend = accounting_backend(os.environ)
    if backend == 'file':
        with _file_news_owner(os.environ.get('NEWS_AI_LEDGER_PATH')):
            yield
        return
    if backend == 'postgres':
        with _postgres_news_owner(os.environ):
            yield
        return
    raise NewsOwnerUnavailable('news_owner_backend_unverified')

