"""VerifierEngine ABC — LLM-as-judge between two ASR outputs."""
from abc import ABC, abstractmethod
from typing import Callable, Optional


class VerifierEngine(ABC):
    """LLM-as-judge between primary ASR (segments) and secondary ASR (word-level).

    Output: canonical source-lang segments aligned to primary's time boundaries.
    """

    @abstractmethod
    def verify(
        self,
        primary_segments: list,
        secondary_words: list,
        *,
        progress: Optional[Callable] = None,
    ) -> list:
        """Returns canonical source-lang segments aligned to primary's time boundaries."""
