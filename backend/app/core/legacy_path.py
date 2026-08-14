"""
Puts LEGACY_ROOT on sys.path so module code can `import` the existing
Trading_bot scripts it wraps, without each module hardcoding its own
relative walk-up to a sibling directory.

Usage, from inside a module that needs e.g. announcement_listener_v2.py:

    from app.core.legacy_path import add_legacy_root_to_path
    add_legacy_root_to_path()
    import announcement_listener_v2  # now importable
"""
import sys

from app.core.config import get_settings

_added = False


def add_legacy_root_to_path() -> None:
    global _added
    if _added:
        return
    settings = get_settings()
    root = str(settings.legacy_root)
    if root not in sys.path:
        sys.path.insert(0, root)
    _added = True
