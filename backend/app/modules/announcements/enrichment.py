"""
Lazy wrapper around financial_result_checker.py's ONNX FinBERT-based
classifier.

Naming correction vs. docs/requirements.md's original data contract: despite
that source file's docstring claiming "positive"/"negative" sentiment, the
actual model call (find_news_result) returns "result" or "general" -- it
classifies whether text IS a financial-result announcement, not its
polarity. So this populates `financial_result_flag`, not `sentiment_label`/
`sentiment_score` (those stay unpopulated until a real sentiment model is
wired in -- see requirements.md open-questions log).

Imported lazily, off the event loop, on first use: importing
financial_result_checker.py loads a BERT tokenizer + ONNX model at import
time (slow, and unnecessary if enrichment is never called).
"""
import logging
import threading
from typing import Optional

from app.core.legacy_path import add_legacy_root_to_path, load_legacy_env

logger = logging.getLogger("announcements.enrichment")

_module = None
_load_lock = threading.Lock()
_load_failed = False


def _get_module():
    global _module, _load_failed
    if _module is not None or _load_failed:
        return _module
    with _load_lock:
        if _module is not None or _load_failed:
            return _module
        load_legacy_env()
        add_legacy_root_to_path()
        try:
            import financial_result_checker as frc  # noqa: F401  (heavy import, intentional)
            _module = frc
        except Exception:
            logger.exception(
                "Could not load financial_result_checker.py (ONNX model/tokenizer "
                "under model/result_detection/) -- enrichment will be skipped."
            )
            _load_failed = True
    return _module


def classify_financial_result(text: str) -> Optional[int]:
    """Returns 1 if `text` looks like a financial-result announcement, 0 if
    not, None if the classifier isn't available or errored on this input."""
    module = _get_module()
    if module is None:
        return None
    result = module.find_news_result(text)
    if result == "result":
        return 1
    if result == "general":
        return 0
    logger.warning("Unexpected classifier output %r, treating as unavailable", result)
    return None
