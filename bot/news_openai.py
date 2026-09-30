"""Budgeted OpenAI lane for the existing News pipeline only."""
from __future__ import annotations

import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)
MODEL = 'gpt-6-luna'
API_ROOT = 'https://api.openai.com/v1'
_catalog = (0.0, False)


def model_preflight(*, force=False):
    """Read-only account model check. No inference, key logging or fallback model."""
    global _catalog
    if not force and time.monotonic() < _catalog[0]:
        return _catalog[1]
    key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key:
        logger.info('[news-openai] model_preflight=missing_key model=%s', MODEL)
        _catalog = (time.monotonic() + 900, False)
        return False
    try:
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            response = client.get(API_ROOT + '/models', headers={'Authorization': 'Bearer ' + key})
        if response.status_code != 200:
            logger.info('[news-openai] model_preflight=http_%s model=%s', response.status_code, MODEL)
            _catalog = (time.monotonic() + 900, False)
            return False
        models = {row.get('id') for row in response.json().get('data', []) if isinstance(row, dict)}
        available = MODEL in models
        logger.info('[news-openai] model_preflight=%s model=%s visible_models=%s',
                    'available' if available else 'unavailable', MODEL, len(models))
        _catalog = (time.monotonic() + 3600, available)
        return available
    except Exception as exc:
        logger.info('[news-openai] model_preflight=%s model=%s', type(exc).__name__, MODEL)
        _catalog = (time.monotonic() + 900, False)
        return False
