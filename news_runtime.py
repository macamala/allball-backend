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


def configuration_errors(env):
    errors = []
    if request_limits(env) is None:
        errors.append('explicit_news_request_limits_required')
    elif 0 in request_limits(env):
        errors.append('news_request_allowance_disabled')
    if not str(env.get('OPENAI_API_KEY') or '').strip():
        errors.append('news_ai_key_missing')
    for key in ('NEWS_HISTORICAL_REPAIR_ENABLED', 'NEWS_EXPANDED_FEEDS_ENABLED'):
        if env.get(key) not in ('0', '1'):
            errors.append('explicit_boolean_required:' + key)
    ledger = _absolute_path(env.get('NEWS_AI_LEDGER_PATH'))
    mount = _absolute_path(env.get('RAILWAY_VOLUME_MOUNT_PATH'))
    if ledger is None or mount is None:
        errors.append('absolute_news_ledger_and_volume_paths_required')
    elif ledger == mount or not ledger.is_relative_to(mount):
        errors.append('news_ledger_outside_volume')
    return errors


def storage_errors(env, *, mountinfo=None):
    """Read-only Linux mount/path checks; does not consume an AI reservation.

    mountinfo is injectable only by tests, not through an environment bypass.
    Bind mounts are read from mountinfo because ismount misses same-device binds.
    A read-only/ephemeral filesystem or an unverified nested mount fails closed.
    """
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
def news_owner(ledger_path):
    """One cooperating scheduler per shared ledger file, not a multihost cap.

    Never unlink the lock file: unlinking can let another process lock a different
    inode. Closing the descriptor releases ownership even after exceptions.
    """
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
