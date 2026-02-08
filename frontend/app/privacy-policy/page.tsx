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
 * Privacy policy page.
 */

export const metadata = {
  title: "Privacy Policy",
  description: "Privacy policy for the Ask Piotr Synak demo",
};

export default function PrivacyPolicyPage() {
  return (
    <main className="app-main">
      <div className="legal-page">
        <header className="legal-header">
          <h1>Privacy Policy</h1>
          <p className="muted">Last updated: February 2026</p>
        </header>

        <div className="legal-prose">
          <p>
            This website is a personal, non-commercial demo project showcasing
            professional experience and technical capabilities.
          </p>

          <p>
            The goal of this policy is to explain, in a clear and transparent
            way, how data is handled when you use this site.
          </p>

          <h2>1. Data controller</h2>
          <p>
            Data controller (site owner): <strong>Piotr Synak</strong>.
          </p>

          <h2>2. What data is collected</h2>
          <p>
            This website does not collect personal data such as names, email
            addresses, accounts, or profiles.
          </p>
          <p>The only data processed during normal operation is:</p>
          <ul>
            <li>an anonymous session identifier stored in a strictly necessary cookie</li>
            <li>minimal technical request metadata required to operate the service (e.g. request timing)</li>
          </ul>
          <p>
            No form submissions, user accounts, or identifiers are required to
            use the site.
          </p>

          <h2>3. Cookies</h2>
          <p>This site uses one strictly necessary technical cookie:</p>
          <ul>
            <li>
              <strong>Name:</strong> <code>ask_piotr_session_id</code>
            </li>
            <li>
              <strong>Purpose:</strong> store an anonymous session identifier
              required to maintain conversation continuity
            </li>
            <li>
              <strong>Type:</strong> first-party, HttpOnly, SameSite=Lax, Secure
              when served over HTTPS
            </li>
            <li>
              <strong>Scope:</strong> strictly functional
            </li>
            <li>
              <strong>Lifetime:</strong> up to 1 year (Max-Age: 31536000 seconds)
            </li>
          </ul>

          <p>This cookie:</p>
          <ul>
            <li>does not track users across websites</li>
            <li>does not enable profiling</li>
            <li>is not used for analytics or advertising</li>
          </ul>

          <p>
            Strictly necessary cookies are generally exempt from consent
            requirements under EU ePrivacy rules. You can still disable cookies
            in your browser, although some site functionality may not work
            correctly.
          </p>

          <h2>4. No tracking or analytics</h2>
          <p>This website does not use:</p>
          <ul>
            <li>Google Analytics</li>
            <li>marketing or advertising cookies</li>
            <li>third-party tracking pixels</li>
            <li>fingerprinting or cross-site tracking</li>
            <li>behavioral profiling</li>
          </ul>
          <p>There are no ads and no commercial tracking of any kind.</p>

          <h2>5. Interaction logging (privacy-first)</h2>
          <p>
            For operational reliability, abuse prevention, and debugging, the
            backend may process limited logs in a privacy-minimised form.
          </p>
          <ul>
            <li>Logs are used solely for reliability and abuse prevention</li>
            <li>Data is not sold and not used for advertising</li>
            <li>Retention is limited (see below)</li>
          </ul>

          <p className="muted">
            Note: infrastructure providers (hosting/CDN/reverse proxy) may
            transiently process technical connection data (including IP
            addresses) for security and delivery purposes.
          </p>

          <p className="muted">
            The service may also use an internal request header (
            <code>x-session-id</code>) to correlate requests during processing.
            This header is not stored in the browser.
          </p>

          <h2>6. Data retention</h2>
          <p>
            Technical logs, if stored, are retained only for a limited period
            and are not used to identify individuals.
          </p>
          <p>No personal profiles or long-term behavioral histories are created.</p>

          <h2>7. Data sharing</h2>
          <p>
            No personal data is sold, shared, or transferred to third parties
            for marketing purposes.
          </p>
          <p>
            To generate answers, the service may call external AI model
            providers. Those providers may process request content transiently
            to produce a response, within the technical scope of the service.
          </p>

          <h2>8. Use of Artificial Intelligence</h2>
          <p>
            This website uses artificial intelligence (AI) models to generate
            answers to user questions.
          </p>
          <p>The AI system operates under the following principles:</p>
          <ul>
            <li>Evidence-based answers only</li>
            <li>
              Responses are generated exclusively from a curated, predefined
              knowledge base created by the site owner.
            </li>
            <li>
              The system is designed not to invent, guess, or extrapolate beyond
              available source material.
            </li>
          </ul>

          <h3>No autonomous learning from users</h3>
          <ul>
            <li>User interactions are not used to train or fine-tune AI models.</li>
          </ul>

          <h3>No personal profiling</h3>
          <ul>
            <li>
              The AI does not build user profiles, infer identities, or track
              individuals across sessions.
            </li>
          </ul>

          <h3>Human-authored knowledge base</h3>
          <ul>
            <li>
              All factual content originates from human-curated documents
              describing professional experience, projects, and publications.
            </li>
          </ul>

          <h3>Model providers</h3>
          <ul>
            <li>
              AI model providers may process request content transiently to
              generate responses.
            </li>
            <li>
              No personal data is intentionally submitted. Where supported,
              privacy-preserving settings are preferred.
            </li>
          </ul>

          <h2>9. Limitations and transparency</h2>
          <p>While AI is used to assist with information retrieval and summarisation:</p>
          <ul>
            <li>the system may refuse to answer if sufficient evidence is not available</li>
            <li>answers are constrained by the completeness of the underlying knowledge base</li>
            <li>
              AI output should be interpreted as informational, not advisory (no
              legal/medical/financial advice)
            </li>
          </ul>
          <p>
            This design prioritises correctness, transparency, and responsible AI
            usage over conversational breadth.
          </p>

          <h2>10. Your rights</h2>
          <p>
            If you are located in the EU or Switzerland, you have rights under
            GDPR / revFADP, including the right to information and deletion.
          </p>
          <p>
            Because this site does not maintain personal user accounts or
            identifiable profiles, there is typically no personal data to
            retrieve or erase.
          </p>

          <h2>11. Contact</h2>
          <p>If you have any questions about privacy or data handling, you can contact:</p>
          <p>
            Piotr Synak
            <br />
            📧 ask.about.piotr@gmail.com
          </p>

          <h2>12. Changes to this policy</h2>
          <p>
            This policy may be updated if the technical architecture or data
            handling practices change.
          </p>
          <p>The date at the top indicates the latest revision.</p>
        </div>
      </div>
    </main>
  );
}
