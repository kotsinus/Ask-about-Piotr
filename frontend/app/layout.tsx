/*
 * Copyright 2026 Piotr Synak
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * Purpose:
 * Root layout for the Next.js app.
 */

import type { ReactNode } from "react";
import Link from "next/link";

import "./globals.css";

export const metadata = {
  title: "Ask Piotr Synak",
  description:
    "Grounded Q&A about Piotr Synak's experience, backed by curated knowledge cards with citations"
};

export default function RootLayout({
  children
}: {
  children: ReactNode;
}) {
  return (
    // Some browser extensions (e.g. grammar checkers) inject attributes into
    // <html> before React hydrates, which can cause hydration mismatch warnings.
    <html lang="en" suppressHydrationWarning>
      <body>
        <div className="site-root">
          <div className="site-content">{children}</div>
          <footer className="site-footer" aria-label="Site footer">
            <div className="site-footer-inner">
              <p className="site-footer-line">
                Privacy-first demo. This site uses a strictly necessary, anonymous session cookie
                to function correctly. No tracking, no analytics, no ads.{" "}
                <Link className="site-footer-link" href="/privacy-policy">
                  Privacy policy
                </Link>
              </p>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}

