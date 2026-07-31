# Veritas Shield EiraOS Integration (`veritas-shield-eiraos-integration`)

Kryptografisk verificerbar, narrativt intelligent og brugercentreret platform til informationsvurdering integreret direkte i **EiraOS**.

## Arkitektur & Lag

- **EUDI Wallet Bridge (Lag 2 - Kryptografisk Tillid):** eIDAS 2.0 / QEAA validering af digitale signaturer på udgivelser.
- **Lag 1: Artikelanalyse (Det Røde Skjold):** Regelbaseret motor (200 faste parametre uden AI-hallucination) for risikoprofilering.
- **Lag 2: Afsenderprofil (Det Grønne Skjold):** Whitelisting/blacklisting og EUDI-verifikation af medier og journalister.
- **Lag 3: Narrativ Kortlægning (Det Blå Skjold):** Mønstergenkendelse over tid i **EiraOS Temporal Graph (SQLite)** med Mistral AI.
- **Attention Management & Cognitive Shielding:** Støjdæmpning, "Læse-tilstand" og intentionsbaseret filtrering i EiraOS.
- **Enterprise Governance (ECK Integration):** Audit trail og compliance-pipeline for offentlige og private organisationer.

## Mappe-struktur

```
veritas-shield-eiraos-integration/
├── adapters/
│   ├── eudi-wallet-adapter/       # Adapter for EUDI Wallet & QEAA signaturvalidering
│   └── temporal-graph-adapter/   # SQLite Temporal Graph adapter for EiraOS
├── lag1-article-analysis/        # 200 Regelbaserede parametre & Python rule engine
├── lag2-sender-profiling/        # Whitelist, blacklist & review-processer
├── lag3-narrative-mapping/       # LLM Prompts & visualisering af narrativer over tid
├── enterprise-governance/        # Audit trail & ECK compliance-modul
└── README.md
```

## Hurtig start

1. **Test Lag 1 Regel-motoren:**
   ```bash
   python3 lag1-article-analysis/rule_engine.py
   ```

2. **Test EUDI Wallet Adapter (Mock):**
   ```bash
   python3 adapters/eudi-wallet-adapter/app.py
   ```
