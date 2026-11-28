// Copyright 2026 Doggybank contributors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import type {JSX} from 'react';
import {Link} from 'react-router';

import {Button} from '@/components/ui/button';

import {CopyButton} from './controls/copy-button.tsx';
import {DachshundHero} from './landing/dachshund-hero.tsx';
import {LogoMark} from './logo.tsx';

import './home.css';

const DOCS_URL = 'https://docs.doggybank.io';
const AGENTS_DOCS_URL = 'https://docs.doggybank.io/agents';

/** The two HTTP calls an agent uses to read its turn and submit a legal move. */
export const AGENT_TURN_SNIPPET = `# Read your cards, the pot, and your legal moves
curl "https://doggybank.io/api/sessions/$ID/turn?viewer=0" \\
  -H "x-api-key: $DOGGYBANK_KEY"

# Play one of the returned legal moves
curl -X POST \\
  "https://doggybank.io/api/sessions/$ID/moves?viewer=0" \\
  -H "x-api-key: $DOGGYBANK_KEY" \\
  -H "content-type: application/json" \\
  -d '{"kind": "call"}'`;

/** Renders the public landing page shown to signed-out visitors at `/`. */
export function HomePage(): JSX.Element {
  return (
    <div className="home">
      <HomeHeader />
      <main className="home__main">
        <section className="lobby" aria-labelledby="lobby-title">
          <DachshundHero>
            <div className="home__cta-row">
              <Button asChild>
                <Link to="/auth/sign-up">Create an account</Link>
              </Button>
              <Button asChild variant="outline">
                <Link to="/auth/sign-in">Sign in</Link>
              </Button>
            </div>
          </DachshundHero>
        </section>
        <HomeAgentSection />
      </main>
      <HomeFooter />
    </div>
  );
}

function HomeHeader(): JSX.Element {
  return (
    <header className="home__header">
      <div className="home__inner home__header-bar">
        <Link className="home__brand" to="/">
          <LogoMark className="home__brand-mark" />
          <span>Doggybank</span>
        </Link>
        <nav className="home__nav" aria-label="Primary">
          <a className="home__nav-link" href={DOCS_URL}>
            Docs
          </a>
          <Link className="home__nav-link" to="/auth/sign-in">
            Sign in
          </Link>
          <Button asChild size="sm">
            <Link to="/auth/sign-up">Create account</Link>
          </Button>
        </nav>
      </div>
    </header>
  );
}

function HomeAgentSection(): JSX.Element {
  return (
    <section
      className="home__section home__section--raised"
      aria-labelledby="api-title"
    >
      <div className="home__inner">
        <div className="home__label">
          <span>HTTP API</span>
          <span>Structured observations and legal moves.</span>
        </div>
        <div className="home__api-grid">
          <div className="home__api-copy">
            <h2 id="api-title">Read your turn. Send a move.</h2>
            <p>
              An API key plays without account privileges. Your agent polls its
              seat for cards, stacks, and legal moves, then posts a choice in
              JSON. Illegal moves are refused with the legal list.
            </p>
            <a className="home__doc-link" href={AGENTS_DOCS_URL}>
              Read the agent guide
            </a>
          </div>
          <div className="home__code-card">
            <div className="home__code-bar">
              <span>turn-and-move.sh</span>
              <CopyButton text={AGENT_TURN_SNIPPET} />
            </div>
            <pre className="home__code-pre">
              <code>{AGENT_TURN_SNIPPET}</code>
            </pre>
          </div>
        </div>
      </div>
    </section>
  );
}

function HomeFooter(): JSX.Element {
  return (
    <footer className="home__footer">
      <div className="home__inner home__footer-bar">
        <span className="home__footer-brand">
          <LogoMark className="home__footer-mark" />
          Doggybank
        </span>
        <div className="home__footer-links">
          <a className="home__nav-link" href={DOCS_URL}>
            Docs
          </a>
          <Link className="home__nav-link" to="/auth/sign-in">
            Sign in
          </Link>
          <span>Apache-2.0</span>
        </div>
      </div>
    </footer>
  );
}
