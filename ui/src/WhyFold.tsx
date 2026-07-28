interface Props {
  open: boolean;
  bullets: string[];
  onToggle: () => void;
}

export function WhyFold({ open, bullets, onToggle }: Props) {
  if (bullets.length === 0) return null;

  return (
    <div className="why-fold">
      <button
        type="button"
        className="why-fold-trigger"
        aria-expanded={open}
        onClick={onToggle}
      >
        Hvorfor ser jeg dette?
        <span className="why-fold-chevron" aria-hidden>
          {open ? "⌄" : "›"}
        </span>
      </button>
      {open && (
        <div className="why-fold-body fade-in">
          <p className="why-fold-kicker">Fordi</p>
          <ul className="why-fold-list">
            {bullets.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
