import { Building2, Plus, Search, Trash2, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { Company } from '../types'
import { Button, Field, PageHeading, Panel, SavedMark, TextInput } from './ui'

const emptyCompany: Company = { ats: 'greenhouse', slug: '', name: '' }

export function CompaniesPanel({ companies, onSave }: { companies: Company[]; onSave: (companies: Company[]) => Promise<Company[]> }) {
  const [draft, setDraft] = useState(companies)
  const [query, setQuery] = useState('')
  const [adding, setAdding] = useState(false)
  const [newCompany, setNewCompany] = useState<Company>(emptyCompany)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const dirty = JSON.stringify(draft) !== JSON.stringify(companies)

  const visible = useMemo(() => draft.filter((company) => `${company.name} ${company.slug} ${company.ats}`.toLowerCase().includes(query.toLowerCase())), [draft, query])

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

  const add = () => {
    if (!newCompany.name.trim() || !newCompany.slug.trim()) return
    setDraft((current) => [...current, { ...newCompany, name: newCompany.name.trim(), slug: newCompany.slug.trim() }])
    setNewCompany(emptyCompany)
    setAdding(false)
    setSaved(false)
  }

  return (
    <div className="page-enter">
      <PageHeading
        eyebrow="Source management"
        title="Company watchlist"
        description="Choose high-intent companies on supported public ATS boards. A focused list makes every run more useful."
        action={<div className="save-actions"><SavedMark visible={saved} />{dirty ? <span className="unsaved-dot">Unsaved changes</span> : null}<Button onClick={() => setAdding(true)} variant="secondary"><Plus size={16} /> Add company</Button><Button onClick={save} loading={saving} disabled={!dirty}>Save watchlist</Button></div>}
      />

      <Panel>
        <div className="table-tools">
          <div className="search-box"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search companies or ATS…" aria-label="Search companies" /></div>
          <span>{draft.length} companies</span>
        </div>
        <div className="company-table">
          <div className="company-table__head"><span>Company</span><span>Applicant tracking system</span><span>Board slug</span><span /></div>
          {visible.map((company) => {
            const index = draft.indexOf(company)
            return (
              <div className="company-row" key={`${company.ats}-${company.slug}-${index}`}>
                <div className="company-name"><span className="company-logo">{company.name.slice(0, 2).toUpperCase()}</span><input value={company.name} onChange={(event) => setDraft((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, name: event.target.value } : item))} /></div>
                <div><span className={`ats-badge ats-badge--${company.ats}`}>{company.ats}</span></div>
                <input className="table-input" value={company.slug} onChange={(event) => setDraft((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, slug: event.target.value } : item))} />
                <button className="icon-button icon-button--danger" type="button" aria-label={`Remove ${company.name}`} onClick={() => setDraft((current) => current.filter((_, itemIndex) => itemIndex !== index))}><Trash2 size={16} /></button>
              </div>
            )
          })}
          {!visible.length ? <div className="empty-row"><Building2 size={24} /><span>No companies match that search.</span></div> : null}
        </div>
      </Panel>

      {adding ? (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setAdding(false)}>
          <div className="modal" role="dialog" aria-modal="true" aria-labelledby="company-dialog" onMouseDown={(event) => event.stopPropagation()}>
            <button className="modal__close" type="button" onClick={() => setAdding(false)} aria-label="Close"><X size={18} /></button>
            <span className="eyebrow">New source</span>
            <h2 id="company-dialog">Add a company board</h2>
            <p>The slug is the final path segment of the public Greenhouse, Lever, or Ashby careers URL.</p>
            <div className="form-stack">
              <Field label="Company name"><TextInput autoFocus value={newCompany.name} onChange={(event) => setNewCompany({ ...newCompany, name: event.target.value })} placeholder="e.g. Acme" /></Field>
              <Field label="ATS provider"><select className="input" value={newCompany.ats} onChange={(event) => setNewCompany({ ...newCompany, ats: event.target.value as Company['ats'] })}><option value="greenhouse">Greenhouse</option><option value="lever">Lever</option><option value="ashby">Ashby</option></select></Field>
              <Field label="Board slug"><TextInput value={newCompany.slug} onChange={(event) => setNewCompany({ ...newCompany, slug: event.target.value })} placeholder="e.g. acme" /></Field>
            </div>
            <div className="modal__actions"><Button variant="ghost" onClick={() => setAdding(false)}>Cancel</Button><Button onClick={add} disabled={!newCompany.name.trim() || !newCompany.slug.trim()}>Add to watchlist</Button></div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
