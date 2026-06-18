import Link from 'next/link';

// Sticky header — the Omnividence logo (wordmark) pinned top-left. Clicking it
// returns to the landing screen.
export default function Header() {
  return (
    <header className="app-header">
      <Link href="/" aria-label="Omnividence home" style={{ display: 'block' }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img className="app-header__logo" src="/logo.png" alt="Omnividence" />
      </Link>
    </header>
  );
}
