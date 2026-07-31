"""
EiraOS Capability Engine — Policy-First & Provider-Agnostic Routing Core
"""
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class SecurityClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"  # Requires local/offline execution
    RESTRICTED = "restricted"

class CapabilityType(str, Enum):
    REASONING = "capability:reasoning"
    TRANSLATION = "capability:translation"
    OCR = "capability:ocr"
    IDENTITY = "capability:identity"
    WALLET = "capability:wallet"
    VERITAS = "capability:veritas"
    STORAGE = "capability:storage"

class ProviderDescriptor(BaseModel):
    provider_id: str                   # e.g., "local-nllb-v2", "azure-deepl", "eudi-wallet-core"
    capability: CapabilityType
    is_local: bool                     # Runs locally on device NPU/CPU without internet?
    max_security_level: SecurityClassification
    latency_ms: int
    cost_per_op_eur: float

class CapabilityRequest(BaseModel):
    required_capability: CapabilityType
    data_classification: SecurityClassification
    max_cost_tolerance: float = 0.0     # Default 0.0 forces local/free execution if possible
    metadata: Dict[str, Any] = {}

class CapabilityRouter:
    def __init__(self):
        self._registry: Dict[CapabilityType, List[ProviderDescriptor]] = {}
        self._bootstrap_default_providers()

    def register_provider(self, descriptor: ProviderDescriptor):
        if descriptor.capability not in self._registry:
            self._registry[descriptor.capability] = []
        self._registry[descriptor.capability].append(descriptor)

    def _bootstrap_default_providers(self):
        # Register Local NPU/CPU capabilities
        self.register_provider(ProviderDescriptor(
            provider_id="local-mistral-npu",
            capability=CapabilityType.REASONING,
            is_local=True,
            max_security_level=SecurityClassification.RESTRICTED,
            latency_ms=12,
            cost_per_op_eur=0.0
        ))
        self.register_provider(ProviderDescriptor(
            provider_id="local-nllb-translator",
            capability=CapabilityType.TRANSLATION,
            is_local=True,
            max_security_level=SecurityClassification.CONFIDENTIAL,
            latency_ms=8,
            cost_per_op_eur=0.0
        ))
        self.register_provider(ProviderDescriptor(
            provider_id="veritas-proof-engine",
            capability=CapabilityType.VERITAS,
            is_local=True,
            max_security_level=SecurityClassification.RESTRICTED,
            latency_ms=2,
            cost_per_op_eur=0.0
        ))

    def resolve_capability(self, request: CapabilityRequest) -> ProviderDescriptor:
        """
        Policy-First & Provider-Agnostic Routing Engine.
        Selects the optimal provider based on security classification and cost.
        """
        candidates = self._registry.get(request.required_capability, [])
        
        # 1. Security Filtering (Policy Gate)
        valid_candidates = []
        for provider in candidates:
            if request.data_classification in [SecurityClassification.CONFIDENTIAL, SecurityClassification.RESTRICTED] and not provider.is_local:
                continue  # Reject cloud providers for confidential or restricted data!
            valid_candidates.append(provider)

        if not valid_candidates:
            raise RuntimeError(
                f"Ingen gyldig provider fundet for '{request.required_capability.value}' "
                f"med sikkerhedsniveau '{request.data_classification.value}'"
            )

        # 2. Sort by Cost -> Latency
        valid_candidates.sort(key=lambda p: (p.cost_per_op_eur, p.latency_ms))
        return valid_candidates[0]
