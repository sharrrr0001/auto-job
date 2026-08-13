import { BriefcaseBusiness, FileText, Sparkles, UserRound } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { Profile } from '../types'
import { profileSignal } from '../utils'
import { Button, Field, PageHeading, Panel, SavedMark, TagEditor, TextInput } from './ui'

const seniorityOptions = ['student', 'intern', 'entry', 'junior', 'mid', 'senior', 'lead']

export function ProfileEditor({
  profile,
  onSave,
}: {
  profile: Profile
  onSave: (profile: Profile) => Promise<Profile>
}) {
  const [draft, setDraft] = useState(profile)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const dirty = JSON.stringify(draft) !== JSON.stringify(profile)

  useEffect(() => {
    const block = (event: BeforeUnloadEvent) => {
      if (dirty) event.preventDefault()
    }
    window.addEventListener('beforeunload', block)
    return () => window.removeEventListener('beforeunload', block)
  }, [dirty])

  const update = <K extends keyof Profile>(key: K, value: Profile[K]) => {
    setDraft((current) => ({ ...current, [key]: value }))
    setSaved(false)
  }

  const save = async () => {
    setSaving(true)
    try {
      const normalized = await onSave(draft)
      setDraft(normalized)
      setSaved(true)
      window.setTimeout(() => setSaved(false), 2400)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="page-enter">
      <PageHeading
        eyebrow="Candidate intelligence"
        title="Your profile"
        description="Give the matching agent an honest, high-signal picture of what you can do and what you want next."
        action={
          <div className="save-actions">
            <SavedMark visible={saved} />
            {dirty ? <span className="unsaved-dot">Unsaved changes</span> : null}
            <Button onClick={save} loading={saving} disabled={!dirty}>Save profile</Button>
          </div>
        }
      />

      <div className="profile-layout">
        <Panel className="profile-card">
          <div className="profile-avatar" aria-hidden="true">
            {(draft.name || '?').split(' ').map((part) => part[0]).slice(0, 2).join('').toUpperCase()}
          </div>
          <h2>{draft.name || 'Your name'}</h2>
          <p>{draft.current_title || 'Add your current role'}</p>
          <div className="profile-card__meta">
            <span><BriefcaseBusiness size={15} /> {draft.years_experience || 0} years</span>
            <span><Sparkles size={15} /> {draft.seniority || 'Not set'}</span>
          </div>
          <div className="completeness">
            <span>Profile signal</span>
            <strong>{profileSignal(draft)}%</strong>
            <div><i style={{ width: `${profileSignal(draft)}%` }} /></div>
          </div>
          <p className="profile-card__note">This data is included in screening and drafting prompts. Keep every claim interview-safe.</p>
        </Panel>

        <div className="editor-stack">
          <Panel>
            <div className="panel-title"><UserRound size={18} /><div><h2>Identity & context</h2><p>The essentials used to judge role and seniority fit.</p></div></div>
            <div className="form-grid">
              <Field label="Full name"><TextInput value={draft.name} onChange={(event) => update('name', event.target.value)} placeholder="Your full name" /></Field>
              <Field label="Current title"><TextInput value={draft.current_title} onChange={(event) => update('current_title', event.target.value)} placeholder="e.g. Computer Science Student" /></Field>
              <Field label="Years of experience"><TextInput type="number" min="0" max="60" step="0.5" value={draft.years_experience} onChange={(event) => update('years_experience', Number(event.target.value))} /></Field>
              <Field label="Seniority">
                <select className="input" value={draft.seniority} onChange={(event) => update('seniority', event.target.value)}>
                  {seniorityOptions.map((option) => <option key={option} value={option}>{option[0].toUpperCase() + option.slice(1)}</option>)}
                </select>
              </Field>
              <Field label="Education" className="form-grid__wide"><TextInput value={draft.education} onChange={(event) => update('education', event.target.value)} placeholder="Degree, school, and graduation year" /></Field>
              <Field label="Professional summary" hint="A concise 2–3 sentence snapshot." className="form-grid__wide">
                <textarea className="input textarea" value={draft.summary} onChange={(event) => update('summary', event.target.value)} placeholder="What do you build well, and what kind of problems energize you?" rows={4} />
              </Field>
            </div>
          </Panel>

          <Panel>
            <div className="panel-title"><Sparkles size={18} /><div><h2>Skills & direction</h2><p>Use specific, defensible terms rather than broad buzzwords.</p></div></div>
            <div className="form-stack">
              <TagEditor label="Core skills" value={draft.core_skills} onChange={(value) => update('core_skills', value)} placeholder="e.g. Python" />
              <TagEditor label="Interests" hint="Themes you want the agent to prioritize." value={draft.interests} onChange={(value) => update('interests', value)} placeholder="e.g. AI infrastructure" />
              <TagEditor label="Domains" value={draft.domains} onChange={(value) => update('domains', value)} placeholder="e.g. Cybersecurity" />
              <TagEditor label="Target roles" value={draft.target_titles} onChange={(value) => update('target_titles', value)} placeholder="e.g. AI Engineer Intern" />
            </div>
          </Panel>

          <Panel>
            <div className="panel-title"><FileText size={18} /><div><h2>Proof of work</h2><p>Lead with outcomes, scale, or what you personally owned.</p></div></div>
            <div className="project-list">
              {draft.notable_projects.map((project, index) => (
                <div className="project-row" key={`${index}-${project.slice(0, 12)}`}>
                  <span>{String(index + 1).padStart(2, '0')}</span>
                  <textarea className="input textarea" rows={3} value={project} onChange={(event) => {
                    const projects = [...draft.notable_projects]
                    projects[index] = event.target.value
                    update('notable_projects', projects)
                  }} />
                  <button type="button" onClick={() => update('notable_projects', draft.notable_projects.filter((_, itemIndex) => itemIndex !== index))}>Remove</button>
                </div>
              ))}
              <Button variant="secondary" onClick={() => update('notable_projects', [...draft.notable_projects, ''])}>Add project</Button>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  )
}
