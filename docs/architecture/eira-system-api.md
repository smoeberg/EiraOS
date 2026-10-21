# EiraSystemAPI — kontrakt for Ubuntu-systemfunktioner

**Status:** Arkitekturforslag; ikke en implementeret eller runtime-verificeret API.  
**Målplatform:** Ubuntu Desktop 26.04 LTS, seneste 26.04.x punktudgave.  
**Ejer:** EiraOS. Ubuntu-/freedesktop-adaptere implementerer kontrakten; GUI'en afhænger kun af kontrakten.

## 1. Formål og grænser

`EiraSystemAPI` er EiraOS' stabile grænse mellem applikationslogik og operativsystemet. Den er ikke en enkelt Ubuntu-API, og den skal ikke foregive, at Ubuntu tilbyder ét samlet API til alle indstillinger, drivere, filer, netværk og enheder.

Kontrakten definerer operationernes betydning, version, input/output, fejl, tilladelseskrav og auditkrav. Adapterne oversætter til de relevante understøttede systemgrænseflader. De konkrete grænseflader vælges og verificeres pr. capability på Ubuntu 26.04.x.

### Afhængighedsretning

```text
React GUI
   │ typed view models / UI commands
   ▼
EiraOS application use cases
   │ EiraSystemAPI v1
   ▼
Capability policy + permission/confirmation gate
   │ adapter interface
   ├── Ubuntu filesystem adapter
   ├── Desktop portal / GIO adapter (where appropriate)
   ├── NetworkManager adapter
   ├── systemd adapter (scoped service actions)
   └── UDisks2 adapter (disks and mounts)
          │
          ▼
Ubuntu / freedesktop services / kernel
```

React må ikke kalde shell, D-Bus, Polkit eller filsystemfunktioner direkte. Systemadaptere må ikke importere React. Domæne- og use-case-logik skal kunne testes uden GUI, desktop-session eller rigtig systemændring.

## 2. Versionering og kompatibilitet

- Kontraktens første version er `EiraSystemAPI v1`; den er endnu ikke en runtime-API.
- Alle operationer har et eksplicit versions-/kontrakt-ID i adapterens capability metadata.
- Tilføjelse af valgfrie felter og nye operationer kan være bagudkompatibel, hvis klienter ignorerer ukendte valgfrie felter.
- Ændringer i betydning, obligatoriske felter, tilladelsesmodel eller fejlkoder kræver ny major-version eller en eksplicit migreringsplan.
- Adaptere annoncerer kun capabilities, som er implementeret, testet og tilgængelige i det aktuelle miljø. Ingen implicit “best effort” capability.
- Ukendt operation, versionsmismatch, manglende adapter, utilstrækkelig assurance eller uafklaret tilladelse skal fejle lukket.

## 3. Fælles kontrakt

Alle operationer skal følge et fælles envelope-princip. Nedenstående er illustrativt TypeScript og er ikke endnu en bindende genereret schemafil:

```ts
type EiraApiVersion = "1";

type EiraErrorCode =
  | "INVALID_ARGUMENT"
  | "NOT_FOUND"
  | "PERMISSION_DENIED"
  | "CONFIRMATION_REQUIRED"
  | "CAPABILITY_UNAVAILABLE"
  | "CONFLICT"
  | "UNSUPPORTED"
  | "RESOURCE_BUSY"
  | "RESOURCE_CHANGED"
  | "IO_ERROR"
  | "VERSION_MISMATCH"
  | "INTERNAL_ERROR";

interface EiraError {
  code: EiraErrorCode;
  message: string;             // safe, user-facing text
  retryable: boolean;
  operation_id: string;
  details?: Record<string, unknown>; // no secrets or raw tracebacks
}

interface EiraRequest<T> {
  api_version: EiraApiVersion;
  request_id: string;           // idempotency/correlation key
  operation: string;
  input: T;
}

interface EiraResponse<T> {
  api_version: EiraApiVersion;
  request_id: string;
  operation_id: string;
  result?: T;
  error?: EiraError;
}
```

En operation skal returnere enten et resultat eller en struktureret fejl, aldrig begge. Følsomme stier, tokens, private filindhold og systemtracebacks må ikke lækkes i fejl eller almindelige audit-events.

## 4. Første capability: filer

Filer bør være den første implementerede capability, fordi den kan afgrænses og testes uden at bygge hele systemindstillingslaget samtidig.

### Ressourceidentitet

En filressource er ikke et frit tekstfelt, der ukritisk sendes videre til shell. Den repræsenteres som en normaliseret, server-valideret resource reference. Klienten må ikke kunne omgå scope ved at ændre sti efter planlægning.

```ts
type FileEntryType = "file" | "directory" | "symlink" | "other";

interface FileEntry {
  resource_id: string;          // opaque EiraOS reference
  display_name: string;
  entry_type: FileEntryType;
  size_bytes?: number;
  modified_at?: string;
  can_read: boolean;
  can_write: boolean;
}

interface DirectoryListing {
  directory_id: string;
  entries: FileEntry[];
  next_page_token?: string;
}
```

`resource_id` skal bindes til den server-validerede resource/scope. UI må ikke bruge en opaque reference som en sti eller fortolke den som shell-argument.

### MVP-operationer og rækkefølge

1. `files.list_directory` — read-only, pagineret, begrænset til godkendt scope.
2. `files.get_metadata` — metadata uden automatisk at læse filindhold.
3. `files.read_text` — eksplicit tekstlæsning med maksimal filstørrelse og defineret håndtering af binære/ukendte encodings.
4. `files.search` — begrænset katalogscope, resultatloft og afbrydelsesmulighed.
5. `files.copy`, `files.move`, `files.rename` — først efter konfliktpolitik, idempotens og test af delvise fejl.
6. `files.delete` og overskrivning — senere, kræver stærk bekræftelse, tydelig målvisning og dokumenteret gendannelses-/fejlstrategi.

Hver operation skal definere input/output, scope, om bekræftelse er påkrævet, nødvendigt assurance-niveau, mulige fejlkoder, auditfelter og tests før den annonceres som understøttet.

## 5. Tilladelser og sikkerhed

- Standard er den aktuelle brugers almindelige Linux-rettigheder; ingen generel root-adgang.
- Ingen shell-baseret udførelse af brugerleverede stier eller kommandoer.
- Valider scope server-side ved både planlægning og udførelse. Bekræftelse er ikke en erstatning for adgangskontrol.
- Afvis traversal, ukontrollerede symlink-hop, scope-escape og resource references, som ikke tilhører sessionens autoriserede scope.
- Beskyt mod TOCTOU ved at genvalidere målobjekt og relevante metadata umiddelbart før ændring; brug fil-descriptor-baserede operationer hvor det er muligt.
- Sletning/overskrivning/flytning kræver en klar kollisionspolitik, idempotens og rapportering af delvise resultater.
- Privilegerede operationer skal være separate, snævre capabilities med eksplicit systemtilladelse; brug Polkit kun hvor en understøttet Ubuntu-grænseflade kræver det.
- Audit skal skelne mellem `requested`, `planned`, `confirmed`, `started`, `succeeded` og `failed`. En bekræftelse må aldrig logges som en vellykket systemændring.

## 6. Adaptervalg på Ubuntu

| Område | Kandidat | Afgrænsning |
|---|---|---|
| Almindelige filer i brugerens adgang | POSIX/Linux filsystem via en begrænset adapter | Brug normale brugerrettigheder; undgå shell |
| Desktop-filvælger og portalbeskyttet adgang | XDG portals | Brug kun når desktop-sandbox-/portalmodellen passer |
| GVfs-/fjernplaceringer og desktop-integration | GIO/GVfs | Verificér tilgængelighed, session og fejlsemantik |
| Netværksforbindelser | NetworkManager D-Bus/API | Separate capabilities for læsning og ændringer |
| Systemtjenester | systemd D-Bus/API | Begrænset service-sæt; ikke en generisk kommandokanal |
| Diske og mountpoints | UDisks2 | Adskilt fra almindelig filhåndtering og med særskilt tilladelsesmodel |
| Generel administration | Cockpit, hvor konkret genbrug er forsvarligt | Valgfri adapter/integration; aldrig kontraktens ejer |

Dette er kandidater, ikke en påstand om at alle grænseflader eller alle metoder er verificeret mod Ubuntu 26.04.x. Hver adapter kræver versionskontrol, tilladelsesreview og integrationstest på målplatformen.

## 7. Definition of Done pr. capability

En capability må først vises som understøttet i GUI'en, når alle punkter er opfyldt:

- EiraSystemAPI v1-input/output og fejlkoder er dokumenteret.
- Server-side policy, scope, assurance og bekræftelsesregler er implementeret.
- Adapteren håndterer manglende systemservice, timeout, versionsmismatch og delvise fejl.
- Unit-, kontrakt-, sikkerheds- og integrationstests består.
- Tests omfatter både tilladte og afviste handlinger samt grænsetilfælde.
- Faktisk test på Ubuntu Desktop 26.04.x er registreret med OS-, kernel-, desktop- og pakkeversioner.
- Audit-resultat afspejler den reelle operation.
- UI er kun præsentation og viser strukturerede resultater/fejl uden at eje systemlogikken.

## 8. Næste konkrete implementering

1. Få CI til at validere den fail-closed intent-confirmation-gate og dens regressionstests.
2. Fastlæg JSON Schema/Pydantic-modeller for EiraSystemAPI v1, og generér eller verificér tilsvarende frontend-typer.
3. Implementér kun `files.list_directory` i et isoleret adaptermodul med read-only scope.
4. Tilføj test-fixture med midlertidigt filsystem og tests for scope-escape, symlinks, manglende adgang, pagination og fejl.
5. Verificér på Ubuntu 26.04.x før næste operation aktiveres.

Indtil dette er gjort, må EiraOS ikke annoncere filhåndtering eller Ubuntu-systemkontrol som implementeret.
