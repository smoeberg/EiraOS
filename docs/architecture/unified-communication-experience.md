# EiraOS Unified Communication Experience

**Status:** Proposed product and architecture direction  
**Implementation status:** Design decision only. No communication client, provider adapter, SMS bridge, PBX integration, or unified inbox is claimed to be implemented.

## Product vision

EiraOS should make communication feel like one coherent system rather than a collection of unrelated applications. Email, chat, SMS, social messaging, voice calls, video meetings, calendar events, contacts, and related files should be accessible through a consistent experience.

The user should be able to move naturally between channels from the same workspace—for example, continue a discussion in chat, compose an SMS to the same person, send an email attachment, or start a voice/video call—without needing to understand the underlying implementation.

**The unifying layer is the EiraOS experience, not a claim that all networks are technically the same.** Each channel retains its identity, delivery rules, privacy model, and capabilities.

## Experience principles

- One coherent communication workspace with a shared design system, search, contact context, notifications, and clear unread state.
- A conversation-first view where supported channels can appear together in a contact's communication history, while every message remains clearly labelled with its actual channel and account.
- Easy channel switching from the same window. Before sending through a different channel, the UI must make the destination and channel obvious; it must never silently convert or reroute a message.
- Email, SMS, chat, social messaging, calls, video meetings, calendar, and contacts should feel like parts of one product, not embedded legacy windows.
- A responsive design language shared by PC and companion mobile experiences, adapted to each form factor.
- AI language assistance can translate, summarize, draft, and help find information across authorized sources. Sending messages, inviting people, recording meetings, or changing events remains subject to user intent and the relevant permission gate.
- Accessibility, keyboard navigation, assistive technologies, localization, and right-to-left languages are foundational requirements.

## Architectural boundaries

### 1. Unified EiraOS interface

Owns presentation and interaction: inbox and conversation views, channel chooser, composer, contact context, calendar surfaces, search, notifications, and accessibility.

The UI must not directly contain protocol code, provider credentials, privileged OS access, or provider-specific business logic.

### 2. Eira Communication API

Define a versioned, provider-neutral contract for capabilities such as:

- Accounts, contacts and identity links.
- Conversations, messages, attachments, and channel metadata.
- Draft, send, delivery state, and errors where the provider exposes them.
- Voice/video session launch and status where supported.
- Calendar events and invitations.
- Notifications, synchronization state, capability discovery, and authorization.

The API must express provider differences honestly. A provider may not support edits, reactions, delivery receipts, search, or message history. The contract must report unsupported capabilities instead of pretending they exist.

### 3. Provider and protocol adapters

Keep adapters separate and replaceable. Evaluate standards and existing open-source projects before implementing new protocol engines.

Potential areas to evaluate—not implementation commitments—include:
- Email: IMAP/SMTP and provider OAuth integrations.
- Calendar and contacts: CalDAV/CardDAV and provider APIs.
- Chat: Matrix and supported APIs from other providers.
- SMS: a paired Android phone, supported modem, or authorized SMS gateway, depending on target hardware and jurisdiction.
- Voice/PBX: SIP integration and compatible calling infrastructure.
- Video: WebRTC and supported meeting providers.
- Social messaging: official APIs or supported integrations only.

Availability and permitted functionality vary by provider, device, operating system, and API policy. Do not promise full integration with a social network unless its supported interface allows it.

### 4. Identity and conversation linking

A person may have several addresses and identities—email addresses, phone numbers, Matrix IDs, and provider-specific handles. EiraOS may let the user link these identities into one contact, but must not merge them based on a guess alone.

Messages remain associated with their original account, channel, sender, timestamps, attachments, and delivery state. Unified presentation must not destroy protocol-specific meaning or security properties.

### 5. Security and user control

- Store credentials in the platform's secure credential store where available; never expose provider tokens to the UI.
- Enforce account-level and operation-level permissions.
- Clearly indicate the active sending account and channel.
- Keep end-to-end encryption and trust boundaries intact; do not claim that the unified layer makes encrypted services interoperable.
- Do not scrape private web interfaces, bypass provider restrictions, or read another app's private database without an explicit supported integration.
- Require explicit confirmation for consequential actions when intent or destination is ambiguous.
- Make data synchronization, AI processing, retention, and connected accounts visible and controllable by the user.

## Implementation strategy

1. Define user journeys and the shared interaction model before selecting engines.
2. Create the versioned Eira Communication API and a capability/permission model.
3. Prototype the UI with mock adapters and representative data; validate navigation, channel switching, accessibility, and responsive layouts.
4. Evaluate candidate engines and integrations against maintenance, license, security, platform support, API quality, test coverage, and long-term replaceability.
5. Add one real end-to-end channel at a time, with automated tests and documented integration evidence.
6. Expand to SMS, chat, calendar, voice/PBX, video, and social integrations according to feasibility and user value.
7. Reuse the same contracts across PC and companion mobile clients where practical.

## Acceptance criteria

A feature is not considered implemented because it appears in a mockup or because an external app can be launched. Each integration must document:

- Supported capabilities and known limitations.
- Account authorization and permission behavior.
- Error handling, offline behavior, and synchronization semantics.
- Automated tests and the platform/version used for integration verification.
- License and dependency review.
- Clear UI indication of the channel and account used for every outbound action.

## Relationship to existing principles

This document extends `docs/architecture/eiraos-communication-principles.md` and `docs/architecture/eira-cross-device-principles.md`. Those principles remain in force: provider neutrality, PC/mobile continuity, privacy by design, explicit authorization, and a strict separation between presentation and system/provider logic.
