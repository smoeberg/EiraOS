# EiraOS Communication Principles

**Status:** Proposed architecture direction  
**Implementation status:** This document records product and architecture intent. It does not claim that communication clients or integrations are implemented.

## Product decision

Communication should be deeply integrated into the EiraOS experience, while remaining provider-neutral and user-controlled. EiraOS should not require users to adopt a proprietary Eira account, mail service, or chat network to use the operating system.

The platform should integrate communication capabilities and installed apps through explicit contracts, rather than requiring every communication service to be implemented inside the OS.

## Three layers

### 1. System communication layer

Provide shared platform capabilities for:
- A unified notification surface with per-app and per-account controls.
- App-to-app sharing through explicit, permission-aware share actions.
- Contact selection and identity references where the user has connected a supported source.
- Deep links that open the relevant app and conversation/message when the provider supports them.
- Consistent handling of notification privacy, quiet hours, lock-screen visibility, and accessibility.
- Optional, permission-scoped search across connected sources, only where the provider exposes an appropriate API.

This layer must not silently scrape apps, read arbitrary local mail databases, or bypass provider authorization.

### 2. Communication apps

Treat the following as core user workflows and evaluate implementations independently:
- **Email client:** Support standard protocols/providers where practical, such as IMAP/SMTP and OAuth-based providers. Support multiple accounts, search, attachments, drafts, and accessible composition. Provider-specific features may require their own integrations.
- **Chat and messaging:** Integrate existing providers through their supported APIs or installed clients. Evaluate open protocols such as Matrix as an optional first-class integration; do not assume every proprietary network permits full third-party clients.
- **Voice and video:** Prefer supported external clients or provider integrations initially; define system-level launch, device selection, and notification behavior without inventing a new calling network.
- **Calendar and contacts:** Integrate with user-selected providers and existing standards where practical, using explicit account and data permissions.

A built-in client is a product decision, not a requirement that EiraOS operate its own mail or messaging service.

### 3. AI communication assistant

With explicit user permission, AI may help:
- Summarize a selected conversation or a clearly scoped set of messages.
- Draft, rewrite, translate, or adjust the tone of a reply.
- Search connected communication sources using natural language, when supported by authorized APIs.
- Extract potential tasks or dates and ask before creating calendar events or tasks.

AI must distinguish suggestions from actions. Sending messages, forwarding content, inviting people, deleting messages, and sharing attachments require clear user intent and appropriate confirmation. AI must not train on, retain, or transmit message content beyond the declared processing and privacy policy. Connected data should be minimized and access revocable.

## Privacy and security requirements

- Account connections are opt-in, visible, and revocable.
- Use provider-approved authorization flows and least-privilege scopes.
- Store credentials and tokens using an appropriate OS credential store; never store secrets in UI code or plain-text configuration.
- Keep account data separated by user and provider; enforce permission checks in the backend, not just in the GUI.
- Make notification previews and lock-screen content configurable.
- Provide clear status for offline, expired authorization, failed sync, and provider limitations.
- Do not claim end-to-end encryption unless the selected protocol and implementation actually provide it.
- Preserve provider terms, rate limits, and API restrictions.

## Suggested product direction

1. Build the shared communication foundation first: notifications, account/permission model, app launching, share actions, and consistent privacy controls.
2. Prototype an email client or integrate an established open-source client; compare maintenance cost, accessibility, provider coverage, and security before committing.
3. Provide chat through a supported integration, with Matrix worth evaluating as an open-protocol option; allow other installed clients to participate where APIs permit.
4. Add AI assistance to explicitly selected content before attempting broad cross-account search.
5. Expand to calendar, contacts, and voice/video only after the account and permission model is proven.

## Definition of done

A communication feature is implemented only when its UI, provider/system integration, authentication, permission boundaries, failure states, privacy behavior, and automated tests are present. Provider compatibility and any end-to-end encryption claims require specific verification.

## Architectural boundary

Communication UI must not access provider credentials or private data stores directly. UI requests go through documented application contracts and provider adapters. The system layer supplies common experiences but does not bypass each provider's authorization model.
