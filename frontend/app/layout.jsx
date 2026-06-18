import './globals.css';
import { IBM_Plex_Mono, Chakra_Petch } from 'next/font/google';
import Disclaimer from '@/components/Disclaimer';
import Header from '@/components/Header';
import Footer from '@/components/Footer';

const mono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-mono',
  display: 'swap',
});
const display = Chakra_Petch({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-display',
  display: 'swap',
});

export const metadata = {
  title: 'Omnividence — Face Similarity Search',
  description:
    'School demo: approximate visual face-similarity search over public images. Does not confirm identity.',
};

// Root layout. Flex-column shell: disclaimer + sticky header (logo top-left) +
// main (the 3 screens) + footer. The mandated disclaimer is always rendered.
export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${mono.variable} ${display.variable}`}>
      <body>
        <div className="app-shell">
          <div className="grid-overlay" aria-hidden="true" />
          <Disclaimer />
          <Header />
          <main className="app-main">{children}</main>
          <Footer />
        </div>
      </body>
    </html>
  );
}
