import { Check, LoaderCircle, Plus, X } from 'lucide-react'
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'
import { useState } from 'react'

export function Button({
  children,
  variant = 'primary',
  loading = false,
  className = '',
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  loading?: boolean
}) {
  return (
    <button
      className={`button button--${variant} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <LoaderCircle size={16} className="spin" aria-hidden="true" /> : null}
      {children}
    </button>
  )
}

export function Field({
  label,
  hint,
  children,
  className = '',
}: {
  label: string
  hint?: string
  children: ReactNode
  className?: string
}) {
  return (
    <label className={`field ${className}`}>
      <span className="field__label">{label}</span>
      {hint ? <span className="field__hint">{hint}</span> : null}
      {children}
    </label>
  )
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className="input" {...props} />
}

export function TagEditor({
  label,
  hint,
  value,
  onChange,
  placeholder = 'Type and press Enter',
}: {
  label: string
  hint?: string
  value: string[]
  onChange: (next: string[]) => void
  placeholder?: string
}) {
  const [draft, setDraft] = useState('')

  const add = () => {
    const next = draft.trim().replace(/,$/, '')
    if (!next) return
    if (!value.some((item) => item.toLocaleLowerCase() === next.toLocaleLowerCase())) {
      onChange([...value, next])
    }
    setDraft('')
  }

  return (
    <div className="field">
      <span className="field__label">{label}</span>
      {hint ? <span className="field__hint">{hint}</span> : null}
      <div className="tag-editor">
        <div className="tag-editor__items">
          {value.map((item) => (
            <span className="tag" key={item}>
              {item}
              <button
                type="button"
                aria-label={`Remove ${item}`}
                onClick={() => onChange(value.filter((entry) => entry !== item))}
              >
                <X size={13} />
              </button>
            </span>
          ))}
        </div>
        <div className="tag-editor__entry">
          <input
            value={draft}
            placeholder={value.length ? 'Add another…' : placeholder}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={add}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ',') {
                event.preventDefault()
                add()
              }
              if (event.key === 'Backspace' && !draft && value.length) {
                onChange(value.slice(0, -1))
              }
            }}
          />
          <button type="button" className="tag-editor__add" onMouseDown={(event) => event.preventDefault()} onClick={add}>
            <Plus size={16} /> Add
          </button>
        </div>
      </div>
    </div>
  )
}

export function Toggle({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean
  onChange: (checked: boolean) => void
  label: string
  description?: string
}) {
  return (
    <label className="toggle-row">
      <span>
        <strong>{label}</strong>
        {description ? <small>{description}</small> : null}
      </span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span className="toggle" aria-hidden="true"><span /></span>
    </label>
  )
}

export function SavedMark({ visible }: { visible: boolean }) {
  return (
    <span className={`saved-mark ${visible ? 'saved-mark--visible' : ''}`} aria-live="polite">
      <Check size={14} /> Saved
    </span>
  )
}

export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <header className="page-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action ? <div className="page-heading__action">{action}</div> : null}
    </header>
  )
}

export function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}>{children}</section>
}
