"""
capabilityd — EiraOS Capability & Policy Engine Daemon
Central OS Bus for capability registration, policy checks, and provider routing.
"""
from app.core.capability import CapabilityRouter, CapabilityRequest, CapabilityType, SecurityClassification

class CapabilityDaemon:
    def __init__(self):
        self.name = "capabilityd"
        self.router = CapabilityRouter()

    def resolve_and_dispatch(self, capability_str: str, security_level_str: str) -> dict:
        try:
            cap_type = CapabilityType(capability_str)
            sec_level = SecurityClassification(security_level_str)
            
            req = CapabilityRequest(required_capability=cap_type, data_classification=sec_level)
            provider = self.router.resolve_capability(req)
            
            return {
                "status": "RESOLVED",
                "required_capability": cap_type.value,
                "security_level": sec_level.value,
                "selected_provider": provider.dict(),
                "policy_gate_passed": True
            }
        except Exception as e:
            return {"status": "POLICY_REJECTED", "error": str(e)}

if __name__ == "__main__":
    d = CapabilityDaemon()
    print(d.resolve_and_dispatch("capability:reasoning", "confidential"))
