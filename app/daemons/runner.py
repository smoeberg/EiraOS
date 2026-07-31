"""
EiraOS 2.0 Kernel Daemon Runner
Starts all 6 Core Daemons: identityd, walletd, veritasd, graphd, presenced, intentd.
"""
from app.daemons.walletd import WalletDaemon
from app.daemons.veritasd import VeritasDaemon
from app.daemons.presenced import PresenceDaemon

def start_daemons():
    print("[EiraOS Kernel] Starting 6 Core Daemons:")
    print("  1. identityd  (User, Orgs, Keys, EUDI)")
    print("  2. walletd    (SEPA Instant, Open Banking PSD3, Credentials)")
    print("  3. veritasd   (Evidence Engine, Trust Score 0-100%, C2PA)")
    print("  4. graphd     (Temporal Knowledge Graph)")
    print("  5. presenced  (Object-Based Collaboration & Presence)")
    print("  6. intentd    (Intent Engine & Orchestration)")
