"""
Backward-compatible extraction service shim.

The implementation now lives in app.services.extraction.
"""

from app.services.extraction import LLMUsage, extract_from_document

__all__ = ["LLMUsage", "extract_from_document"]
