"""Tests for sentence_split fine-segmentation module."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_module_exports_public_api():
    """Module exposes transcribe_fine_seg, word_gap_split, FineSegmentationError."""
    from asr import sentence_split
    assert callable(sentence_split.transcribe_fine_seg)
    assert callable(sentence_split.word_gap_split)
    assert issubclass(sentence_split.FineSegmentationError, Exception)
