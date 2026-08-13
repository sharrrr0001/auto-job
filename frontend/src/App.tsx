import {
  BriefcaseBusiness,
  Building2,
  ChevronLeft,
  Menu,
  Radio,
  Settings2,
  UserRound,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { ApplicationsPanel } from './components/ApplicationsPanel'
import { CompaniesPanel } from './components/CompaniesPanel'
import { Overview } from './components/Overview'
import { PreferencesEditor } from './components/PreferencesEditor'
import { ProfileEditor } from './components/ProfileEditor'
import { RunPanel } from './components/RunPanel'
import type { BootstrapData, Profile, RunOptions, Section } from './types'

const navigation = [
  { id: 'overview' as const, label: 'Overview', icon: Radio },
  { id: 'profile' as const, label: 'Profile', icon: UserRound },
  { id: 'preferences' as const, label: 'Search preferences', icon: Settings2 },
  { id: 'companies' as const, label: 'Companies', icon: Building2 },
  { id: 'applications' as const, label: 'Applications', icon: BriefcaseBusiness },
]

const blankProfile: Profile = {
  name: '',
  current_title: '',
  years_experience: 0,
  seniority: 'entry',
  education: '',
  summary: '',
  core_skills: [],
  interests: [],
  domains: [],
  target_titles: [],
  notable_projects: [],
}

function currentSection(): Section {
  const section = window.location.hash.replace('#/', '') as Section
  return navigation.some((item) => item.id === section) ? section : 'overview'
}

export default function App() {
  const [data, setData] = useState<BootstrapData | null>(null)
  const [section, setSection] = useState<Section>(currentSection)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [runOpen, setRunOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  const load = useCallback(async (quiet = false) => {
    try {
      const result = await api.bootstrap()
      setData(result)
      setError(null)
    } catch (reason) {
      if (!quiet) setError(reason instanceof Error ? reason.message : 'Unable to load the dashboard')
    }
  }, [])

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => { void load() })
    return () => window.cancelAnimationFrame(frame)
  }, [load])
  useEffect(() => {
    const sync = () => setSection(currentSection())
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])
  useEffect(() => {
    if (data?.run.status !== 'running') return
    const timer = window.setInterval(async () => {
      try {
        const run = await api.runStatus()
        setData((current) => current ? { ...current, run } : current)
        if (run.status !== 'running') void load(true)
      } catch { /* a later poll will recover */ }
    }, 1400)
    return () => window.clearInterval(timer)
  }, [data?.run.status, load])
  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 3200)
    return () => window.clearTimeout(timer)
  }, [toast])

  const profile = useMemo(() => ({ ...blankProfile, ...(data?.profile ?? {}) } as Profile), [data?.profile])

  const navigate = (next: Section) => {
    window.location.hash = `/${next}`
    setSection(next)
    setSidebarOpen(false)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const notifyError = (reason: unknown): never => {
    const message = reason instanceof Error ? reason.message : 'Something went wrong'
    setToast(`Error: ${message}`)
    throw reason
  }

  if (!data && !error) return <LoadingScreen />
  if (!data) return <ErrorScreen message={error ?? 'Unable to load'} retry={() => void load()} />

  const content = {
    overview: <Overview profile={profile} stats={data.stats} companies={data.companies} applications={data.applications} run={data.run} navigate={navigate} openRun={() => setRunOpen(true)} />,
    profile: <ProfileEditor profile={profile} onSave={async (next) => {
      try {
        const result = await api.saveProfile(next)
        setData((current) => current ? { ...current, profile: result.profile } : current)
        setToast(result.message)
        return result.profile
      } catch (reason) { return notifyError(reason) }
    }} />,
    preferences: <PreferencesEditor settings={data.settings} onSave={async (next) => {
      try {
        const result = await api.saveSettings(next)
        setData((current) => current ? { ...current, settings: result.settings } : current)
        setToast(result.message)
        return result.settings
      } catch (reason) { return notifyError(reason) }
    }} />,
    companies: <CompaniesPanel companies={data.companies} onSave={async (next) => {
      try {
        const result = await api.saveCompanies(next)
        setData((current) => current ? { ...current, companies: result.companies } : current)
        setToast(result.message)
        return result.companies
      } catch (reason) { return notifyError(reason) }
    }} />,
    applications: <ApplicationsPanel applications={data.applications} onToggle={async (job, applied) => {
      try {
        const result = await api.updateApplication(job.job_id, applied)
        setData((current) => current ? {
          ...current,
          stats: result.stats,
          applications: current.applications.map((item) => item.job_id === job.job_id ? result.job : item),
        } : current)
        setToast(applied ? 'Marked as applied' : 'Moved back to tracked')
      } catch (reason) { notifyError(reason) }
    }} />,
  }[section]

  const startRun = async (options: RunOptions) => {
    try {
      const run = await api.startRun(options)
      setData((current) => current ? { ...current, run } : current)
      setToast('Pipeline started')
    } catch (reason) { notifyError(reason) }
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? 'sidebar--open' : ''}`}>
        <div className="brand"><div className="brand__mark"><span>J</span></div><div><strong>jobhunt</strong><small>CONTROL ROOM</small></div></div>
        <button className="sidebar__close" type="button" aria-label="Close navigation" onClick={() => setSidebarOpen(false)}><X size={20} /></button>
        <nav>
          <span className="nav-label">Workspace</span>
          {navigation.map((item) => <button key={item.id} className={section === item.id ? 'active' : ''} onClick={() => navigate(item.id)}><item.icon size={18} /><span>{item.label}</span>{item.id === 'applications' && data.stats.applied ? <i>{data.stats.applied}</i> : null}</button>)}
        </nav>
        <div className="sidebar__bottom">
          <div className="mini-profile"><div>{(profile.name || '?').split(' ').map((part) => part[0]).slice(0, 2).join('').toUpperCase()}</div><span><strong>{profile.name || 'Candidate'}</strong><small>{profile.seniority} profile</small></span></div>
          <button className="collapse-button" type="button" title="Navigation stays expanded on desktop"><ChevronLeft size={16} /></button>
        </div>
      </aside>
      {sidebarOpen ? <button className="mobile-scrim" onClick={() => setSidebarOpen(false)} aria-label="Close navigation" /> : null}

      <main>
        <div className="mobile-bar"><button type="button" onClick={() => setSidebarOpen(true)} aria-label="Open navigation"><Menu size={20} /></button><div className="brand"><div className="brand__mark"><span>J</span></div><strong>jobhunt</strong></div><button className={`mobile-run ${data.run.status === 'running' ? 'active' : ''}`} onClick={() => setRunOpen(true)}><Radio size={18} /></button></div>
        {error ? <div className="connection-banner">Dashboard refresh failed: {error}. Showing the most recent data.<button onClick={() => void load()}>Retry</button></div> : null}
        <div className="page-wrap">{content}</div>
      </main>

      <RunPanel open={runOpen} run={data.run} onClose={() => setRunOpen(false)} onStart={startRun} />
      {toast ? <div className={`toast ${toast.startsWith('Error:') ? 'toast--error' : ''}`} role="status">{toast}</div> : null}
    </div>
  )
}

function LoadingScreen() {
  return <div className="loading-screen"><div className="brand__mark brand__mark--large"><span>J</span></div><div className="loading-line"><i /></div><p>Preparing your control room…</p></div>
}

function ErrorScreen({ message, retry }: { message: string; retry: () => void }) {
  return <div className="error-screen"><div className="brand__mark brand__mark--large"><span>J</span></div><span className="eyebrow">Connection problem</span><h1>The control room is offline.</h1><p>{message}</p><button className="button button--primary" onClick={retry}>Try again</button></div>
}
