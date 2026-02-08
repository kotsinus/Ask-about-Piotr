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
  description: "Privacy policy for the Ask Piotr Synak demo"
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
            This website is a personal, non-commercial demo project showcasing professional
            experience and technical capabilities.
          </p>

          <p>
            The goal of this policy is to explain, in a clear and transparent way, how data is
            handled when you use this site.
          </p>

          <h2>1. What data is collected</h2>
          <p>
            This website does not collect personal data such as names, email addresses, accounts,
            or profiles.
          </p>
          <p>The only data processed during normal operation is:</p>
          <ul>
            <li>an anonymous session identifier stored in a strictly necessary cookie</li>
            <li>
              minimal technical request metadata required to operate the service (e.g. request
              timing)
            </li>
          </ul>
          <p>No form submissions, user accounts, or identifiers are required to use the site.</p>

          <h2>2. Cookies</h2>
          <p>This site uses one strictly necessary technical cookie:</p>
          <ul>
            <li>
              <strong>Purpose:</strong> maintain a short-lived anonymous session required for
              correct operation
            </li>
            <li>
              <strong>Type:</strong> first-party, HttpOnly
            </li>
            <li>
              <strong>Scope:</strong> functional only
            </li>
            <li>
              <strong>Lifetime:</strong> limited to the active session or a short technical
              duration
            </li>
          </ul>
          <p>This cookie:</p>
          <ul>
            <li>does not track users across websites</li>
            <li>does not enable profiling</li>
            <li>does not support advertising or analytics</li>
          </ul>
          <p>
            According to EU ePrivacy rules and GDPR, such cookies do not require user consent.
          </p>

          <h2>3. No tracking or analytics</h2>
          <p>This website does not use:</p>
          <ul>
            <li>Google Analytics</li>
            <li>marketing or advertising cookies</li>
            <li>third-party tracking pixels</li>
            <li>fingerprinting or cross-site tracking</li>
            <li>behavioral profiling</li>
          </ul>
          <p>There are no ads and no commercial tracking of any kind.</p>

          <h2>4. Interaction logging (privacy-first)</h2>
          <p>
            For technical debugging and quality monitoring, the backend may log interactions in a
            privacy-minimised form:
          </p>
          <ul>
            <li>IP addresses are never stored in raw form</li>
            <li>Any IP-derived data is anonymised or hashed</li>
            <li>Logs are used solely for operational reliability and abuse prevention</li>
            <li>Data is not shared with third parties</li>
          </ul>

          <h2>5. Data retention</h2>
          <p>
            Technical logs, if stored, are retained only for a limited period and are not used to
            identify individuals.
          </p>
          <p>No personal profiles or long-term behavioral histories are created.</p>

          <h2>6. Data sharing</h2>
          <p>No personal data is sold, shared, or transferred to third parties.</p>
          <p>
            External AI model providers may process request content only to generate responses, and
            only within the technical scope of the service.
          </p>

          <h2>7. Use of Artificial Intelligence</h2>
          <p>This website uses artificial intelligence (AI) models to generate answers to user questions.</p>
          <p>The AI system operates under the following principles:</p>
          <ul>
            <li>Evidence-based answers only</li>
            <li>
              Responses are generated exclusively from a curated, predefined knowledge base created
              by the site owner.
            </li>
            <li>The system is designed not to invent, guess, or extrapolate beyond available source material.</li>
          </ul>
          <p>No autonomous learning from users</p>
          <ul>
            <li>User interactions are not used to train or fine-tune AI models.</li>
          </ul>
          <p>No personal profiling</p>
          <ul>
            <li>The AI does not build user profiles, infer identities, or track individuals across sessions.</li>
          </ul>
          <p>Human-authored knowledge base</p>
          <ul>
            <li>
              All factual content originates from human-curated documents describing professional
              experience, projects, and publications.
            </li>
          </ul>
          <p>Model providers</p>
          <ul>
            <li>
              AI model providers may process request content transiently to generate responses.
            </li>
            <li>
              No personal data is intentionally submitted, and no long-term storage is controlled by this site.
            </li>
          </ul>

          <h2>8. Limitations and transparency</h2>
          <p>
            While AI is used to assist with information retrieval and summarisation:
          </p>
          <ul>
            <li>the system may refuse to answer if sufficient evidence is not available</li>
            <li>answers are constrained by the completeness of the underlying knowledge base</li>
            <li>AI output should be interpreted as informational, not advisory</li>
          </ul>
          <p>
            This design prioritises correctness, transparency, and responsible AI usage over
            conversational breadth.
          </p>

          <h2>9. Your rights</h2>
          <p>
            If you are located in the EU or Switzerland, you have rights under GDPR / revFADP,
            including the right to information and deletion.
          </p>
          <p>
            Because this site does not maintain personal user accounts or identifiable profiles,
            there is typically no personal data to retrieve or erase.
          </p>

          <h2>10. Contact</h2>
          <p>If you have any questions about privacy or data handling, you can contact:</p>
          <p>
            Piotr Synak
            <br />
            📧 ask.about.piotr@gmail.com
          </p>

          <h2>11. Changes to this policy</h2>
          <p>
            This policy may be updated if the technical architecture or data handling practices
            change.
          </p>
          <p>The date at the top indicates the latest revision.</p>
        </div>
      </div>
    </main>
  );
}

