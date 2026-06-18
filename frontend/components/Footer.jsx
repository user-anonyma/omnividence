// Footer — program name, copyright, and a link back to the GitHub repo.
export default function Footer() {
  return (
    <footer className="app-footer">
      <div className="app-footer__left">
        <span className="app-footer__name">OMNIVIDENCE</span>
        <span className="app-footer__dot" aria-hidden="true" />
        <span>© 2026 Omnividence</span>
      </div>
      <a
        className="app-footer__gh"
        href="https://github.com/user-anonyma/omnividence"
        target="_blank"
        rel="noopener noreferrer"
      >
        <span className="app-footer__gh-box" aria-hidden="true">
          ↗
        </span>
        github.com/user-anonyma/omnividence
      </a>
    </footer>
  );
}
