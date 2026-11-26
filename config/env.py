"""Configuration access: ``.env`` is the only source.

Reading the file is python-dotenv's job; this module adds the two things on top
that the project relies on:

* **no defaults.** Every value is declared in ``.env`` and read through the
  accessors below, so the file is an exhaustive description of how the project
  is configured and there is no second place a value could come from. A missing
  key raises ``ImproperlyConfigured`` instead of silently falling back to
  something else.
* **typed reads.** ``.env`` only holds strings; ``get_bool``/``get_int``/
  ``get_list`` convert them and complain about anything unparsable.
* **strict parsing.** A line python-dotenv cannot read is an error here, not
  the warning it would be by default.

Values already present in the real environment are kept as they are (dotenv's
``override=False``): that is how ``docker compose`` injects ``.env`` into the
containers, and it lets a single value be overridden for one command
(``USE_SQLITE=1 pytest``).
"""

import logging
import os
from pathlib import Path

import dotenv.main
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

ENV_FILE = BASE_DIR / '.env'

TRUE_VALUES = {'1', 'true', 'yes', 'on'}
FALSE_VALUES = {'0', 'false', 'no', 'off', ''}


class _CollectParseWarnings(logging.Handler):
    """Collects the warnings python-dotenv logs for lines it cannot parse."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def load(path: Path = ENV_FILE) -> None:
    """Load ``path`` into ``os.environ`` with python-dotenv.

    Called by ``config.settings`` and by every entry point (``manage.py``,
    ``wsgi.py``, ``asgi.py``) so the file is in place whichever way the project
    is started. Safe to call more than once.
    """
    if not path.is_file():
        raise ImproperlyConfigured(
            f'Configuration file {path} not found. Create it from the '
            f'committed template:\n\n    cp .env.example .env\n'
        )

    # python-dotenv only logs a warning for a line it cannot parse and carries
    # on. Promote that to an error: a typo must not half-configure the project,
    # and compose refuses the very same file outright.
    collected = _CollectParseWarnings()
    dotenv_logger = logging.getLogger(dotenv.main.logger.name)
    dotenv_logger.addHandler(collected)
    try:
        load_dotenv(
            dotenv_path=path,
            encoding='utf-8',
            # Real environment variables win over the file.
            override=False,
            # No ``${VAR}`` expansion, which keeps a `$` inside a password
            # intact and reads the file exactly like compose's `env_file` does.
            interpolate=False,
        )
    finally:
        dotenv_logger.removeHandler(collected)

    if collected.messages:
        details = '\n  '.join(collected.messages)
        raise ImproperlyConfigured(f'{path.name} could not be parsed:\n  {details}')

    if not os.environ.get('DJANGO_SETTINGS_MODULE'):
        raise ImproperlyConfigured(f'DJANGO_SETTINGS_MODULE is missing from {path.name}.')


def get(name: str) -> str:
    """Return the value of ``name``, which has to be declared in ``.env``."""
    try:
        return os.environ[name]
    except KeyError:
        raise ImproperlyConfigured(
            f'{name} is not configured. Add it to {ENV_FILE.name} '
            f'(see .env.example).'
        ) from None


def get_bool(name: str) -> bool:
    """Return ``name`` as a boolean."""
    value = get(name).strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    raise ImproperlyConfigured(
        f'{name} must be a boolean (one of {sorted(TRUE_VALUES | FALSE_VALUES)}), '
        f'got {value!r}.'
    )


def get_int(name: str) -> int:
    """Return ``name`` as an integer."""
    value = get(name).strip()
    try:
        return int(value)
    except ValueError:
        raise ImproperlyConfigured(f'{name} must be an integer, got {value!r}.') from None


def get_list(name: str) -> list[str]:
    """Return ``name`` as a comma separated list (empty value -> empty list)."""
    return [item.strip() for item in get(name).split(',') if item.strip()]
