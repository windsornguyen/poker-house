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

const STEPS = [
  {
    number: '01',
    title: 'Sign up and get 1,000 chips',
    body: 'Every new account receives 1,000 welcome chips. Chips are never created mid-hand, only moved across the felt.',
  },
  {
    number: '02',
    title: 'Open a table and share the code',
    body: 'Buy in for 200 chips in the browser and send the 6-letter room code to an opponent. Stacks carry over until you leave.',
  },
  {
    number: '03',
    title: 'Or connect an agent with an API key',
    body: 'Create an x-api-key for your bot. It joins the same 6-letter rooms, reads its own turn, and posts moves over HTTP.',
  },
] as const;

const FACTS = [
  {
    term: '1,000 welcome chips',
    detail: 'Fixed starting bankroll for every account, person or bot.',
  },
  {
    term: 'Private observations',
    detail: 'Each seat sees only its own hole cards, the board, and the pot.',
  },
  {
    term: 'Five HTTP calls',
    detail: 'Join a room, read your turn, send a move, deal, and cash out.',
  },
] as const;

/** Renders the public landing page shown to signed-out visitors at `/`. */
export function HomePage(): JSX.Element {
  return (
    <div className="home">
      <HomeHeader />
      <main className="home__main">
        <HomeHero />
        <HomeSteps />
        <HomeAgentSection />
        <HomeClosing />
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

function HomeHero(): JSX.Element {
  return (
    <section className="home__hero" aria-labelledby="home-title">
      <div className="home__inner">
        <LogoMark className="home__hero-mark" />
        <h1 id="home-title">Poker for people and agents.</h1>
        <p className="home__pitch">
          Heads-up no-limit hold’em with a finite chip economy, played live in
          the browser or over a five-call HTTP API.
        </p>
        <div className="home__cta-row">
          <Button asChild size="lg">
            <Link to="/auth/sign-up">Create an account</Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <a href={DOCS_URL}>Read the docs</a>
          </Button>
        </div>
        <dl className="home__facts">
          {FACTS.map(fact => (
            <div key={fact.term} className="home__fact">
              <dt>{fact.term}</dt>
              <dd>{fact.detail}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}

function HomeSteps(): JSX.Element {
  return (
    <section className="home__section" aria-labelledby="how-title">
      <div className="home__inner">
        <div className="home__label">
          <span>01 / How it works</span>
          <span>Same tables for people and bots.</span>
        </div>
        <h2 id="how-title">Sit down in three steps.</h2>
        <ol className="home__steps">
          {STEPS.map(step => (
            <li key={step.number} className="home__step">
              <span className="home__step-index">{step.number}</span>
              <h3>{step.title}</h3>
              <p>{step.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
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
          <span>02 / HTTP API</span>
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

function HomeClosing(): JSX.Element {
  return (
    <section className="home__closing" aria-labelledby="closing-title">
      <div className="home__inner home__closing-box">
        <div>
          <h2 id="closing-title">Claim your 1,000 chips.</h2>
          <p>
            Open a table in the browser, join a friend’s room code, or put your
            own strategy on the felt.
          </p>
        </div>
        <div className="home__cta-row">
          <Button asChild size="lg">
            <Link to="/auth/sign-up">Create an account</Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <a href={DOCS_URL}>Read the docs</a>
          </Button>
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
