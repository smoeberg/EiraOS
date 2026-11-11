# EIRA Policy Compiler � arkitektur v0.1

**Status:** Normativ � governance-agent kerne  
**Dato:** 26. juni 2026  
**Relateret:** [EIRA_Glue_Layer_Engineering_v0.1.md](EIRA_Glue_Layer_Engineering_v0.1.md)

---

## 1. Scope

`eira-policy-engine` er Rust-modul i `eira-governance-agent`. Det overs�tter **EIRA Policy YAML** til subsystem-specifikke konfigurationsfiler � med validering, snapshot og rollback.

**Ikke i scope Sprint 0�1:** cross-subsystem constraint rules.

---

## 2. Komponentmodel

```
eira-governance-agent
??? fleet-client          # mTLS, heartbeat, bundle apply
??? policy-engine
?   ??? schema/           # JSON Schema per policy version
?   ??? compiler/         # YAML ? intermediate representation (IR)
?   ??? validator/        # IR consistency checks
?   ??? backends/
?       ??? network.rs    # NetworkManager keyfiles
?       ??? apparmor.rs   # /etc/apparmor.d/eira-*
?       ??? udev.rs       # /etc/udev/rules.d/99-eira-*
?       ??? flatpak.rs    # flatpak override commands
?       ??? falco.rs      # falco_rules.local.yaml
?       ??? identity.rs   # identityd + sssd drop-ins
?       ??? systemd.rs    # unit drop-ins
??? applier/              # staged apply + rollback
??? prober/               # post-apply health
```

---

## 3. Policy YAML � versioneret skema

```yaml
version: "1.0"
org_unit: "OU=Pilot,DC=kommune,DC=dk"

vpn:
  profiles:
    - id: corp-anyconnect
      type: openconnect
      gateway: vpn.kommune.dk
      always_on: true
      pre_login: true
      machine_cert: /etc/eira/certs/machine/client.pem

apps:
  flatpak_whitelist:
    - org.libreoffice.LibreOffice
    - com.microsoft.Edge

usb:
  allow:
    - class: smartcard
    - vendor_id: "0x1234"  # specifik dongle

security:
  falco_rules:
    - name: eira_block_unauthorized_shell
      condition: spawned_process and proc.name in (bash, sh)
```

**Schema-validering f�r compile** � ukendte n�gler = hard fail.

---

## 4. Intermediate Representation (IR)

Alle backends modtager typed IR � ikke r� YAML:

```json
{
  "policy_id": "uuid",
  "compiled_at": "iso8601",
  "backends": {
    "network": { "connections": [...] },
    "udev": { "rules": [...] },
    "apparmor": { "profiles": [...] }
  },
  "cross_constraints": []
}
```

Cross-constraints tom i v1.0. v1.1+:

```json
"cross_constraints": [
  { "id": "usb_requires_vpn", "expr": "usb.storage_allowed IMPLIES network.vpn_connected" }
]
```

---

## 5. Backend-kontrakt

Hver backend implementerer:

```rust
trait PolicyBackend {
    fn name(&self) -> &'static str;
    fn compile(&self, ir: &PolicyIR) -> Result<StagedFiles>;
    fn validate(&self, staged: &StagedFiles) -> Result<()>;
    fn apply(&self, staged: &StagedFiles) -> Result<()>;
    fn rollback(&self, snapshot: &Snapshot) -> Result<()>;
    fn probe(&self) -> ProbeResult;  // green | yellow | red
}
```

**StagedFiles:** skrives kun til `/var/lib/eira/policy-staging/<policy_id>/` indtil apply.

---

## 6. Validering per backend

| Backend | Validator |
|---------|-----------|
| apparmor | `apparmor_parser -Q` p� hver profil |
| network | `nmcli connection load` dry-run; `nmcli con show` |
| udev | `udevadm test` p� syntetisk event |
| flatpak | `flatpak info` for hver whitelisted app |
| falco | `falco --validate` |
| systemd | `systemd-analyze verify` |

---

## 7. Snapshot og rollback

F�r hver apply:

```
/var/lib/eira/policy-snapshots/<timestamp>/
  ??? manifest.json
  ??? etc/NetworkManager/system-connections/  (copy)
  ??? etc/apparmor.d/                         (copy)
  ??? ...
```

Rollback = restore + `systemctl reload` per backend + probe.

**Retention:** sidste 5 snapshots lokalt; metadata til Fleet.

---

## 8. Fleet-integration

| Event | Payload |
|-------|---------|
| `policy.compile.started` | policy_id, version |
| `policy.compile.failed` | errors[] per backend |
| `policy.apply.succeeded` | probe results |
| `policy.apply.rolled_back` | reason, snapshot_id |

IT Portal viser **diff preview** (P2) f�r apply p� >N enheder.

---

## 9. Teststrategi

| Niveau | Test |
|--------|------|
| Unit | Hver backend compile med golden YAML fixtures |
| Integration | VM: apply ? probe green; inject bad rule ? rollback |
| Chaos | Partial apply fail ? assert previous policy active |
| Fleet | Staged rollout 5% ? 100% med compliance gate |

---

## 10. Sprint 0�1 leverance

- [ ] JSON Schema `policy-schema` v1.0  
- [ ] Backends: `network`, `falco`, `flatpak`  
- [ ] Applier + snapshot (network only)  
- [ ] Prober for sssd + network + governance heartbeat  

---

## Relaterede dokumenter (operationalisering)

| Spørgsmål | Dokument |
|-----------|----------|
| Bundle-versionering og rollback | [Update Release Train](../../eira-fleet-control/docs/specs/EIRA_Update_Release_Train_v0.1.md) |
| CVE, RACI, drift | [OSS Operations Model](EIRA_OSS_Operations_Model_v0.1.md) |
| Fleet rollout | [Fleet Control](../../eira-fleet-control/docs/specs/EIRA_Fleet_Control_v0.1.md) |
| Navigation | [Document Map](../EIRA_Document_Map_v0.1.md) |

---

*EIRA Policy Compiler v0.1*
