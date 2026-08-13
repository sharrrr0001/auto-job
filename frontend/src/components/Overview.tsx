import { ArrowRight, BriefcaseBusiness, Building2, CheckCircle2, CircleDot, MapPin, Radio, Sparkles, Target } from 'lucide-react'
import type { Application, Company, Profile, RunState, Section, Stats } from '../types'
import { profileSignal } from '../utils'
import { Button, PageHeading, Panel } from './ui'

export function Overview({
  profile,
  stats,
  companies,
  applications,
  run,
  navigate,
  openRun,
}: {
  profile: Profile
  stats: Stats
  companies: Company[]
  applications: Application[]
  run: RunState
  navigate: (section: Section) => void
  openRun: () => void
}) {
  const shortlisted = applications.filter((job) => (job.score ?? 0) >= 7).length
  const recent = applications.slice(0, 4)

  return (
    <div className="page-enter">
      <PageHeading
        eyebrow="Daily command center"
        title={`Good ${dayPart()}, ${firstName(profile.name)}.`}
        description="Your search agent is configured and ready. Here’s the signal across your current pipeline."
        action={<Button onClick={openRun}><Radio size={16} /> {run.status === 'running' ? 'View live run' : 'Run job search'}</Button>}
      />

      <section className="metrics-grid" aria-label="Job search metrics">
        <Metric icon={<BriefcaseBusiness />} label="Roles tracked" value={stats.tracked} detail="Across every discovery run" tone="ink" />
        <Metric icon={<Sparkles />} label="Strong matches" value={shortlisted} detail="Scored 7.0 or higher" tone="coral" />
        <Metric icon={<CheckCircle2 />} label="Applications" value={stats.applied} detail={stats.tracked ? `${Math.round((stats.applied / stats.tracked) * 100)}% of tracked roles` : 'Ready when you are'} tone="green" />
        <Metric icon={<Building2 />} label="Watched companies" value={companies.length} detail="Across 3 supported ATSs" tone="amber" />
      </section>

      <div className="overview-grid">
        <Panel className="overview-grid__main">
          <div className="section-heading"><div><span className="eyebrow">Latest intelligence</span><h2>Recently discovered</h2></div><button onClick={() => navigate('applications')}>View all <ArrowRight size={15} /></button></div>
          <div className="recent-list">
            {recent.map((job) => (
              <a href={job.url} target="_blank" rel="noreferrer" className="recent-job" key={job.job_id}>
                <div className="recent-job__brand">{job.company.slice(0, 2).toUpperCase()}</div>
                <div className="recent-job__copy"><strong>{job.title}</strong><span>{job.company}<i>·</i><MapPin size={12} />{job.location || 'Not listed'}</span></div>
                <div className="recent-job__score"><span>Match</span><strong>{job.score == null ? '—' : job.score.toFixed(1)}</strong></div>
                <ArrowRight size={16} className="recent-job__arrow" />
              </a>
            ))}
            {!recent.length ? <div className="empty-inline"><CircleDot size={22} /><div><strong>No tracked roles yet</strong><span>Start a mock run to see the pipeline in action.</span></div></div> : null}
          </div>
        </Panel>

        <Panel className="agent-card">
          <div className="agent-card__top"><span className={`status-pulse status-pulse--${run.status}`} /><span className="eyebrow">Agent status</span></div>
          <h2>{runTitle(run.status)}</h2>
          <p>{runDescription(run)}</p>
          <div className="agent-steps">
            {['Fetch public boards', 'Filter for relevance', 'Score & draft'].map((step, index) => <div key={step}><span>{index + 1}</span><strong>{step}</strong></div>)}
          </div>
          <Button variant="secondary" onClick={openRun}>{run.status === 'running' ? 'Open live console' : 'Configure a run'} <ArrowRight size={15} /></Button>
        </Panel>

        <Panel className="profile-health">
          <div className="profile-health__score"><svg viewBox="0 0 44 44" aria-hidden="true"><circle cx="22" cy="22" r="18" /><circle cx="22" cy="22" r="18" style={{ strokeDasharray: `${profileSignal(profile) * 1.13} 113` }} /></svg><strong>{profileSignal(profile)}%</strong></div>
          <div><span className="eyebrow">Candidate signal</span><h2>{profileSignal(profile) >= 80 ? 'Profile is in strong shape' : 'Your profile needs detail'}</h2><p>{profileSignal(profile) >= 80 ? 'The agent has enough context to assess fit with confidence.' : 'Add interests, proof of work, and a focused summary for better matches.'}</p></div>
          <button onClick={() => navigate('profile')}>Review profile <ArrowRight size={15} /></button>
        </Panel>

        <Panel className="focus-card">
          <div className="focus-card__icon"><Target size={20} /></div>
          <span className="eyebrow">Current focus</span>
          <h2>{profile.target_titles[0] || 'Set a target role'}</h2>
          <div className="focus-tags">{profile.interests.slice(0, 3).map((interest) => <span key={interest}>{interest}</span>)}</div>
          <button onClick={() => navigate('profile')}>Tune direction <ArrowRight size={15} /></button>
        </Panel>
      </div>
    </div>
  )
}

function Metric({ icon, label, value, detail, tone }: { icon: React.ReactNode; label: string; value: number; detail: string; tone: string }) {
  return <article className={`metric metric--${tone}`}><div className="metric__icon">{icon}</div><div><span>{label}</span><strong>{value.toLocaleString()}</strong><small>{detail}</small></div></article>
}

function firstName(name: string) {
  return name?.trim().split(/\s+/)[0] || 'there'
}

function dayPart() {
  const hour = new Date().getHours()
  if (hour < 12) return 'morning'
  if (hour < 18) return 'afternoon'
  return 'evening'
}

function runTitle(status: RunState['status']) {
  if (status === 'running') return 'Discovery is in progress'
  if (status === 'succeeded') return 'Last run completed'
  if (status === 'failed') return 'Last run needs attention'
  return 'Ready for the next search'
}

function runDescription(run: RunState) {
  if (run.status === 'running') return 'Jobs are moving through the fetch, filter, and scoring funnel now.'
  if (run.status === 'succeeded') return `Completed ${formatRelative(run.finished_at)}. Your tracker is up to date.`
  if (run.status === 'failed') return 'Open the console to inspect the final output and retry safely.'
  return 'Run the real pipeline or test the complete flow with bundled mock data.'
}

function formatRelative(value: string | null) {
  if (!value) return 'recently'
  const minutes = Math.round((Date.now() - new Date(value).getTime()) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  if (minutes < 1440) return `${Math.round(minutes / 60)}h ago`
  return `${Math.round(minutes / 1440)}d ago`
}
