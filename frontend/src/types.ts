export type Section = 'overview' | 'profile' | 'preferences' | 'companies' | 'applications'

export interface Profile {
  name: string
  current_title: string
  years_experience: number
  seniority: string
  education: string
  summary: string
  core_skills: string[]
  interests: string[]
  domains: string[]
  target_titles: string[]
  notable_projects: string[]
  [key: string]: unknown
}

export interface SearchSettings {
  include_titles: string[]
  exclude_titles: string[]
  locations: string[]
  allow_remote: boolean
  max_age_days: number | null
  score_threshold: number
  max_per_digest: number
  screen_batch_size: number
}

export interface Company {
  ats: 'greenhouse' | 'lever' | 'ashby'
  slug: string
  name: string
}

export interface Application {
  job_id: string
  first_seen: string
  company: string
  title: string
  location: string
  url: string
  score: number | null
  reason: string | null
  emailed: boolean
  applied: boolean
  applied_on: string | null
}

export interface Stats {
  tracked: number
  emailed: number
  applied: number
}

export interface RunState {
  status: 'idle' | 'running' | 'succeeded' | 'failed'
  started_at: string | null
  finished_at: string | null
  exit_code: number | null
  logs: string[]
}

export interface BootstrapData {
  profile: Partial<Profile>
  settings: SearchSettings
  companies: Company[]
  applications: Application[]
  stats: Stats
  run: RunState
}

export interface RunOptions {
  mock: boolean
  keyword_scorer: boolean
  no_draft: boolean
  send_email: boolean
  limit: number | null
}
