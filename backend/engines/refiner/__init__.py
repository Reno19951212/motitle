"""RefinerEngine ABC — same-lingual polish (broadcast register, glossary, disfluency)."""
from abc import ABC, abstractmethod
from typing import Callable, Optional


class RefinerEngine(ABC):
    """Same-lingual polish. Per-segment 1:1; same lang in/out; preserves timestamps."""

    @abstractmethod
    def refine(
        self,
        segments: list,
        *,
        progress: Optional[Callable] = None,
    ) -> list:
        """Per-segment 1:1; same lang in/out; preserves timestamps."""
