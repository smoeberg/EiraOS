"""
EiraOS 2.0 Kernel Daemon Runner
Starts system daemons: capabilityd, identityd, walletd, veritasd, graphd, presenced, contextd, intentd.
"""
def start_daemons():
    print("[EiraOS Kernel] Starting Capability Engine & System Daemons:")
    print("  0. capabilityd (Central OS Bus, Capability Router, Policy Gate)")
    print("  1. identityd   (User, Orgs, Keys, EUDI)")
    print("  2. walletd     (Financial OS: SEPA, Open Banking PSD3)")
    print("  3. veritasd    (Evidence Engine 0-100%, C2PA)")
    print("  4. graphd      (Temporal Knowledge Graph)")
    print("  5. presenced   (Object Presence & Active Collaboration)")
    print("  6. contextd    (Life Context: Arbejde, Privat, Rejse)")
    print("  7. intentd     (Intent Engine & Orchestration)")
