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

from dotenv import load_dotenv

from app.core.config import get_settings

_path_added = False
_ntt_path_added = False
_env_loaded = False


def add_legacy_root_to_path() -> None:
    global _path_added
    if _path_added:
        return
    settings = get_settings()
    root = str(settings.legacy_root)
    if root not in sys.path:
        sys.path.insert(0, root)
    _path_added = True


def add_new_trade_tool_root_to_path() -> None:
    """Module C (Equity Trading) wraps new_trade_tool, which has its own
    common.py/utils_time.py/db.py distinct from the ones at LEGACY_ROOT --
    needs its own sys.path entry."""
    global _ntt_path_added
    if _ntt_path_added:
        return
    settings = get_settings()
    root = str(settings.new_trade_tool_root)
    if root not in sys.path:
        sys.path.insert(0, root)
    _ntt_path_added = True


def load_legacy_env() -> None:
    """Load Trading_bot/.env into this process's environment (without
    overriding anything already set, e.g. by aitrade's own backend/.env).

    Legacy scripts like announcement_listener_v2.py call load_dotenv() on
    import too, but that searches upward from the current working directory
    -- which won't find Trading_bot/.env when uvicorn runs from a sibling
    directory (aitrade/backend). Loading it explicitly here, before
    importing any legacy module that needs it, makes their own load_dotenv()
    call a harmless no-op instead of leaving required vars (e.g.
    TRUEDATA_AUTH_TOKEN) unset.
    """
    global _env_loaded
    if _env_loaded:
        return
    settings = get_settings()
    load_dotenv(dotenv_path=settings.legacy_root / ".env", override=False)
    _env_loaded = True
