"""
Sentiment + category classification, ported from Kite_API_31.py.

Sentiment: faithful port of cleanText() + analyseText() (an SVM + TF-IDF
vectorizer pair pickled at Trading_bot/model/sentiment/). Only ever returns
"positive" or "neutral" in the original -- preserved as-is.

Category: NOT ported -- onnx_bert.py's predict_with_onnx() is already a
clean, self-contained module (its own model/tokenizer, no side effects
beyond loading them) and is what the live pipeline actually calls
(parallel_initial_functions uses predict_with_onnx, not the separate
pickle+tfidf category model also loaded at Kite_API_31.py module level --
that second model has no caller in the live path and is not ported).

sound_alert() calls in the original (played on error, e.g. a Windows beep)
are not reproduced -- purely an audio side effect with no bearing on the
trading decision itself.
"""
import logging
import pickle
import re
import threading
from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from app.core.legacy_path import add_legacy_root_to_path

logger = logging.getLogger("announcement_trading.classification")

_lock = threading.Lock()
_svm_cls = None
_svm_vectorizer = None
_nlp = None  # spaCy, for redact_with_spacy
_load_failed = False

_onnx_predict = None
_onnx_load_failed = False


def _model_dir() -> Path:
    return get_settings().legacy_root / "model" / "sentiment"


def _ensure_sentiment_loaded() -> bool:
    global _svm_cls, _svm_vectorizer, _load_failed
    if _svm_cls is not None or _load_failed:
        return _svm_cls is not None
    with _lock:
        if _svm_cls is not None or _load_failed:
            return _svm_cls is not None
        try:
            model_dir = _model_dir()
            with open(model_dir / "svm.pickle", "rb") as f:
                _svm_cls = pickle.load(f)
            with open(model_dir / "vectorizer.pickle", "rb") as f:
                _svm_vectorizer = pickle.load(f)
        except Exception:
            logger.exception("Could not load sentiment SVM model -- sentiment will report 'neutral'")
            _load_failed = True
    return _svm_cls is not None


def _ensure_spacy_loaded():
    global _nlp
    if _nlp is not None:
        return _nlp
    with _lock:
        if _nlp is None:
            import spacy

            _nlp = spacy.load("en_core_web_sm")
    return _nlp


def clean_text(text: str) -> str:
    """Faithful port of cleanText()."""
    import nltk
    from nltk.corpus import stopwords
    from nltk.stem import WordNetLemmatizer

    lemma = WordNetLemmatizer()
    stp = stopwords.words("english")
    text = re.sub("[^a-zA-Z0-9]", " ", text)
    text = text.lower()
    text = nltk.word_tokenize(text)
    text = [lemma.lemmatize(word) for word in text]
    text = [word for word in text if word not in stp]
    return " ".join(text)


def redact_with_spacy(text: str) -> str:
    """Faithful port of redact_with_spacy() -- strips ORG entities, then
    keeps only the text after the first 'limited' (matches the original's
    behavior exactly, including that slightly odd split-on-'limited' step)."""
    nlp = _ensure_spacy_loaded()
    doc = nlp(text)
    new_string = text
    for e in reversed(doc.ents):
        if e.label_ == "ORG":
            start = e.start_char
            end = start + len(e.text)
            new_string = new_string[:start] + new_string[end:]
    return new_string.split("limited", 1)[-1]


def analyse_sentiment(text: str) -> str:
    """Faithful port of analyseText() -- returns "positive" or "neutral"."""
    if not _ensure_sentiment_loaded():
        return "neutral"
    try:
        text_copy = text
        cleaned = clean_text(text)
        vec = _svm_vectorizer.transform([cleaned])
        pred = _svm_cls.predict(vec)

        if pred[0] == 0:
            cleaned_copy = clean_text(text_copy)
            cleaned_copy = redact_with_spacy(cleaned_copy)
            vec2 = _svm_vectorizer.transform([cleaned_copy])
            pred = _svm_cls.predict(vec2)

        return "positive" if pred[0] == 1 else "neutral"
    except Exception:
        logger.exception("Error in analyse_sentiment")
        return "neutral"


def _ensure_onnx_loaded():
    global _onnx_predict, _onnx_load_failed
    if _onnx_predict is not None or _onnx_load_failed:
        return _onnx_predict
    with _lock:
        if _onnx_predict is not None or _onnx_load_failed:
            return _onnx_predict
        try:
            add_legacy_root_to_path()
            import onnx_bert

            _onnx_predict = onnx_bert.predict_with_onnx
        except Exception:
            logger.exception("Could not load onnx_bert category model -- category will report 'other'")
            _onnx_load_failed = True
    return _onnx_predict


def classify_category(text: str) -> str:
    """Wraps onnx_bert.predict_with_onnx -- the same category model the
    live pipeline actually uses. Returns "other" if the model isn't
    available rather than raising, matching the gate logic downstream that
    treats "other" as a routine skip, not an error."""
    predict = _ensure_onnx_loaded()
    if predict is None:
        return "other"
    try:
        return predict(text)
    except Exception:
        logger.exception("Error in classify_category")
        return "other"
