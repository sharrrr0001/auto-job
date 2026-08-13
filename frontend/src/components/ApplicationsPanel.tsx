import { ArrowUpRight, Briefcase, Check, Mail, MapPin, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { Application } from '../types'
import { PageHeading, Panel } from './ui'

type Filter = 'all' | 'shortlisted' | 'applied'

export function ApplicationsPanel({
  applications,
  onToggle,
}: {
  applications: Application[]
  onToggle: (job: Application, applied: boolean) => Promise<void>
}) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [pending, setPending] = useState<string | null>(null)

  const visible = useMemo(() => applications.filter((job) => {
    const matchesQuery = `${job.title} ${job.company} ${job.location}`.toLowerCase().includes(query.toLowerCase())
    const matchesFilter = filter === 'all' || (filter === 'applied' ? job.applied : (job.score ?? 0) >= 7)
    return matchesQuery && matchesFilter
  }), [applications, query, filter])

  const toggle = async (job: Application) => {
    setPending(job.job_id)
    try {
      await onToggle(job, !job.applied)
    } finally {
      setPending(null)
    }
  }

  return (
    <div className="page-enter">
      <PageHeading
        eyebrow="Opportunity history"
        title="Applications"
        description="Review every scored role and keep your actual application progress in one place."
      />
      <Panel>
        <div className="application-tools">
          <div className="segmented" role="group" aria-label="Application filter">
            {(['all', 'shortlisted', 'applied'] as Filter[]).map((item) => (
              <button key={item} className={filter === item ? 'active' : ''} onClick={() => setFilter(item)}>{item[0].toUpperCase() + item.slice(1)}</button>
            ))}
          </div>
          <div className="search-box"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search title, company, location…" aria-label="Search applications" /></div>
        </div>

        <div className="application-list">
          {visible.map((job) => (
            <article className="job-row" key={job.job_id}>
              <div className="score-orb" data-score={scoreTone(job.score)}>{job.score == null ? '—' : job.score.toFixed(1)}</div>
              <div className="job-row__main">
                <div className="job-row__title"><h2>{job.title}</h2>{job.emailed ? <span title="Included in an emailed digest"><Mail size={13} /> Sent</span> : null}</div>
                <p><strong>{job.company}</strong><span><MapPin size={13} />{job.location || 'Location not listed'}</span></p>
                {job.reason ? <div className="job-reason">{job.reason}</div> : null}
              </div>
              <div className="job-row__status">
                <time dateTime={job.first_seen}>{formatDate(job.first_seen)}</time>
                <button className={`application-check ${job.applied ? 'application-check--done' : ''}`} disabled={pending === job.job_id} onClick={() => toggle(job)}>
                  <span>{job.applied ? <Check size={14} /> : null}</span>{job.applied ? 'Applied' : 'Mark applied'}
                </button>
                <a href={job.url} target="_blank" rel="noreferrer">View role <ArrowUpRight size={14} /></a>
              </div>
            </article>
          ))}
          {!visible.length ? <div className="empty-state"><Briefcase size={28} /><h2>No roles here yet</h2><p>Try a different filter, or run the discovery pipeline to populate your tracker.</p></div> : null}
        </div>
      </Panel>
    </div>
  )
}

function scoreTone(score: number | null) {
  if (score == null) return 'neutral'
  if (score >= 8) return 'high'
  if (score >= 6) return 'medium'
  return 'low'
}

function formatDate(value: string) {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? 'Unknown date' : parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}
