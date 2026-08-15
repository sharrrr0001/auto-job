import { Database, KeyRound, Plus, ShieldCheck, Trash2, UserCog, Users } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { AdminUser, User, UserInput } from '../types'
import { Button, Field, PageHeading, Panel, TextInput } from './ui'

const emptyUser: UserInput = { name: '', email: '', password: '', role: 'user' }

export function AdminPanel({ currentUser, notify }: { currentUser: User; notify: (message: string, error?: boolean) => void }) {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [draft, setDraft] = useState<UserInput>(emptyUser)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      setUsers((await api.adminUsers()).users)
    } catch (reason) {
      notify(reason instanceof Error ? reason.message : 'Unable to load users', true)
    } finally {
      setLoading(false)
    }
  }, [notify])

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => { void load() })
    return () => window.cancelAnimationFrame(frame)
  }, [load])

  const create = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    try {
      const result = await api.createUser(draft)
      setDraft(emptyUser)
      notify(result.message)
      await load()
    } catch (reason) {
      notify(reason instanceof Error ? reason.message : 'Unable to create user', true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page-enter">
      <PageHeading eyebrow="Access & data" title="Admin panel" description="Manage who can sign in and control each account’s stored job-search data." />
      <div className="admin-grid">
        <Panel className="admin-create">
          <div className="panel-title"><Plus size={18} /><div><h2>Add a user</h2><p>Create a private workspace and login.</p></div></div>
          <form className="form-stack" onSubmit={create}>
            <Field label="Name"><TextInput value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} required /></Field>
            <Field label="Email"><TextInput type="email" value={draft.email} onChange={(event) => setDraft({ ...draft, email: event.target.value })} required /></Field>
            <Field label="Temporary password" hint="At least 10 characters"><TextInput type="password" minLength={10} value={draft.password} onChange={(event) => setDraft({ ...draft, password: event.target.value })} required /></Field>
            <Field label="Access level"><select className="input" value={draft.role} onChange={(event) => setDraft({ ...draft, role: event.target.value as UserInput['role'] })}><option value="user">User</option><option value="admin">Administrator</option></select></Field>
            <Button type="submit" loading={busy}><Plus size={16} /> Create user</Button>
          </form>
        </Panel>

        <Panel className="admin-users">
          <div className="panel-title"><Users size={18} /><div><h2>User accounts</h2><p>{users.length} account{users.length === 1 ? '' : 's'} with isolated data.</p></div></div>
          {loading ? <div className="admin-loading">Loading users…</div> : <div className="user-list">
            {users.map((user) => <UserRow key={user.id} user={user} self={user.id === currentUser.id} reload={load} notify={notify} />)}
          </div>}
        </Panel>
      </div>
    </div>
  )
}

function UserRow({ user, self, reload, notify }: { user: AdminUser; self: boolean; reload: () => Promise<void>; notify: (message: string, error?: boolean) => void }) {
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)

  const action = async (work: () => Promise<{ message: string }>) => {
    setBusy(true)
    try {
      const result = await work()
      notify(result.message)
      await reload()
    } catch (reason) {
      notify(reason instanceof Error ? reason.message : 'Admin action failed', true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <article className={`user-row ${user.active ? '' : 'user-row--disabled'}`}>
      <div className="user-row__identity"><div>{initials(user.name)}</div><span><strong>{user.name}{self ? ' (you)' : ''}</strong><small>{user.email}</small></span></div>
      <div className="user-row__stats">
        <span><Database size={13} /> {user.data.tracked} roles</span><span>{user.data.companies} companies</span><span>{user.data.applied} applied</span>
      </div>
      <div className="user-row__controls">
        <label><ShieldCheck size={14} /><select aria-label={`Access level for ${user.name}`} value={user.role} disabled={self || busy} onChange={(event) => void action(() => api.updateUser(user.id, { role: event.target.value as 'admin' | 'user' }))}><option value="user">User</option><option value="admin">Admin</option></select></label>
        <Button variant="secondary" disabled={self || busy} onClick={() => void action(() => api.updateUser(user.id, { active: !user.active }))}>{user.active ? 'Disable login' : 'Enable login'}</Button>
      </div>
      <div className="user-row__password"><KeyRound size={15} /><TextInput aria-label={`New password for ${user.name}`} type="password" minLength={10} placeholder="New password" value={password} onChange={(event) => setPassword(event.target.value)} /><Button variant="secondary" disabled={password.length < 10 || busy} onClick={() => void action(async () => { const result = await api.updateUser(user.id, { password }); setPassword(''); return result })}>Reset</Button></div>
      <div className="user-row__danger">
        <Button variant="ghost" disabled={busy} onClick={() => { if (window.confirm(`Reset all profile, search, application, and run data for ${user.name}?`)) void action(() => api.resetUserData(user.id)) }}><UserCog size={15} /> Reset data</Button>
        {!self ? <Button variant="danger" disabled={busy} onClick={() => { if (window.confirm(`Permanently delete ${user.name} and all associated data?`)) void action(() => api.deleteUser(user.id)) }}><Trash2 size={15} /> Delete</Button> : null}
      </div>
    </article>
  )
}

function initials(name: string) {
  return name.split(/\s+/).map((part) => part[0]).slice(0, 2).join('').toUpperCase()
}
