import { Gauge, MapPin, SlidersHorizontal } from 'lucide-react'
import { useState } from 'react'
import type { SearchSettings } from '../types'
import { Button, Field, PageHeading, Panel, SavedMark, TagEditor, TextInput, Toggle } from './ui'

export function PreferencesEditor({
  settings,
  onSave,
}: {
  settings: SearchSettings
  onSave: (settings: SearchSettings) => Promise<SearchSettings>
}) {
  const [draft, setDraft] = useState(settings)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const dirty = JSON.stringify(draft) !== JSON.stringify(settings)

  const update = <K extends keyof SearchSettings>(key: K, value: SearchSettings[K]) => {
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
        eyebrow="Matching logic"
        title="Search preferences"
        description="Shape the free prefilter first. Tighter inputs mean less noise and fewer model calls."
        action={<div className="save-actions"><SavedMark visible={saved} />{dirty ? <span className="unsaved-dot">Unsaved changes</span> : null}<Button onClick={save} loading={saving} disabled={!dirty}>Save preferences</Button></div>}
      />

      <div className="settings-grid">
        <Panel className="settings-grid__main">
          <div className="panel-title"><SlidersHorizontal size={18} /><div><h2>Role filters</h2><p>Add the job titles you want. Matching is case-insensitive and requires no regex.</p></div></div>
          <div className="form-stack">
            <TagEditor
              label="Roles to find"
              hint="Examples: Backend Engineer, AI Engineer, Software Engineer Intern. Leave empty only if you want every title."
              value={draft.role_filters}
              onChange={(value) => update('role_filters', value)}
              placeholder="e.g. Backend Engineer"
            />
            {!draft.role_filters.length ? <div className="inline-warning">No role filter is set, so every title can pass this gate.</div> : null}
            <TagEditor
              label="Advanced exclusions"
              hint="Optional regular expressions. Exclusions always win over a role match."
              value={draft.exclude_titles}
              onChange={(value) => update('exclude_titles', value)}
              placeholder="e.g. \\b(senior|staff)\\b"
            />
          </div>
        </Panel>

        <Panel className="settings-grid__side">
          <div className="panel-title"><Gauge size={18} /><div><h2>Quality bar</h2><p>Control how much work reaches your digest.</p></div></div>
          <div className="score-control">
            <div><span>Minimum score</span><strong>{draft.score_threshold.toFixed(1)}</strong></div>
            <input type="range" min="0" max="10" step="0.5" value={draft.score_threshold} onChange={(event) => update('score_threshold', Number(event.target.value))} />
            <div className="range-labels"><span>Broad</span><span>Selective</span></div>
          </div>
          <div className="form-grid form-grid--compact">
            <Field label="Digest limit" hint="Max drafted roles"><TextInput type="number" min="1" max="50" value={draft.max_per_digest} onChange={(event) => update('max_per_digest', Number(event.target.value))} /></Field>
            <Field label="Screen batch" hint="Jobs per model call"><TextInput type="number" min="1" max="50" value={draft.screen_batch_size} onChange={(event) => update('screen_batch_size', Number(event.target.value))} /></Field>
          </div>
        </Panel>

        <Panel className="settings-grid__main">
          <div className="panel-title"><MapPin size={18} /><div><h2>Location & freshness</h2><p>Set the geographic boundaries before AI screening begins.</p></div></div>
          <TagEditor label="Accepted locations" value={draft.locations} onChange={(value) => update('locations', value)} placeholder="e.g. Bengaluru" />
          <div className="preference-row">
            <Toggle checked={draft.allow_remote} onChange={(value) => update('allow_remote', value)} label="Include remote roles" description="Allows roles containing remote, anywhere, WFH, or distributed." />
            <Field label="Maximum posting age" hint="Days; newer roles are usually more actionable.">
              <div className="input-suffix"><TextInput type="number" min="1" max="365" value={draft.max_age_days ?? ''} onChange={(event) => update('max_age_days', event.target.value ? Number(event.target.value) : null)} /><span>days</span></div>
            </Field>
          </div>
        </Panel>

        <Panel className="filter-preview settings-grid__side">
          <span className="eyebrow">Current funnel</span>
          <h2>Every posting must pass all three gates.</h2>
          <ol>
            <li><span>01</span><div><strong>Role match</strong><small>{draft.role_filters.length || 'Any'} roles · {draft.exclude_titles.length} exclusions</small></div></li>
            <li><span>02</span><div><strong>Location fit</strong><small>{draft.locations.length || 'Any'} regions · remote {draft.allow_remote ? 'on' : 'off'}</small></div></li>
            <li><span>03</span><div><strong>Fresh enough</strong><small>{draft.max_age_days ? `Posted within ${draft.max_age_days} days` : 'No age limit'}</small></div></li>
          </ol>
        </Panel>
      </div>
    </div>
  )
}
