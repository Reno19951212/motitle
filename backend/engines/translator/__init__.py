"""TranslatorEngine ABC — cross-lingual conversion (lang_X → lang_Y)."""
from abc import ABC, abstractmethod
from typing import Callable, Optional


class TranslatorEngine(ABC):
    """Cross-lingual text conversion. Per-segment 1:1; preserves timestamps."""

    @abstractmethod
    def translate(
        self,
        segments: list,
        *,
        progress: Optional[Callable] = None,
    ) -> list:
        """Per-segment 1:1; preserves timestamps; outputs target_lang text."""
