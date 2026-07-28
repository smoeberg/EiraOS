import { useCallback, useEffect, useState } from "react";
import {
  clearSessionId,
  fetchOidcConfig,
  getSessionId,
  mockLogin,
  startOidcLogin,
  type OidcConfig,
} from "./api";

type Props = {
  actorId?: string;
  onAuthChange: () => void;
};

export function AuthButton({ actorId, onAuthChange }: Props) {
  const [config, setConfig] = useState<OidcConfig | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasSession = Boolean(getSessionId() || actorId);

  useEffect(() => {
    fetchOidcConfig()
      .then(setConfig)
      .catch(() => setConfig(null));
  }, []);

  const handleLogin = useCallback(async () => {
    if (!config) return;
    setError(null);
    setBusy(true);
    try {
      if (config.mock_enabled) {
        await mockLogin({
          email: "mette@kommune.dk",
          name: "Mette",
          org_unit: "Kommune",
        });
        onAuthChange();
      } else {
        startOidcLogin();
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Login fejlede");
      setBusy(false);
    }
  }, [config, onAuthChange]);

  const handleLogout = useCallback(() => {
    clearSessionId();
    onAuthChange();
  }, [onAuthChange]);

  if (!config) return null;

  if (hasSession) {
    const label = actorId ?? "Logget ind";
    return (
      <div className="auth-control">
        <span className="auth-user" title={label}>
          {label}
        </span>
        <button type="button" className="auth-btn auth-btn--ghost" onClick={handleLogout}>
          Log ud
        </button>
      </div>
    );
  }

  return (
    <div className="auth-control">
      {error && <span className="auth-error">{error}</span>}
      <button
        type="button"
        className="auth-btn"
        onClick={handleLogin}
        disabled={busy}
      >
        {busy ? "Logger ind…" : config.mock_enabled ? "Log ind (dev)" : "Log ind med Entra"}
      </button>
    </div>
  );
}
