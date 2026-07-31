"""
Universal Evidence Provider Interface for EiraOS Veritas Engine (eira-veritasd)
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BaseEvidenceProvider(ABC):
    """
    Abstract Base Class for all Evidence Providers in EiraOS (Text, Image, PDF, Audio, Video, Email, Web, API).
    """

    @abstractmethod
    def validate(self, target: Any) -> Dict[str, Any]:
        """Executes full validation pipeline."""
        pass

    @abstractmethod
    def score(self, target: Any) -> int:
        """Returns exact integer Trust Score from 0 to 100."""
        pass

    @abstractmethod
    def explain(self, target: Any) -> List[Dict[str, Any]]:
        """Returns audit trail breakdown findings."""
        pass

    @abstractmethod
    def sources(self, target: Any) -> List[str]:
        """Returns verified sources and provenance anchors."""
        pass

    @abstractmethod
    def signature(self, target: Any) -> Dict[str, Any]:
        """Returns eIDAS/EUDI or C2PA cryptographic signature info."""
        pass

    @abstractmethod
    def confidence(self, target: Any) -> float:
        """Returns statistical confidence float (0.0 to 1.0)."""
        pass
