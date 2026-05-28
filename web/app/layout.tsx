import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Navesink — Municipal Permitting Assistant',
  description: 'AI-powered permitting assistant for Red Bank and Fair Haven, NJ',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className={`${inter.className} h-full flex flex-col`}>
        {/* Legal disclaimer — always visible, cannot be dismissed */}
        <div className="shrink-0 bg-amber-50 border-b border-amber-200 px-4 py-2">
          <p className="text-center text-xs text-amber-800 leading-snug">
            <span className="font-semibold">⚠ Legal Disclaimer:</span>{' '}
            Navesink is an AI-powered informational tool and does not constitute legal, zoning, or
            professional advice. Always verify information with your borough&apos;s official offices
            or a licensed professional before making permitting decisions.
          </p>
        </div>
        <div className="flex-1 flex flex-col overflow-hidden">
          {children}
        </div>
      </body>
    </html>
  );
}
