# Installér EiraOS på en pc

EiraOS installeres fra et ISO, der er bygget på Ubuntu Desktop 26.04 LTS' officielle installer. Installeren lægger først et komplet Ubuntu Desktop på maskinen og derefter EiraOS ovenpå. Du logger ind med din adgangskode på Ubuntus login-skærm, og EiraOS er din standard-session.

## Krav

- amd64-pc med UEFI eller BIOS, mindst 8 GB RAM og 40 GB disk
- Internetforbindelse under installationen (opdateringer og pakkernes afhængigheder hentes fra Ubuntus arkiv; `eira-labwc` ligger på ISO'et)
- USB-nøgle på mindst 8 GB

## 1. Hent eller byg ISO'et

**Fra CI:** Kør workflowet *Ubuntu 26.04 Packaging Acceptance* (fanen Actions → Run workflow), og hent artefaktet `eira-installer-iso-ubuntu-26.04-amd64`. Det testbillede, CI installerer i sin VM (det sletter den første disk uden at spørge), forlader ikke CI-maskinen og kan ikke hentes.

**Lokalt på Ubuntu 26.04:**

```bash
sudo apt install xorriso gnupg curl
scripts/build_deb.sh --output-dir dist
BASE=$(scripts/fetch_ubuntu_iso.sh)
scripts/build_iso.sh --base-iso "$BASE" --deb dist/eira-os-core.deb --output-dir dist
```

`fetch_ubuntu_iso.sh` henter det nyeste Ubuntu Desktop 26.04-ISO og afviser det, hvis `SHA256SUMS` ikke er signeret med Canonicals CD-image-nøgle, eller hvis checksummen ikke passer. Resultatet er `dist/EiraOS-<version>-amd64.iso` (versionen står i `VERSION`) med `.sha3-256` og `.build-info.json`.

## 2. Skriv ISO'et til en USB-nøgle

```bash
sudo dd if=dist/EiraOS-0.8.0-amd64.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

Erstat `/dev/sdX` med USB-nøglen (tjek med `lsblk`). Alt på nøglen slettes. På Windows og macOS kan du bruge balenaEtcher.

## 3. Installér

1. Boot pc'en fra USB-nøglen, og vælg **Installér EiraOS (Ubuntu 26.04 LTS)**.
2. Bekræft, at du vil bruge EiraOS' automatiske installationsopsætning.
3. Vælg sprog og tastatur (dansk er forvalgt), netværk og **den disk, der skal bruges**. Installeren sletter kun den disk, du selv vælger.
4. Opret din bruger med adgangskode.
5. Genstart, og fjern USB-nøglen.

Ved første opstart gør `eira-firstboot` EiraOS til din standard-session, og du logger ind på login-skærmen som normalt. EiraOS er den eneste session, der kan vælges. Ubuntus egne sessioner (GNOME osv.) skjules af `eira-session-policy`, fordi Explorer ikke har nogen flugtvej (ADR-0001). Login-skærmen er kun infrastruktur, ikke brugerfladen.

Terminal, filer og andre klassiske værktøjer ligger i **Builder Mode** i EiraOS. Builder er slået fra, indtil IT tillader den med `EIRA_BUILDER_MODE_ALLOWED=1` i `/etc/eira/eira.conf`. Skal en maskine have hele Ubuntu-skrivebordet, for eksempel en IT-arbejdsstation, kan IT tilføje `EIRA_ALLOW_UBUNTU_SESSION=1` samme sted og genstarte. Så kommer sessionerne tilbage.

## Sådan testes installationen automatisk

CI installerer testbilledet i en virtuel maskine (QEMU/KVM, UEFI), booter den installerede disk og logger automatisk ind. Derefter tjekker `eira-ci-report` daemons, sockets, IPC, første boot, standard-session, at EiraOS er den eneste session, login-skærmen, labwc og EiraOS-shellen. Den tjekker også sikkerhedsgrænserne på den installerede pakke: gaten, modelprocessen, journalens segl og samtykkeagenten (setgid, gruppe, at kun agenten kan samtykke). Testbilledet installerer uden net fra et lokalt pakkearkiv. Resultatet står i artefaktet `vm-acceptance-logs`.

## Kendte begrænsninger i 1.0 RC1

- EiraOS-shellen har kun strøm (sluk, genstart, dvale) gennem EiraSystemAPI. Netværk, lyd og indstillinger mangler (se [udviklingsplanen](UDVIKLINGSPLAN.md)).
- Login går gennem GDM med en almindelig Ubuntu-bruger. Kontekster med én Linux-bruger pr. kontekst ([ADR-0005](decisions/ADR-0005-kontekster-og-datas-hjem.md)) er ikke implementeret endnu.
- Samtykkeagentens beskyttelse mod clickjacking (R-6.2) er afprøvet mod en headless labwc i CI, men endnu ikke i en grafisk session (UDVIKLINGSPLAN F0.2).
- Installationen kræver netværk.
- Fejler installationen, pakkes logs i `/var/log/installer/eira-error-logs.tgz` i installer-miljøet. Hent dem før genstart.
