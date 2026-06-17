// components.css first so globals.css (the newer FaceCheck-style layout + the
// circular score badge) wins any class it intentionally overrides.
import '../components/components.css';
import './globals.css';
import Disclaimer from '@/components/Disclaimer';

export const metadata = {
  title: 'Omnividence — Face Similarity Search',
  description:
    'School demo: approximate visual face-similarity search over public images. Does not confirm identity.',
};

// Root layout. The Disclaimer is rendered HERE (the single mandated render site)
// in a sticky position so the sentence "Results are approximate visual similarity
// matches and do not confirm identity." is ALWAYS visible on every page and state.
export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <Disclaimer />
        {children}
      </body>
    </html>
  );
}
