"""
Secrets Loader
==============
Small abstraction over secret sources. Order:
  1. environment variable
  2. .env file (if python-dotenv is present)
  3. mounted file at /run/secrets/<name>  (Docker/K8s convention)

Never read secrets from config.yml - that file is committed and
rotating it means a PR. Env + mounted files are the standard path.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_ENV_LOADED = False


def _load_dotenv_once():
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def get_secret(name: str, default=None) -> str:
    _load_dotenv_once()
    if name in os.environ:
        return os.environ[name]

    mount_path = Path(f"/run/secrets/{name}")
    if mount_path.exists():
        return mount_path.read_text().strip()

    if default is not None:
        logger.warning("secret '%s' not found, using default", name)
        return default

    raise KeyError(
        f"Secret '{name}' not set. Export as env var or mount at /run/secrets/{name}."
    )
