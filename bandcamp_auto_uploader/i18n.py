import json
from pathlib import Path


class Translator:
    """Simple JSON-based translation system. Keys are English strings, values are translations."""

    def __init__(self, lang: str = "en"):
        self.lang = lang
        self._strings: dict[str, str] = {}
        self.load()

    def load(self):
        path = Path(__file__).parent / "locales" / f"{self.lang}.json"
        if path.exists():
            with path.open(encoding="utf-8") as f:
                self._strings = json.load(f)
        else:
            self._strings = {}

    def tr(self, key: str) -> str:
        """Translate a string. Returns the translation or the original key if not found."""
        return self._strings.get(key, key)

    def reload(self):
        self.load()


# Global translator instance
_translator: Translator | None = None


def setup_translator(lang: str = "en") -> Translator:
    global _translator
    _translator = Translator(lang)
    return _translator


def get_translator() -> Translator:
    assert _translator is not None
    return _translator


def tr(key: str) -> str:
    return get_translator().tr(key)
