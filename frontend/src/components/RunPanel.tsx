import { AlertTriangle, CheckCircle2, Circle, FlaskConical, LoaderCircle, Play, Terminal, X, XCircle } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { RunOptions, RunState } from '../types'
import { Button, Field, TextInput, Toggle } from './ui'

const defaults: RunOptions = {
  mock: false,
  keyword_scorer: false,
  no_draft: false,
  send_email: false,
  limit: null,
}

export function RunPanel({
  open,
  run,
  onClose,
  onStart,
}: {
  open: boolean
  run: RunState
  onClose: () => void
  onStart: (options: RunOptions) => Promise<void>
}) {
  const [options, setOptions] = useState(defaults)
  const [starting, setStarting] = useState(false)
  const logEnd = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open) logEnd.current?.scrollIntoView({ behavior: 'smooth' })
  }, [open, run.logs])

  if (!open) return null

  const start = async () => {
    setStarting(true)
    try {
      await onStart({
        ...options,
        keyword_scorer: options.mock ? true : options.keyword_scorer,
        no_draft: options.mock ? true : options.no_draft,
      })
    } finally {
      setStarting(false)
    }
  }

  const running = run.status === 'running'
  const hasOutput = running || run.status === 'succeeded' || run.status === 'failed'

  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside className="run-drawer" role="dialog" aria-modal="true" aria-labelledby="run-title" onMouseDown={(event) => event.stopPropagation()}>
        <header className="run-drawer__header">
          <div><span className="eyebrow">Pipeline control</span><h2 id="run-title">Run job discovery</h2></div>
          <button type="button" onClick={onClose} aria-label="Close"><X size={20} /></button>
        </header>

        {hasOutput ? (
          <div className="run-console-wrap">
            <div className={`run-summary run-summary--${run.status}`}>
              {running ? <LoaderCircle className="spin" /> : run.status === 'succeeded' ? <CheckCircle2 /> : <XCircle />}
              <div><strong>{running ? 'Pipeline running' : run.status === 'succeeded' ? 'Run completed' : 'Run failed'}</strong><span>{running ? 'Keep this panel open to follow the live output.' : `Exit code ${run.exit_code ?? 'unknown'}`}</span></div>
              <button type="button" onClick={() => setOptions(defaults)} disabled={running}>New run</button>
            </div>
            <div className="terminal">
              <div className="terminal__bar"><span><i /><i /><i /></span><strong><Terminal size={13} /> jobhunt pipeline</strong><small>{run.logs.length} lines</small></div>
              <pre aria-live="polite">{run.logs.map((line, index) => <code key={`${index}-${line}`}>{line}{'\n'}</code>)}</pre>
              <div ref={logEnd} />
            </div>
            {!running ? <Button onClick={start} variant="secondary"><Play size={15} /> Run again with current options</Button> : null}
          </div>
        ) : (
          <div className="run-config">
            <div className="run-mode-cards">
              <button type="button" className={!options.mock ? 'active' : ''} onClick={() => setOptions({ ...options, mock: false })}><span><Circle size={15} /><strong>Live boards</strong></span><small>Fetch your configured public company boards.</small></button>
              <button type="button" className={options.mock ? 'active' : ''} onClick={() => setOptions({ ...options, mock: true })}><span><FlaskConical size={15} /><strong>Safe test</strong></span><small>Use bundled fixtures with no API key or network.</small></button>
            </div>

            <div className="run-options">
              <Toggle checked={options.keyword_scorer || options.mock} onChange={(value) => setOptions({ ...options, keyword_scorer: value })} label="Use offline keyword scorer" description="Development-only scoring with no model cost." />
              <Toggle checked={options.no_draft || options.mock} onChange={(value) => setOptions({ ...options, no_draft: value })} label="Skip application drafts" description="Screen matches without generating tailored kits." />
              <Toggle checked={options.send_email} onChange={(value) => setOptions({ ...options, send_email: value })} label="Email the finished digest" description="Uses the SMTP credentials already stored in .env." />
              <Field label="Cost guard" hint="Optional maximum number of jobs sent to screening."><TextInput type="number" min="1" max="500" value={options.limit ?? ''} onChange={(event) => setOptions({ ...options, limit: event.target.value ? Number(event.target.value) : null })} placeholder="No limit" /></Field>
            </div>

            {options.send_email ? <div className="run-warning"><AlertTriangle size={16} /><span>A real email will be sent if the pipeline succeeds. Application submission is never automated.</span></div> : null}
            <div className="run-drawer__footer"><p>Configuration and profile changes are read when the run starts.</p><Button onClick={start} loading={starting}><Play size={16} /> Start pipeline</Button></div>
          </div>
        )}
      </aside>
    </div>
  )
}
