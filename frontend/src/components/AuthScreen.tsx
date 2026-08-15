import { LockKeyhole, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api'
import type { AuthState } from '../types'
import { Button, Field, TextInput } from './ui'

export function AuthScreen({ state, onAuthenticated }: { state: AuthState; onAuthenticated: (state: AuthState) => void }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [setupToken, setSetupToken] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const next = state.setup_required
        ? await api.setup({ name, email, password, setup_token: setupToken })
        : await api.login(email, password)
      onAuthenticated(next)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to sign in')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <div className="auth-brand"><div className="brand__mark brand__mark--large"><span>J</span></div><div><strong>jobhunt</strong><small>SECURE CONTROL ROOM</small></div></div>
        <div className="auth-icon">{state.setup_required ? <ShieldCheck /> : <LockKeyhole />}</div>
        <span className="eyebrow">{state.setup_required ? 'First-time setup' : 'Welcome back'}</span>
        <h1>{state.setup_required ? 'Create the administrator.' : 'Sign in to continue.'}</h1>
        <p>{state.setup_required ? 'This first account owns user access and workspace data.' : 'Your profile, preferences, applications, and runs are private to your account.'}</p>
        <form onSubmit={submit} className="auth-form">
          {state.setup_required ? <Field label="Your name"><TextInput autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} required /></Field> : null}
          <Field label="Email"><TextInput type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></Field>
          <Field label="Password" hint={state.setup_required ? 'Use at least 10 characters.' : undefined}><TextInput type="password" autoComplete={state.setup_required ? 'new-password' : 'current-password'} minLength={state.setup_required ? 10 : 1} value={password} onChange={(event) => setPassword(event.target.value)} required /></Field>
          {state.setup_required && state.setup_token_required ? <Field label="Setup token" hint="Use the JOBHUNT_SETUP_TOKEN configured on the server."><TextInput type="password" value={setupToken} onChange={(event) => setSetupToken(event.target.value)} required /></Field> : null}
          {error ? <div className="auth-error" role="alert">{error}</div> : null}
          <Button type="submit" loading={busy}>{state.setup_required ? 'Create admin account' : 'Sign in'}</Button>
        </form>
      </section>
    </main>
  )
}
