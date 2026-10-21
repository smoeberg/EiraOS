# EiraOS Design Principles

**Status:** Proposed architecture direction  
**Scope:** Desktop experience and cross-system interaction  
**Implementation status:** This document records design intent; it does not claim that the described UI or services are implemented.

## Product direction

EiraOS should combine the technical foundation and hardware support of Ubuntu with a coherent, modern experience inspired by the best interaction principles of iPadOS and Android. Inspiration is not a mandate to copy either platform's appearance or proprietary implementation.

The experience should feel approachable to first-time users while preserving real Linux capabilities for advanced users.

## Principles

1. **Simple by default, capable when needed.** Common tasks should be discoverable and understandable without requiring users to know Linux terminology. Advanced controls remain available.
2. **A distinct EiraOS identity.** Use a consistent design language rather than merely reskinning a traditional desktop.
3. **Presentation separated from system logic.** UI components render state and express user intent; application/domain logic and Ubuntu integration live behind explicit contracts and adapters.
4. **Real, testable functionality.** A visible control must correspond to a real capability or be clearly identified as unavailable/in development. Do not present mock operations as completed system actions.
5. **Security by design.** Privileged operations require explicit authorization, scoped capabilities, clear confirmation where appropriate, and auditable outcomes.
6. **Accessible across input modes.** Support keyboard, mouse, touch, assistive technology, scalable text, and reduced motion.
7. **Consistent interaction.** Navigation, search, settings, notifications, quick settings, app switching, and file workflows should share common interaction patterns.

## Experience areas

1. **Home and navigation:** A personal, actionable home surface with app access, useful widgets, and clear navigation.
2. **Visual design system:** Typography, color, spacing, iconography, motion, themes, and reusable UI components.
3. **Windows and multitasking:** Predictable window behavior, app switching, focus, and keyboard navigation on desktop hardware.
4. **Settings, notifications, and quick settings:** Understandable system controls backed by real system capabilities.
5. **Files, apps, search, and assistant:** A coherent way to discover content and perform actions without exposing filesystem details unnecessarily.
6. **Accessibility and input:** Keyboard, mouse, touch, assistive technologies, localization-aware layouts, and reduced-motion support.
7. **Language handling and internationalization:** A system-wide language layer described below.

## Eira Language Layer

Language handling is a first-class, cross-cutting platform capability, not a feature owned independently by each screen.

### Responsibilities

- **Locale and language preferences:** Define system display language, preferred languages, regional formatting, and per-app overrides where practical.
- **UI localization:** Localize navigation, settings, labels, notifications, help, validation messages, and error explanations using versioned translation resources.
- **Internationalization (i18n):** Design for Unicode, plural rules, text expansion, locale-aware dates/numbers/currency, time zones, input methods, keyboard layouts, and right-to-left (RTL) scripts.
- **AI language understanding:** Allow users to express intents in supported natural languages, including ordinary phrasing and synonyms. Convert the interpretation into a typed, validated intent before any system action is considered.
- **Multilingual workflows:** Where supported, allow the UI language, conversation language, and document language to differ.
- **Translation assistance:** AI may propose or help review missing translations, but generated text must not silently replace approved critical strings.
- **Model independence:** The language layer must not depend on a single AI model or provider. AI services are replaceable behind explicit interfaces, with a defined fallback when unavailable.
- **Language coverage and capability disclosure:** Make supported languages and feature-level limitations clear; do not imply equal quality or speech support where it has not been validated.

### Safety and reliability

- AI interpretation is not authorization. Every proposed system action must pass the same capability, permission, assurance, and confirmation gates as any other request.
- Security prompts, permission explanations, destructive-action confirmations, and critical errors use reviewed, stable translations. If a reviewed translation is unavailable, use a clearly identified safe fallback rather than inventing critical wording at runtime.
- Preserve the original user input and provide a way to clarify ambiguous interpretations before execution.
- Never execute commands or privileged operations merely because a model generated text. Use typed intents and allowlisted operations.
- Language changes must not change authorization policy, identity, or the meaning of a capability.

### Suggested implementation sequence

1. Define locale preferences and a UI translation-resource format.
2. Add localization conventions and checks to the UI build and tests.
3. Localize a small end-to-end vertical slice, including settings, validation, and error states.
4. Define a versioned language-service contract for intent interpretation and translation assistance.
5. Connect AI interpretation to the existing intent pipeline while retaining deterministic validation and security gates.
6. Add automated tests for missing strings, pluralization, RTL/layout behavior, locale formatting, ambiguous intents, model unavailability, and unsafe model output.
7. Validate language quality and accessibility with native or qualified reviewers before claiming production support.

## Definition of done

A design or system feature is not complete merely because a mockup exists. For a feature to be considered implemented, it should have:
- a documented behavior and API/contract where applicable;
- a working UI and backend integration;
- permission and failure behavior defined;
- automated tests for expected behavior and important negative cases;
- accessibility and localization considerations;
- evidence from the target Ubuntu environment before claiming target-platform verification.

## Relationship to the system architecture

The design layer consumes stable EiraOS contracts; it does not call shell commands, D-Bus, Polkit, or privileged filesystem operations directly. Ubuntu-specific behavior belongs in system adapters behind the EiraSystemAPI and related service contracts. The language layer follows the same separation and must not bypass those boundaries.
