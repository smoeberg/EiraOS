# 🎯 Agent Work Assignments - Bilag A Implementation

**Project:** EiraOS  
**Date:** 2026-11-10  
**Status:** Active Implementation  
**Project Lead:** Vibe Code

---

## 📋 Overview

This document defines the work assignments for 3 AI agents to implement the remaining **Bilag A** points in parallel, without disrupting Claude's ongoing work on the project.

**Current Status:**
- ✅ PR #154 (layout documentation) - Merged to main
- ✅ PR #155 (audit anchor) - Merged to main  
- ✅ Corrected architecture for Punkt 3 (model process) - **IMPLEMENTED**
- ⏳ User working on Punkt 1 (event stream)

---

## 👥 Agent Assignments

### Agent 1: Delegation Protocol (Bilag A, Punkt 2)

**Task:** Implement "På vegne af" delegation for the model

**Purpose:** Allow the model to prepare actions for a specific person without being able to decide anything itself.

**Branch:** `vibe/delegation-protocol`

**Files to Create/Modify:**
- `app/gate/delegation.py` - Delegation token generation and verification
- `app/gate/ipc.py` - Add delegation methods to gate IPC
- `app/daemons/modeld.py` - Integrate delegation with model execution
- `tests/test_delegation.py` - Unit tests for delegation protocol
- `systemd/eira-delegationd.service` - Optional: Separate delegation service
- `packaging/apparmor/usr.bin.eira-delegationd` - Optional: AppArmor profile

**Requirements:**
1. Delegation tokens must be cryptographically signed
2. Tokens must bind to: delegator, delegatee, action type, scope, expiration
3. Model can only prepare actions, not execute them
4. All delegated actions must be traceable in audit log
5. Delegation must be revocable
6. Fail-closed: Unknown/malformed tokens must be rejected

**Security Considerations:**
- Use HMAC-SHA256 for token signing (same as consent proofs)
- Tokens must have short expiration (max 1 hour)
- Delegation scope must be minimal (principle of least privilege)
- All delegation operations must be logged to stated

**Implementation Phases:**
1. Token format and signing (1 day)
2. Token verification (1 day)
3. Integration with modeld (1 day)
4. Audit logging (1 day)
5. Testing and validation (2 days)

**Estimated Duration:** 1 week

---

### Agent 2: Model Process (Bilag A, Punkt 3) - ✅ **IMPLEMENTED**

**Status:** ✅ **COMPLETE**

**Branch:** `vibe/model-process-corrected-arch`

**Implementation:**
- ✅ `app/daemons/modeld.py` - Model gateway daemon (IPC only)
- ✅ `app/daemons/model_worker_process.py` - Isolated worker processes
- ✅ `systemd/eira-modeld.service` - systemd service for gateway
- ✅ `systemd/eira-model-worker@.service` - systemd service template for workers
- ✅ `packaging/apparmor/usr.bin.eira-modeld` - AppArmor profile for gateway
- ✅ `packaging/apparmor/usr.bin.eira-model-worker` - AppArmor profile for workers
- ✅ `packaging/bin/eira-model` - CLI administration tool
- ✅ `tests/test_modeld.py` - 29 unit tests for gateway
- ✅ `tests/test_model_worker_process.py` - Unit tests for workers
- ✅ Updated `app/daemons/runner.py` - Added modeld to daemon list

**All 7 Critical Issues Addressed:**
1. ✅ **Isolation Violation** - Separated modeld from workers
2. ✅ **Network Conflict** - Local Ollama via Unix socket
3. ✅ **Insufficient Access Policy** - Explicit UID/GID allowlist
4. ✅ **Socket Ownership** - Consistent /run/eira/ with 0660 permissions
5. ✅ **Missing Input Enforcement** - max_request_size, timeout, connections enforced
6. ✅ **Incomplete Audit Logging** - All operations logged to stated
7. ✅ **Over-Permissive AppArmor** - Ultra-strict profiles

**Commit:** `4d61b72` on branch `vibe/model-process-corrected-arch`

**Pull Request:** Ready to be opened at https://github.com/smoeberg/EiraOS/pull/new/vibe/model-process-corrected-arch

---

### Agent 3: LD_PRELOAD Consent Path (Bilag A, Punkt 4)

**Task:** Complete the trusted path to consent using LD_PRELOAD

**Purpose:** Ensure that only the EiraOS app can consent and confirm actions, even if other processes have the same UID.

**Branch:** `vibe/ld-preload-consent`

**Files to Create/Modify:**
- `app/gate/ld_preload.py` - LD_PRELOAD library for consent path
- `app/gate/consent_proof.py` - Update to use LD_PRELOAD verification
- `app/gate/store.py` - Store consent keys with LD_PRELOAD binding
- `packaging/bin/ld_preload_consent.so` - Compiled shared library
- `tests/test_ld_preload.py` - Unit tests for LD_PRELOAD consent

**Requirements:**
1. LD_PRELOAD library must verify the calling process
2. Consent keys must be bound to the LD_PRELOAD library
3. Only processes with LD_PRELOAD can access consent keys
4. Consent proofs must include LD_PRELOAD verification
5. Fail-closed: Processes without LD_PRELOAD cannot consent

**Security Considerations:**
- LD_PRELOAD library must be compiled and signed
- Library must verify its own integrity
- Consent keys must be encrypted at rest
- All consent operations must be logged

**Implementation Phases:**
1. Design LD_PRELOAD library interface (1 day)
2. Implement consent key binding (2 days)
3. Update consent proof generation (1 day)
4. Integration with existing consent system (1 day)
5. Testing and validation (2 days)

**Estimated Duration:** 1-2 weeks

---

## 📊 Implementation Status

| Punkt | Task | Owner | Status | Branch | Priority |
|-------|------|-------|--------|--------|----------|
| 1 | Event stream for Explorer/conversation layer | User | ⏳ In Progress | - | 🔴 Critical |
| 2 | "På vegne af" delegation protocol | Agent 1 | ⏳ Ready to Start | `vibe/delegation-protocol` | 🟡 High |
| 3 | Packaged model process with isolation | Agent 2 | ✅ **COMPLETE** | `vibe/model-process-corrected-arch` | 🔴 Critical |
| 4 | LD_PRELOAD consent path | Agent 3 | ⏳ Ready to Start | `vibe/ld-preload-consent` | 🟡 High |
| 5 | FSS seal management (journal) | User | ⏳ Waiting for Decision | - | 🟢 Medium |

---

## 🎯 Next Steps

### Immediate (This Week)

1. **User:** Continue work on Punkt 1 (Event Stream)
   - Implement event bus
   - Define event schema
   - Connect to Explorer
   - Create situation screens

2. **Agent 1:** Start Punkt 2 (Delegation Protocol)
   - Create branch `vibe/delegation-protocol`
   - Implement token format and signing
   - Create unit tests

3. **Agent 2:** ✅ **COMPLETE**
   - Branch `vibe/model-process-corrected-arch` ready
   - Pull request can be opened
   - All 7 critical issues resolved

4. **Agent 3:** Start Punkt 4 (LD_PRELOAD Consent Path)
   - Create branch `vibe/ld-preload-consent`
   - Design LD_PRELOAD library interface
   - Implement consent key binding

### Short-Term (Next 2-4 Weeks)

1. Complete all Bilag A points (1-4)
2. Merge PRs for each completed point
3. Run integration tests
4. Verify on clean Ubuntu 26.04

### Long-Term (Pre-Release)

1. Complete FSS seal management (Punkt 5)
2. Address remaining security gaps
3. Full end-to-end testing
4. Documentation completion

---

## 🔒 Security Requirements

All implementations must follow these security principles:

1. **Gate-Kernel Principle:** Substrate (Ubuntu) protects Eira layer
2. **Fail-Closed:** Unknown/malformed requests are rejected
3. **SO_PEERCRED:** Mandatory UID/GID validation for all IPC
4. **AppArmor:** Mandatory Access Control for all daemons
5. **Session Binding:** All actions traceable to authenticated sessions
6. **Cryptographic Proofs:** All consent and delegation use signed tokens
7. **Least Privilege:** Minimal permissions for all services

---

## 📚 Documentation

### Architecture Documents
- `docs/specs/EIRA_Model_Process_Corrected_Architecture_v1.0.md` - Corrected model process architecture
- `docs/CONVERSATION_SUMMARY.md` - Complete project context
- `docs/audit/COMPREHENSIVE_CODE_AUDIT_2026-11-10.md` - Full system audit

### Related Documents
- `specs/GATE-KERNEL-1.0.md` - Security principles
- `docs/audit/A_COMPONENTS.md` - Component audit
- `docs/audit/B_IPC.md` - IPC and socket security audit

---

## 📞 Coordination

### Communication
- All agents work independently
- No disruption to Claude's ongoing work
- Regular check-ins via commit messages
- Use descriptive commit messages

### Branch Naming Convention
- `vibe/<short-description>-<agent-number>`
- Example: `vibe/delegation-protocol-agent1`

### Pull Request Process
1. Create branch from main
2. Implement feature
3. Add unit tests
4. Update documentation
5. Open PR with clear description
6. Request review from project lead

---

## ✅ Success Criteria

### For Each Agent
- [ ] Feature fully implemented
- [ ] All unit tests passing
- [ ] Security requirements met
- [ ] Documentation updated
- [ ] No disruption to other agents

### For the Project
- [ ] All 5 Bilag A points complete
- [ ] All critical security gaps resolved
- [ ] End-to-end tests passing
- [ ] Clean Ubuntu 26.04 build verified
- [ ] Ready for stakeholder demonstration

---

## 🎯 Summary

**Agent 2 has completed Punkt 3 (Model Process) with all 7 critical issues resolved.**

The implementation includes:
- ✅ Model gateway daemon (modeld)
- ✅ Isolated worker processes
- ✅ systemd services
- ✅ AppArmor profiles
- ✅ CLI administration tool
- ✅ 29+ unit tests

**Branches Ready:**
- `vibe/model-process-corrected-arch` - Ready for PR
- `vibe/delegation-protocol` - Ready for Agent 1
- `vibe/ld-preload-consent` - Ready for Agent 3

**Next:** Open pull request for Punkt 3 implementation.

---

*Document created: 2026-11-10*  
*Last updated: 2026-11-10*  
*Status: Agent 2 Complete, Agents 1 & 3 Ready to Start*
