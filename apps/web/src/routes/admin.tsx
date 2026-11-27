import {fetchSession} from '@better-auth-ui/core';
import {type JSX, type SyntheticEvent, useEffect, useState} from 'react';
import {redirect} from 'react-router';

import {Badge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {Input} from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

import type {Accounts} from '../contract/contract.ts';
import {authClient, queryClient} from '../session/auth-client.ts';
import {SessionClient} from '../session/client.ts';
import {ThemeProvider} from '../theme/theme-provider.tsx';

/** The admin page's title. */
export function meta(): Array<{title: string}> {
  return [{title: 'Chips · Doggybank'}];
}

/** Sends a visitor without a session to sign in, and back here after. */
export async function clientLoader(): Promise<null> {
  const session = await fetchSession(queryClient, authClient);
  if (session === null) throw redirect('/auth/sign-in?redirectTo=%2Fadmin');
  return null;
}

/** The empty page shown until the accounts load. */
export function HydrateFallback(): JSX.Element {
  return <main className="flex min-h-svh p-6" />;
}

/** Every account's chips, and grants from the treasury, for an internal account. */
export default function Admin(): JSX.Element {
  const [client] = useState(() => new SessionClient());
  const [accounts, setAccounts] = useState<Accounts | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    client.accounts().then(setAccounts, (caught: unknown) => {
      setError(caught instanceof Error ? caught.message : String(caught));
    });
  }, [client]);

  return (
    <ThemeProvider>
      <main className="mx-auto flex min-h-svh max-w-3xl flex-col gap-6 p-6">
        <h1 className="text-2xl font-semibold tracking-tight">Chips</h1>
        {error !== null && <p role="alert">{error}</p>}
        {accounts !== null && (
          <>
            <GrantForm client={client} onGranted={setAccounts} />
            <AccountTable accounts={accounts} />
          </>
        )}
      </main>
    </ThemeProvider>
  );
}

function GrantForm({
  client,
  onGranted,
}: {
  readonly client: SessionClient;
  readonly onGranted: (accounts: Accounts) => void;
}): JSX.Element {
  const [email, setEmail] = useState('');
  const [amount, setAmount] = useState('');
  const [error, setError] = useState<string | null>(null);

  async function grant(event: SyntheticEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    try {
      onGranted(await client.grant(email, Number(amount)));
      setAmount('');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={event => {
        void grant(event);
      }}
    >
      <div className="flex gap-2">
        <Input
          aria-label="Email"
          placeholder="Email"
          type="email"
          value={email}
          onChange={event => {
            setEmail(event.target.value);
          }}
        />
        <Input
          aria-label="Chips"
          placeholder="Chips"
          type="number"
          min={1}
          step={1}
          value={amount}
          onChange={event => {
            setAmount(event.target.value);
          }}
        />
        <Button type="submit" disabled={email === '' || amount === ''}>
          Grant
        </Button>
      </div>
      {error !== null && <p role="alert">{error}</p>}
    </form>
  );
}

function AccountTable({accounts}: {readonly accounts: Accounts}): JSX.Element {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Account</TableHead>
          <TableHead>Kind</TableHead>
          <TableHead className="text-right">Chips</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {accounts.accounts.map(account => (
          <TableRow key={account.id}>
            <TableCell>{account.email ?? account.id}</TableCell>
            <TableCell>
              {account.kind !== null && (
                <Badge variant="secondary">{account.kind}</Badge>
              )}
            </TableCell>
            <TableCell className="text-right">
              {account.balance.toLocaleString()}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
