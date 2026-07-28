# EIRA VPN Compatibility Matrix v0.1

**Status:** Skabelon — udfyldes ved teknisk pre-review  
**Dato:** 4. juli 2026  
**Formål:** Dokumentér hvilken VPN der virker på Ubuntu 24.04 + EIRA — inkl. pre-login og Always On  
**Relateret:**
- [EIRA_Windows_Technical_Parity_v0.1.md](EIRA_Windows_Technical_Parity_v0.1.md) §6
- [EIRA_Support_Matrix_v0.1.md](EIRA_Support_Matrix_v0.1.md)
- [EIRA_Strategic_Reality_Check_v0.1.md](EIRA_Strategic_Reality_Check_v0.1.md) §7

> **Pilot-gate:** Hvis organisationens VPN kun virker med proprietær klient **uden** Linux pre-login — **pilot aflyses eller hybrid** for den profil.

---

## 1. Sådan udfyldes matricen

| Status | Betydning |
|--------|-----------|
| ✅ **Grøn** | Testet på reference-PC; Always On + login-flow OK |
| ⚠️ **Gul** | Virker med begrænsning (fx ingen pre-login) |
| ❌ **Rød** | Virker ikke på Ubuntu — hybrid påkrævet |
| ⬜ **Ikke testet** | Skal testes før pilot-commit |

**Testmiljø:** EIRA reference-PC, Ubuntu 24.04.2, NetworkManager, governance-push profil.

---

## 2. Kompatibilitetsmatrix

| VPN / gateway | Linux-klient | Pre-login | Always On | Status | Noter |
|---------------|--------------|-----------|-----------|--------|-------|
| **WireGuard** | `wireguard` + NM | Via systemd unit | ✅ | ⬜ Ikke testet | Foretrukket for nye udrulninger |
| **OpenVPN** | NetworkManager | Mulig (systemd) | ✅ | ⬜ Ikke testet | Standard profil via governance |
| **IPsec (IKEv2)** | strongSwan | Mulig | ✅ | ⬜ Ikke testet | Central profil |
| **Cisco AnyConnect** | OpenConnect (OSS) | ⚠️ Afhænger af config | ⚠️ | ⬜ Ikke testet | OSS protokol-kompatibel |
| **Fortinet** | openfortivpn | ⚠️ | ⚠️ | ⬜ Ikke testet | Test SSL VPN version |
| **Palo Alto GlobalProtect** | OpenConnect / vendor | ⚠️ Ofte begrænset | ⚠️ | ⬜ Ikke testet | **Kritisk test** for mange kommuner |
| **Check Point** | Vendor / SNX | ❌ Ofte | ❌ | ⬜ Ikke testet | Hybrid sandsynlig |
| **Microsoft VPN** | WireGuard / SSTP | Varierer | ⚠️ | ⬜ Ikke testet | |

---

## 3. EIRA integration

| Lag | Funktion |
|-----|----------|
| **Governance agent** | Push `keyfile` / `nmconnection` til `/etc/NetworkManager/system-connections/` |
| **Policy YAML** | `vpn.required: true`, `vpn.profile_id`, `vpn.pre_login: true/false` |
| **Fleet** | Compliance: `vpn_connected == true` før `compliant` |
| **Factory Enroll** | VPN-profil kan pre-seedes ved første boot (kanal B) |

### Pre-login tunnel (systemd)

```
network-online.target
    → eira-vpn-prelogin.service (hvis policy kræver det)
    → NetworkManager connect vpn-profile
    → eira-identityd (Entra kan kræve netværk)
```

**Arkitektbeslutning:** Pre-login er **ikke** accepteret som "umuligt" — men skal **bevises per VPN** i denne matrix.

---

## 4. Testprotokol (per VPN-række)

| Trin | Handling | Pass |
|------|----------|------|
| 1 | Import profil via governance (ikke manuel GUI) | Profil aktiv |
| 2 | Reboot — VPN forbinder før bruger-login (hvis pre-login krævet) | Forbindelse op |
| 3 | Entra OIDC login over VPN | Session OK |
| 4 | Sluk VPN — compliance falder i Fleet | Alert |
| 5 | Sleep / resume | Reconnect ≤ 30s |
| 6 | Docking / Wi-Fi skift | Ingen manuel reconnect |

---

## 5. Fallback-beslutningstræ

Se [Strategic Reality Check](EIRA_Strategic_Reality_Check_v0.1.md) §7.

1. OpenConnect / openfortivpn / WireGuard  
2. Vendor Linux-klient  
3. Split tunnel + conditional access (Entra)  
4. Hybrid PC for berørte brugere  
5. Pilot scope reduceres  

---

## 6. Pilot-kommune — udfyldningsblok

| Felt | Værdi |
|------|-------|
| Organisation | *(udfyld)* |
| VPN-produkt | *(udfyld)* |
| Gateway version | *(udfyld)* |
| Testet af | *(navn, dato)* |
| Resultat | ✅ / ⚠️ / ❌ |
| Pre-login | Ja / Nej / N/A |
| Godkendt af IT-chef | *(signatur, dato)* |

---

*EIRA VPN Compatibility Matrix v0.1 — obligatorisk udfyldt før Fase 1 (~50 PC).*
