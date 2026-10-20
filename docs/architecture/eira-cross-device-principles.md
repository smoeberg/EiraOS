# Eira Cross-Device Principles

**Status:** Proposed architecture direction  
**Implementation status:** This document records product and architecture intent. It does not claim that mobile apps, synchronization, or device pairing are implemented.

## Product direction

EiraOS should be designed as a coherent experience across PC and mobile from the beginning. Mobile must not be treated as a late add-on. The PC remains the full desktop environment; the mobile experience is designed for touch, small screens, mobility, and quick interactions.

The goal is continuity across devices while allowing each device to remain useful independently.

## Experience model

### PC
- Full desktop workspace, windows and multitasking.
- Files, system settings, terminal, productivity apps, communication clients, and AI assistance.
- Detailed controls for administration and advanced workflows.

### Mobile
- Touch-first navigation, responsive layouts, accessible controls, and efficient one-handed use.
- Notifications, messaging and communication access, quick actions, selected documents, and AI assistance.
- Device-specific capabilities exposed only with explicit permission and platform support.
- Do not assume EiraOS replaces Android or iOS as the phone's operating system. Initial mobile support may be an Eira companion app running on existing mobile platforms.

### Cross-device continuity
- Optional, user-controlled sync of selected preferences, drafts, tasks, and supported content.
- Continue a supported workflow on another device when the user is authenticated and the app/provider allows it.
- Share files and links between paired/authorized devices.
- Consistent language and accessibility preferences where practical.
- Device status and notification handoff only where supported and clearly configured.

## Shared platform services

Define stable contracts for:
- Account and device registration.
- Authentication and session management.
- Device trust, revocation, and lost-device response.
- Per-data-type sync preferences and conflict handling.
- Notification routing and privacy controls.
- File/link sharing.
- Language and locale preferences.
- Communication-provider connections and permission scopes.
- Audit events and user-visible sync status.

The UI and device-specific clients must consume documented contracts. Platform-specific functions belong in adapters; do not embed device OS assumptions in shared domain logic.

## Security and privacy

- Pairing and account linking require explicit user action.
- Use secure, authenticated transport and encrypt sensitive data in transit; sensitive data at rest must use appropriate platform storage protections.
- Minimize synced data. Do not sync entire mailboxes, documents, contacts, or message histories by default.
- Give users per-category sync controls, clear status, export/deletion behavior, and revocation.
- Lost or compromised devices must be revocable without exposing other devices' local data.
- Device identity is not authorization by itself. Every sensitive action checks user identity, current permissions, and resource scope.
- Avoid exposing message content on lock screens unless the user enables previews.
- Do not claim end-to-end encryption unless the protocol and implementation have been reviewed and tested for it.

## Suggested implementation sequence

1. Define the cross-device threat model, account model, and data ownership.
2. Identify initial mobile scope and supported platforms; treat companion-app support separately from a native mobile OS.
3. Implement a narrow vertical slice, such as authenticated device pairing and sharing a link or a deliberately selected file.
4. Add optional language/theme preferences and notification handoff with explicit controls.
5. Add communication workflows only through supported provider APIs and scoped permissions.
6. Add sync conflict, offline, expired-session, revoked-device, and recovery tests.
7. Validate behavior on real target devices before claiming compatibility.

## Definition of done

Cross-device functionality is complete only when authentication, authorization, transport security, privacy controls, offline/failure behavior, revocation, automated tests, and device-level verification exist. A mockup or shared visual design alone is not implementation.

## Relationship to other Eira architecture

- eiraos-design-principles.md defines the experience and language layer.
- eiraos-communication-principles.md defines provider-neutral communication integration.
- eira-system-api.md defines the proposed PC-facing system contract.

Cross-device services complement these contracts; they must not bypass local OS security or provider authorization.
