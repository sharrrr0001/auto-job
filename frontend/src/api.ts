import type {
  BootstrapData,
  Company,
  Profile,
  RunOptions,
  RunState,
  SearchSettings,
  Stats,
  Application,
} from './types'

class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })

  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = Array.isArray(body.detail)
      ? body.detail.map((item: { msg?: string }) => item.msg).join(', ')
      : body.detail
    throw new ApiError(detail || `Request failed (${response.status})`, response.status)
  }
  return body as T
}

export const api = {
  bootstrap: () => request<BootstrapData>('/api/bootstrap'),
  saveProfile: (profile: Profile) =>
    request<{ profile: Profile; message: string }>('/api/profile', {
      method: 'PUT',
      body: JSON.stringify(profile),
    }),
  saveSettings: (settings: SearchSettings) =>
    request<{ settings: SearchSettings; message: string }>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    }),
  saveCompanies: (companies: Company[]) =>
    request<{ companies: Company[]; message: string }>('/api/companies', {
      method: 'PUT',
      body: JSON.stringify({ companies }),
    }),
  updateApplication: (jobId: string, applied: boolean) =>
    request<{ job: Application; stats: Stats }>(`/api/applications/${encodeURIComponent(jobId)}`, {
      method: 'PATCH',
      body: JSON.stringify({ applied }),
    }),
  startRun: (options: RunOptions) =>
    request<RunState>('/api/run', { method: 'POST', body: JSON.stringify(options) }),
  runStatus: () => request<RunState>('/api/run'),
}
