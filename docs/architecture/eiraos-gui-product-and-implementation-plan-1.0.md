# EiraOS GUI Product and Implementation Plan 1.0

**Status:** Product and implementation specification draft; requires UX review and repository audit  
**Date:** 2026-10-21  
**Target platform:** Ubuntu Desktop 26.04 LTS  
**Applies to:** React/Tauri desktop shell, settings/control center, app surfaces, notifications, terminal surface, accessibility, and presentation-layer tests

> The GUI is EiraOS's primary product experience—not a dashboard placed on top of Ubuntu.

This document defines what the EiraOS GUI must contain, how it should behave, how it connects to system capabilities, and how completeness is verified. It describes the target, not a claim that all screens or features already exist.

## 1. Product objective

Create a distinctive, modern PC experience that combines:
- The approachability and direct manipulation of good tablet/mobile interaction patterns.
- The flexibility of a desktop: windows, keyboard, mouse, multitasking, files, external displays, and advanced workflows.
- A coherent intent- and conversation-oriented layer for finding and doing things.
- Full access to real Linux capabilities without forcing every user to learn Linux terminology.
- Clear status, privacy, permissions, and recovery behavior.

EiraOS must not be a superficial Ubuntu theme or a phone interface stretched across a monitor. It must work well on desktop displays, laptops, touch screens, keyboard/mouse setups, and assistive technologies.

## 2. UX principles

1. **Simple by default; advanced when requested.** Common tasks use plain language; detailed controls remain discoverable.
2. **One coherent system.** Navigation, search, settings, notifications, dialogs, and status use consistent patterns.
3. **User intent, not hidden magic.** The system may suggest an action, but shows material consequences and asks when consent or authorization is required.
4. **Real state only.** A control must show actual state from a service or explicitly say unavailable, loading, unsupported, or in development.
5. **Presentation stays separate.** React renders state and captures user intent. It does not implement system policy, invoke arbitrary shell commands, or call privileged OS services directly.
6. **Progressive disclosure.** Basic and advanced modes share the same contracts and state; advanced mode reveals detail rather than a separate unsafe pathway.
7. **No silent changes to user intent.** Do not silently change recipients, accounts, transports, privacy, cost, target devices, or destructive parameters.
8. **Recoverability.** Errors explain what happened, what did not happen, and safe next steps.
9. **Accessible and adaptable.** Keyboard, pointer, touch, screen reader, scalable text, high contrast, reduced motion, and localization are first-class.
10. **Respect the desktop.** Do not remove normal application windows, filesystem access, external peripherals, or terminal capabilities in pursuit of a simplified UX.

## 3. Shell and global layout

The shell must provide stable, predictable access to:
- **Home / workspace** — current work, pinned apps/objects, recent items, and resumable tasks.
- **Global search / command palette** — apps, settings, files, people, objects, and actions, with result types and permission-aware actions.
- **Application launcher** — installed apps, favorites, search, and app details.
- **Workspace and window controls** — overview, switcher, move/resize, snap/tiling, minimize/maximize/close, and multi-monitor behavior.
- **System status area** — network, audio, power/battery, Bluetooth, notifications, time/date, and active background tasks, only when the underlying capability exists.
- **Quick settings** — safe, common toggles with truthful state and links to detailed settings.
- **Notification center** — grouped notifications, action buttons, do-not-disturb/focus, and notification history policy.
- **Eira assistant entry point** — persistent but unobtrusive, available from keyboard and GUI, with explicit proposed/executing/completed/failed states.
- **Settings / Control Center** — complete navigation to supported PC capabilities.
- **Terminal** — launchable as an application and usable alongside other applications.

Exact placement, dock/panel behavior, workspace gestures, and visual composition require a UX prototype decision. The shell must not hard-code the assumption that all users use touch or one display size.

## 3.1 Spatial 3D workspace — core product direction

EiraOS is intended to offer a spatial desktop in which the screen is perceived as a navigable three-dimensional space, not only as a flat stack of windows. This is a product direction to prototype and validate; it is not a claim that a 3D interface is already implemented.

### Spatial behavior

- **Depth and occlusion:** objects can occupy different depths. Foreground objects can overlap or obscure background objects, with clear rules for selection, focus, and bringing an object forward.
- **Rotation and orientation:** supported objects can rotate around one or more axes when the action is meaningful. Rotation must not make labels, controls, or critical information unreadable.
- **Spatial placement:** users can arrange app surfaces, documents, work groups, tools, and assistant/context objects in a navigable workspace. Position and depth must have understandable meaning rather than being decoration alone.
- **Direct manipulation:** objects can be selected, moved, brought forward/back, grouped, opened, minimized, pinned, and returned to a known home position using supported pointer, keyboard, and touch interactions.
- **Navigation:** users can pan, zoom, change viewpoint, or switch between spatial workspaces without losing track of where objects are. Provide a clear reset/recenter action and an overview that shows the overall arrangement.
- **Layered work:** users can keep current work in the foreground and supporting material behind or beside it, while still being able to discover and retrieve obscured objects.
- **Transitions:** motion should communicate movement and hierarchy. It must be short, interruptible where possible, and disabled or reduced when the user requests reduced motion.
- **Persistent arrangement:** spatial positions and groups may be saved per workspace, with explicit recovery behavior when a display resolution, monitor arrangement, or application size changes.

### Product and technical boundaries

- Treat 3D as a **spatial interaction model**, not as a requirement to render every control as a heavy 3D object. Settings forms, text, terminal output, tables, and accessibility surfaces may remain flat panels placed within the spatial environment.
- Preserve normal desktop productivity: resizable app surfaces, keyboard shortcuts, focus order, text selection, drag-and-drop where supported, multi-monitor behavior, and a real Linux terminal.
- The spatial shell must not trap users in perspective navigation. Offer a stable 2D/flat mode or reduced-depth mode, plus keyboard-accessible ways to perform every essential operation.
- Do not rely on depth, color, motion, or rotation alone to convey status or affordance. Keep labels, focus indicators, selection outlines, and accessible names.
- Keep rendering and interaction in the presentation layer. Spatial transforms, object layout, camera/view state, and animations must not own system policy or execute privileged actions.
- Define a stable object model for identity, type, position/depth, orientation, size, grouping, z-order, focus, persistence, and capability references. Keep it separate from React component instances and operating-system authorization.
- Prototype the rendering strategy before selecting a production dependency. Evaluate performance, GPU/driver compatibility, text readability, input latency, memory use, reduced-motion behavior, and maintainability on the pinned Ubuntu 26.04.x target.
- Do not introduce a WebGL/3D engine dependency solely for visual novelty. Document the trade-offs and verify that the selected approach works with the existing React/Tauri/compositor architecture.

### Required prototype and acceptance evidence

The spatial direction must be proven with a runnable prototype before the shell architecture is locked. The prototype should demonstrate:

1. At least three distinct objects at visibly different depths, with foreground/background occlusion.
2. User-controlled rotation of a supported object and clear selection/focus behavior.
3. Moving objects through depth and restoring an object to the foreground.
4. Pan/zoom or viewpoint navigation, plus overview and recenter/reset.
5. Object grouping and persistence of a workspace arrangement.
6. Keyboard-only navigation and actions, readable text, focus indicators, and reduced-motion mode.
7. Flat/reduced-depth fallback and behavior at representative display sizes/scaling.
8. Measured rendering responsiveness on the target hardware class and graceful behavior when 3D acceleration is unavailable.

Until these criteria are demonstrated and reviewed, label the feature **specified / prototype pending**, not implemented or verified.

## 4. Required screens and surfaces

### 4.1 First-run setup and onboarding
- Language, region, keyboard layout, accessibility options, display scaling, network setup where available, privacy choices, and optional account/device setup.
- Explain local processing and any optional cloud processing in understandable terms.
- Clearly distinguish required setup from optional integrations.
- Allow safe skip/revisit where possible; never imply a service is configured when it is not.
- Provide recovery when network, hardware, or permissions are unavailable.

### 4.2 Home and workspace
- User-configurable favorites and pinned items.
- Recent and active work with understandable provenance.
- Contextual suggestions must be explainable, dismissible, and not presented as facts without evidence.
- Clear empty states for new users and unavailable services.
- No fabricated activity, fake service status, or demo records in production mode.

### 4.3 Search and command palette
- Keyboard shortcut and visible entry point.
- Search across applications, settings, files, supported people/objects, and help.
- Typed result categories; preserve the distinction between finding an item and performing an action.
- Permission-aware filtering without leaking inaccessible secrets.
- Ambiguity handling: zero, one, or multiple matches must be explicit.
- Destructive or external actions show a review/confirmation step when required; search results cannot bypass Gate.
- Recent queries/history must have documented privacy and retention behavior.

### 4.4 Application launcher and app management
- Installed apps, favorites, categories, search, launch, pin/unpin, and uninstall/update entry points only where supported.
- Show app source, permissions, and installation status where reliable metadata exists.
- Use supported Ubuntu package/service interfaces behind EiraSystemAPI; UI must not execute package commands directly.
- Distinguish unsupported package formats and failed/partial installs.

### 4.5 Windowing and multitasking
- Open, focus, minimize, maximize, restore, close, move, resize, snap/tiling, and workspace switching.
- Overview and task switcher, including keyboard navigation.
- External monitor, mixed scaling, orientation, and display-disconnect recovery.
- Focus order and shortcuts must be consistent and documented.
- Do not lose unsaved work silently when closing windows or changing display state.
- Define whether app windows are managed by the compositor/window manager or by EiraOS; do not simulate window management inside a single React page if native windows are required.

### 4.6 Settings / Control Center
Settings is a first-class product area, not a collection of placeholder pages. Organize by user task, with search and consistent detail pages.

Required categories and candidate capabilities (availability depends on hardware and Ubuntu services):
- **Network & Internet:** Ethernet, Wi-Fi, connection status, saved networks, VPN, proxy, DNS details where supported.
- **Bluetooth & Devices:** Bluetooth state, pairing, connected devices, input devices, printers/scanners, cameras, audio devices.
- **Display:** resolution, scaling, refresh rate, orientation, night light/color options when supported, multi-monitor arrangement.
- **Sound:** output/input device, volume, per-device settings where supported, microphone privacy/status.
- **Appearance:** theme, accent, wallpaper/background, desktop/panel behavior, icon/text scaling, animation/reduced-motion preference.
- **Personalization & Accessibility:** text size, contrast, keyboard navigation, screen reader integration, sticky/filter keys, magnification, captions where supported.
- **Power & Battery:** power mode, battery status, screen blanking, suspend behavior; never expose unsupported controls.
- **Storage:** volumes, free space, removable devices, mount/eject, storage usage; destructive format/partition operations require explicit risk handling and suitable authorization.
- **Applications:** installed apps, defaults, startup apps, permissions where supported, updates/uninstall.
- **Users & Accounts:** local users and session settings where permitted; account/provider integrations remain explicit.
- **Privacy & Security:** screen/mic/camera indicators where supported, permissions, lock/screen timeout, firewall status, connected services, data retention and cloud-processing controls.
- **Updates & Recovery:** update status, review/install updates, restart requirements, recovery/rollback status where available.
- **Date, Time & Region:** timezone, clock format, locale, language, calendar, number/date formats.
- **Keyboard, Mouse, Touchpad & Input:** layouts, shortcuts, pointer speed, gestures, repeat settings, touch behavior.
- **Printers & Scanners:** discovery, add/remove, queue and error state where supported.
- **Sharing & Remote Access:** disabled by default unless the product explicitly enables a capability; disclose network exposure and require authorization.
- **Developer & Advanced:** terminal, diagnostics, logs, service status, supported developer settings; advanced controls must not bypass Gate.
- **About EiraOS:** version, Ubuntu base/image, support status, hardware/software information, licenses, diagnostics export, update channel.

Each settings page must define: capability identifier, read model, supported mutations, loading/empty/error/permission-denied/offline states, authorization and confirmation rules, success postcondition, audit behavior, and automated tests.

### 4.7 Quick settings and status
- Show current, sourced state; unknown is not the same as off.
- Toggle only capabilities whose operation and rollback/error behavior are implemented.
- Provide detailed settings navigation.
- Warn when a change disconnects the active network, stops a service, affects a call, or otherwise interrupts current work.
- Do not display fabricated battery, VPN, device, update, or privacy status.

### 4.8 Notifications and system activity
- Notification grouping, focus/do-not-disturb, per-app controls where supported, and actionable notifications.
- Long-running operations show progress, cancellation support where safe, and final outcomes.
- Distinguish completed, failed, partially completed, waiting for consent, waiting for authentication, and waiting for user input.
- Notification action handlers go through typed contracts and Gate.
- Define persistence and retention; sensitive message contents must not leak onto lock screen by default.

### 4.9 Files and storage UX
- Browse approved files and locations; navigate, search, preview supported file types, open with apps, and show metadata.
- Make file operations explicit: create, rename, copy, move, delete, trash/restore, mount/eject, and permissions only as capabilities are implemented.
- Respect sandboxing, filesystem permissions, symlinks, mount boundaries, and path traversal protections.
- Clearly distinguish permanent delete from moving to trash; provide undo only when technically guaranteed.
- Show progress, conflicts, permission failures, and partial completion for multi-file operations.
- No broad filesystem authority based solely on AI interpretation.

### 4.10 Assistant and intent workflow
- Conversational entry point and contextual actions, without taking over the entire desktop by default.
- Show the interpreted intent and target when ambiguity or consequence warrants it.
- Separate suggestion, plan, consent, authentication, execution, and verified outcome states.
- Explain why clarification, confirmation, or elevated authentication is needed.
- Never report success solely because the model or UI says so; use the service postcondition and persisted state.
- Allow cancellation before the point of no return where supported and explain when cancellation is no longer possible.
- Provide an inspectable activity/evidence view for material system actions.

### 4.11 Communications
- Unified conversation-first UX may combine views, but must preserve transport, account, recipient, privacy, cost, delivery and failure metadata when material.
- Explicit account/provider connection and disconnection controls.
- Distinguish draft, proposed, queued, sent, delivered, failed, and accepted states where the transport supports them.
- No silent cross-transport rerouting, recipient substitution, or cloud processing.
- Contact resolution must handle ambiguous or duplicate identities before sending.

### 4.12 Terminal and developer surfaces
- Real PTY-backed terminal, not an emulated text input.
- Normal logged-in user permissions by default; no automatic root or sudo.
- Support multiple terminal sessions, Unicode, resize, signals, exit status, and interactive TUI programs.
- Provide clear session lifecycle, copy/paste, keyboard shortcuts, and accessible terminal behavior.
- Terminal commands are not a back door into EiraSystemAPI or Gate-protected GUI actions.
- Developer tools and logs expose useful diagnostics without revealing secrets.

### 4.13 Lock screen, session, and recovery
- Lock/unlock, session switching where supported, login/session errors, sleep/wake, and crash recovery.
- Sensitive notifications hidden by default while locked.
- Restore windows/workspaces only where safe and without restoring secrets or executing actions automatically.
- Recovery mode and safe diagnostic path for broken UI, display configuration, or unavailable daemons.

## 5. Interaction states and behavior contract

Every interactive surface must account for applicable states:
- Initial / empty
- Loading / refreshing
- Ready / current
- Stale / disconnected
- Unsupported / hardware unavailable
- Permission denied
- Waiting for consent
- Waiting for authentication
- Validation error
- Running / progress
- Cancelled
- Failed
- Partially completed
- Completed and verified

UI wording must reflect actual backend status. For example, “completed” requires a verified postcondition, not merely a successful IPC response. A timeout must not be presented as proof that the operation failed if the result is unknown; show an explicit unknown/reconciliation state and avoid unsafe blind retries.

## 5.1 UX resilience, discoverability, and recovery contract

EiraOS must be understandable and recoverable when intent recognition, policy, authorization, integrations, or application hosting do not behave as expected. Fail-closed security is mandatory; a dead-end user experience is not.

### A. Intent repair and graceful degradation

- Distinguish low confidence, ambiguous target, unsupported capability, policy denial, missing consent, missing authentication, timeout/unknown outcome, and execution failure. Do not collapse them into a generic “I don't understand” response.
- When intent is ambiguous, present a short, ranked set of interpretations and let the user choose; do not silently guess when the choice materially changes the action.
- Offer a direct repair path: clarify, rephrase, inspect the proposed plan, choose a visible manual route, or cancel.
- When intent automation is unavailable, keep supported manual navigation and ordinary app workflows usable.
- A failed interpretation must not be treated as a failed operation if execution may already have occurred. Reconcile state before retrying non-idempotent actions.
- Keep explanations short by default, with optional technical detail and diagnostic identifiers.

### B. Discoverability and first-run experience

- Provide a visible, searchable capability catalogue that explains what the user can do in the current context, which capabilities are unavailable, and what permissions or setup are needed.
- Pair natural-language entry with discoverable controls, contextual actions, keyboard shortcuts, examples, and a first-run guided task. Intent must not be the only route to important functionality.
- Use progressive disclosure: show essential choices first and advanced controls when requested or contextually relevant.
- Design onboarding around a useful, completed task, not a tour of abstract concepts. Let users skip, revisit, and reset onboarding.
- Validate first-run comprehension with representative users, including people who do not know Linux or EiraOS terminology.

### C. Trust, assurance, and Gate explanations

- Do not expose a universal trust percentage by default. Show a score only when it is meaningful, calibrated, explainable, and useful to the decision at hand.
- Prefer a clear state and reason (for example, verified, needs review, or blocked) with accessible text; never rely on color alone.
- When an action is blocked, explain the specific unmet requirement at an appropriate level, distinguish policy denial from missing consent/authentication, and provide the shortest legitimate next step where one exists.
- Never imply that user confirmation can override policy or grant authority the user does not possess.
- Record the machine-readable denial reason and diagnostics separately from the human explanation; avoid leaking sensitive policy or system details.

### D. The hybrid desktop: spatial objects and ordinary work

- Treat files, URLs, browser tabs/pages, messages, and supported app windows as first-class entry/exit points across the spatial workspace and conventional desktop workflows.
- Support ordinary open-with, save/download, copy/paste, drag/drop where supported, file picker, browser navigation, and export/share paths without requiring users to convert everything into a graph object.
- Preserve provenance and meaningful metadata when content crosses application boundaries, subject to privacy and platform constraints.
- Make unsupported integration boundaries explicit and provide a normal fallback. Do not present a mock or wrapper as native integration.
- The spatial layer must not block conventional window management, dense lists/tables, text selection, keyboard shortcuts, multi-monitor use, or accessibility tools.

### E. Latency and responsiveness budgets

Use the following as initial product targets to measure in the prototype, not as claims about current performance. Refine them using representative hardware and usability tests:

- Local interaction feedback (focus, selection, opening a lightweight panel): target p95 at or below 100 ms.
- Local navigation or simple view transition: target p95 at or below 150 ms.
- First visible acknowledgement for an intent request: target at or below 100 ms; show progress and allow cancellation while interpretation continues.
- Simple local read-only intent plan: target p95 at or below 400 ms, excluding slow external services.
- Any operation that exceeds its budget must expose truthful progress or a non-blocking pending state; do not freeze the GUI while waiting on a daemon, model, or network.
- Instrument end-to-end latency by stage (input, parse, policy/assurance, IPC, service, render) and report p50/p95/p99. Do not optimize by bypassing Gate or required verification.

### F. Undo, history, and recovery

- Define undo per operation, not as a universal promise. Offer undo only when the system can guarantee the inverse or restore a saved state safely.
- Distinguish undo, restore/recover, retry, and duplicate execution. Explain when an operation is irreversible or its result is uncertain.
- Provide a human-readable activity history for material actions, including what was requested, what was actually done, outcome, and available recovery options.
- Spatial layout changes should be independently undoable and persist separately from application data and system authorization state.
- Never automatically replay a consequential action during crash recovery or workspace restoration.

### G. Identity and organizational context

- Make the active identity, account, organization, role, and acting context visible when relevant to the consequence of an action.
- Require deliberate context switching and make the target context explicit before material or external actions. Avoid repeated prompts when a valid context remains established, but never silently transfer authority across contexts.
- Explain whether a denial is caused by identity, role, policy, authentication, or resource scope; offer a legitimate resolution path when possible.
- Design for delegated roles, organizational acting context, and future public-sector identity integrations without assuming any one provider is already implemented.

### H. Priority failure-path tests

Before broad GUI expansion, prototype and test these end-to-end journeys:

1. **Intent misfire:** User asks to perform a task; the interpretation is ambiguous or confidence is low. The UI offers useful choices or a manual route, preserves the original request, and does not execute a consequential guess.
2. **Gate denial:** User requests a protected action. The UI explains the actual denial category and next legitimate step, does not leak sensitive internals, and cannot bypass the Gate through an alternative UI path.
3. **Hybrid work:** User downloads or selects an ordinary file, opens it in a supported application, returns to the spatial workspace, and can locate/export it without losing context or creating duplicate/conflicting state.
4. **Slow or unavailable service:** The UI remains responsive, shows progress or a clear stale/offline state, and reconciles uncertain outcomes before offering retry.
5. **Undo and recovery:** User makes a reversible workspace change and restores it; then tests an irreversible action and sees an honest explanation of what cannot be undone.
6. **Identity context:** User switches between personal and organizational contexts and can identify which context will authorize a consequential action.

These are release-blocking UX acceptance scenarios for the relevant flows. They must be covered by automated tests where feasible and usability tests with representative users. A design document or visual prototype alone does not count as passing evidence.

## 6. Frontend architecture

Keep the dependency direction:

1. **Presentation:** React pages/components, design tokens, animations, accessibility, local view state.
2. **UI application layer:** screen orchestration, view models, input validation, navigation, optimistic updates only where safe.
3. **Typed EiraOS client:** generated/hand-maintained typed requests and responses, schema/version validation, cancellation and correlation IDs.
4. **Tauri IPC boundary:** narrow command surface and validation; no generic arbitrary privileged command endpoint.
5. **EiraOS domain/services:** use cases, Gate, identity/object resolution, state transitions, audit, persistence.
6. **EiraSystemAPI adapters:** Ubuntu/D-Bus/service integration with native authorization.
7. **Ubuntu/platform:** compositor, session, hardware, system services, drivers.

Rules:
- Components do not access daemon sockets or D-Bus directly.
- Components do not run shell commands for system management.
- No policy decisions based on hidden UI state.
- Backend authorization is authoritative; disabling a button is usability, not security.
- Typed errors are translated into understandable UI messages without dropping diagnostic codes.
- IPC contracts are versioned and tested.
- Loading, stale, retry, cancellation, and duplicate-submit behavior is standardized.
- Keep domain models independent from React and CSS.
- Test user flows through accessible roles/labels rather than fragile DOM structure where practical.

## 7. Design system and component inventory

Create and maintain a single design system with:
- Color, typography, spacing, density, elevation, borders, radii, icon sizing, focus rings, motion and z-index tokens.
- Light/dark themes, high contrast, accent choice, and reduced motion.
- Layout primitives for app shell, page header, navigation rail/panel, content region, cards, lists, tables, forms, dialogs, popovers, menus, toasts, progress, empty/error states.
- Reusable controls: button, text field, search field, checkbox, radio, toggle, select, slider, segmented control, tabs, breadcrumb, list row, tree, data table, device card, permission prompt, confirmation dialog, status indicator.
- Consistent destructive-action hierarchy and confirmation language.
- Icon naming and meaning rules; icons are never the only label for important actions.
- Responsive breakpoints for laptop, desktop, high-DPI, touch, and narrow windows.
- Component documentation and visual regression coverage.

Avoid arbitrary one-off styling. A screen-specific component is allowed when it represents a real domain concept, not merely to bypass the design system.

## 8. State, persistence, and data boundaries

- Server/system state is sourced from authoritative services; local UI state is used only for transient presentation.
- Cache entries include freshness/invalidity semantics.
- A mutation updates the UI only from authoritative response or a clearly marked pending state.
- Use correlation IDs for user-visible long-running actions and audit traces.
- Idempotency keys protect retries where applicable.
- No secrets in local storage, logs, analytics, notifications, crash reports, or view models unless an explicit secure design permits it.
- Define offline behavior and reconciliation for every feature that can run while services are unavailable.
- Avoid optimistic success for privileged or irreversible operations.

## 9. GUI implementation work packages

### GUI-0 — Audit current frontend
Inventory React routes/components, CSS/design tokens, Tauri commands, IPC wrappers, dev HTTP bridge, navigation, app entry points, tests, and any duplicated state. Map each existing screen to this plan. Do not replace existing functionality before understanding it.

### GUI-1 — UX map and shell decision
Create screen map, primary navigation, shell layout, workspace/window strategy, keyboard shortcuts, and interaction flows. Build low-fidelity wireframes and review them before committing to a detailed visual direction.

### GUI-2 — Design system foundation
Implement tokens, themes, primitives, focus behavior, accessibility defaults, component examples, and visual regression baseline.

### GUI-3 — Real shell and global navigation
Implement app shell, launcher, search entry, workspace/window integration, status area, quick settings, notifications, and assistant entry point with truthful state.

### GUI-4 — Settings framework
Build capability-driven settings navigation and page templates; integrate read-only status first, then safe mutations with authorization, confirmation, error and postcondition handling.

### GUI-5 — Files, app management, and everyday workflows
Implement only supported capabilities, with permission boundaries and failure/recovery behavior.

### GUI-6 — Assistant and action lifecycle UI
Represent proposal, clarification, consent, authentication, execution, failure, partial success, and verified completion using the same Gate contract.

### GUI-7 — Communication and terminal surfaces
Build on their typed contracts and independent service boundaries; do not fake transport delivery or terminal execution.

### GUI-8 — Accessibility, localization, and polish
Keyboard-only review, screen-reader pass, high contrast, scaling, reduced motion, language expansion, multi-monitor, sleep/wake, and error-state coverage.

### GUI-9 — Release readiness
Test clean install, upgrade, first run, missing services, denied permissions, offline state, app crash, daemon restart, and recovery. Verify the actual target Ubuntu image.

## 10. GUI acceptance checklist

A GUI capability is accepted only when all applicable criteria pass:

- [ ] The screen and user story are documented.
- [ ] Navigation and keyboard access are defined.
- [ ] UI states and error copy cover unavailable, denied, stale, failed and partial outcomes.
- [ ] The underlying capability exists and is represented in the coverage matrix.
- [ ] The UI calls a typed EiraOS contract, not a shell command or direct OS service.
- [ ] Gate, consent, and authorization remain enforced by backend services.
- [ ] Success is shown only after the required postcondition is verified.
- [ ] Loading, timeout, cancellation, duplicate submit and stale state are tested.
- [ ] Accessibility and localization requirements are checked.
- [ ] Unit/component and relevant integration/E2E tests pass.
- [ ] Screenshots or visual regression evidence are attached where useful.
- [ ] Unsupported functionality is labelled honestly and cannot appear to succeed.
- [ ] Documentation and support status are updated.

## 11. GUI test strategy

- **Design-system tests:** tokens, themes, keyboard focus, accessible names, contrast, reduced motion.
- **Component tests:** form validation, menus/dialogs, status indicators, errors, loading, cancellation.
- **Contract tests:** typed IPC request/response, schema mismatch, error mapping, timeouts.
- **Flow tests:** navigation, search, settings, confirmation, permission denial, long-running tasks.
- **Security tests:** UI cannot bypass Gate; forged or repeated IPC calls are still rejected by backend policy.
- **Integration tests:** actual Tauri IPC and service adapters against controlled test services.
- **Target-image tests:** display/session, NetworkManager and device capability behavior on pinned Ubuntu 26.04.x.
- **E2E tests:** verified state and audit records, not screenshots alone.
- **Visual regression:** key shell/screen states across light/dark, scaling, and representative viewport sizes.
- **Manual exploratory tests:** multi-monitor, touch, screen reader, sleep/wake, terminal TUI, recovery, and real hardware where automation is insufficient.

## 12. Definition of GUI completeness

The GUI is not complete because the home screen looks polished. It is complete only when:
- The core shell and navigation are coherent.
- The full PC Core settings map is either implemented or explicitly marked unsupported/blocked with evidence.
- Common desktop workflows work with keyboard and pointer, and touch where applicable.
- Every visible control reflects a real capability or an honest unavailable state.
- AI workflows obey the Gate and report verified outcomes.
- The terminal remains a real terminal.
- Errors, permissions, offline conditions, restart, and recovery are designed—not afterthoughts.
- Accessibility, localization, and target-platform behavior are tested.
- Every supported capability has traceable acceptance evidence.

## 13. Open UX decisions

Resolve through prototype and usability review rather than silently hard-coding assumptions:
- Main shell arrangement: top bar, dock/panel, navigation rail, or combination.
- Default home/workspace layout and whether it can be customized.
- Window management and compositor integration strategy.
- Search/command palette scope and shortcuts.
- How the assistant is summoned and how contextual suggestions are surfaced.
- Basic/advanced settings presentation.
- Notification privacy and retention defaults.
- Visual identity, icon family, theme defaults, and density.
- Touch/gesture support expectations and supported hardware.
- Which communications surfaces belong in the first release.

## 13.1 Agreed visual baseline: Intuitive 3D Desktop

The primary visual reference is the EiraOS Intuitive 3D Desktop concept, captured as a maintained, self-contained HTML prototype:

- [Intuitive 3D Desktop prototype](prototypes/eiraos-intuitive-3d-desktop.html)

This is the agreed direction for the GUI design baseline. It builds on the attached concept's dark Nordic palette, restrained cyan accent, glass-like surfaces, white app-icon tiles, soft ambient lighting, spatial window depth, and centered application dock. The HTML file is a design prototype, not a production implementation; its sample system values and app content are illustrative and must not be presented as live system state.

### Required application-object model

Applications are represented in the spatial desktop as independently managed objects. Each object has a stable application/window identity and presentation state, including position, depth, orientation, size, focus, grouping, and minimized/restored state. The spatial presentation model must remain separate from application execution, authorization, system policy, and EiraSystemAPI.

- Activating an object brings it into readable focus; other objects recede without losing their own state.
- Minimizing an application removes its surface from the active spatial stage but does not imply closing the application. A dock or object overview must restore it.
- Restoring an object should recover its prior placement and size when the underlying windowing integration permits it.
- Native Linux applications should be hosted through a supported desktop/windowing integration. Windows applications such as Microsoft Word and Excel require a separately validated compatibility strategy (for example Wine or a virtual machine); the GUI must not imply that Windows binaries run natively on Ubuntu.
- Free placement, rotation, grouping, spatial navigation, keyboard access, reduced-motion support, and a flat overview are product requirements. The current HTML prototype only demonstrates a subset of these interactions; it does not prove production window management.
- System controls displayed in the spatial environment must call typed, authorized system capabilities through EiraSystemAPI. Mock controls and static status labels must never be mistaken for real settings.

### Decision status

The visual direction is agreed as the baseline. The implementation technology, compositor/window integration, object persistence format, and interaction details remain subject to prototype evaluation and repository audit. This decision does not mark the GUI, 3D renderer, application hosting, or Ubuntu controls as implemented or verified.

## 14. Related contracts

- [Master Plan 1.0](../MASTER-PLAN-1.0.md)
- [Architecture Baseline 1.0](eiraos-architecture-baseline-1.0.md)
- [Separation of Presentation and Logic](separation-of-presentation-and-logic.md)
- [EiraOS Design Principles](eiraos-design-principles.md)
- [Ubuntu PC API Coverage Matrix](ubuntu-pc-api-coverage-matrix.md)
- [Gate Kernel 1.0](../../specs/GATE-KERNEL-1.0.md)
- [AI Interface 1.0](../../specs/AI-INTERFACE-1.0.md)
- [EDP 1.0](../../specs/EDP-1.0.md)
