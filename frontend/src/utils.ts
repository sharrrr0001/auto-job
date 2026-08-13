import type { Profile } from './types'

export function profileSignal(profile: Profile) {
  const checks = [
    profile.name,
    profile.current_title,
    profile.education,
    profile.summary,
    profile.core_skills.length >= 3,
    profile.target_titles.length >= 1,
    profile.notable_projects.length >= 1,
    profile.domains.length >= 1,
    profile.interests.length >= 1,
  ]
  return Math.round((checks.filter(Boolean).length / checks.length) * 100)
}
