# Installér EiraOS på en pc

EiraOS installeres fra et ISO, der er bygget på Ubuntu 24.04 LTS' officielle installer. Installeren spørger om sprog, tastatur, netværk, disk og bruger. Efter genstart starter maskinen direkte i EiraOS-sessionen.

## Krav

- amd64-pc med UEFI eller BIOS, mindst 4 GB RAM og 25 GB disk
- Internetforbindelse under installationen (Ubuntu-pakker hentes fra arkivet)
- USB-nøgle på mindst 4 GB

## 1. Hent eller byg ISO'et

**Fra CI:** Kør workflowet *Ubuntu 24.04 Packaging Acceptance* (fanen Actions → Run workflow), og hent artefaktet `eira-installer-iso-ubuntu-24.04-amd64`.

**Lokalt på Ubuntu 24.04:**

```bash
sudo apt install xorriso gnupg curl
scripts/build_deb.sh --output-dir dist
BASE=$(scripts/fetch_ubuntu_iso.sh)
scripts/build_iso.sh --base-iso "$BASE" --deb dist/eira-os-core.deb --output-dir dist
```

`fetch_ubuntu_iso.sh` henter det nyeste Ubuntu 24.04 live-server-ISO og afviser det, hvis `SHA256SUMS` ikke er signeret med Canonicals CD-image-nøgle, eller hvis checksummen ikke passer. Resultatet er `dist/EiraOS-1.0-RC1-amd64.iso` med `.sha3-256` og `.build-info.json`.

## 2. Skriv ISO'et til en USB-nøgle

```bash
sudo dd if=dist/EiraOS-1.0-RC1-amd64.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

Erstat `/dev/sdX` med USB-nøglen (tjek med `lsblk`). Alt på nøglen slettes. På Windows og macOS kan du bruge balenaEtcher.

## 3. Installér

1. Boot pc'en fra USB-nøglen, og vælg **Installér EiraOS (Ubuntu 24.04 LTS)**.
2. Bekræft, at du vil bruge EiraOS' autoinstall-konfiguration.
3. Vælg sprog og tastatur (dansk er forvalgt), netværk og **den disk, der skal bruges**. Installeren sletter kun den disk, du selv vælger.
4. Opret din bruger.
5. Genstart, og fjern USB-nøglen.

Ved første opstart binder `eira-firstboot` din bruger til EiraOS-sessionen, og skærmen skifter til EiraOS. Det kan tage op til et minut, mens cloud-init gør brugeren færdig.

## Kendte begrænsninger i 1.0 RC1

- Sessionen logger automatisk ind uden adgangskode; login i selve shellen kommer i en senere PR.
- Installationen kræver netværk; et offline-ISO kommer senere.
- Fejler installationen, pakkes logs i `/var/log/installer/eira-error-logs.tgz` i installer-miljøet. Hent dem før genstart (shell: Help → Enter shell).
