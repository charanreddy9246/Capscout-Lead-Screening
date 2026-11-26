// Thin wrapper over fetch for the FastAPI backend. The session lives in an
// httpOnly cookie, so there is no token handling here.

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `Request failed (${status})`)
    this.status = status
    this.detail = detail
  }
}

const DEMO = import.meta.env.VITE_DEMO === 'true'

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (DEMO) {
    // Demo build: answers come from sample data in the browser (no server).
    const { demoApi, DemoHttpError } = await import('./demo/mockApi')
    try {
      return await demoApi<T>(path, init)
    } catch (e) {
      if (e instanceof DemoHttpError) throw new ApiError(e.status, e.detail)
      throw e
    }
  }
  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      ...init,
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', ...init.headers },
    })
  } catch {
    throw new ApiError(0, 'No connection. Check your network and try again.')
  }
  if (res.status === 204) return undefined as T
  const body = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, body?.detail ?? null)
  return body as T
}

export const post = <T>(path: string, data?: unknown) =>
  api<T>(path, { method: 'POST', body: data === undefined ? undefined : JSON.stringify(data) })

// --- types returned by the backend ------------------------------------------

export type Role = 'SM' | 'ADMIN' | 'SUPER_ADMIN'

export type Staff = {
  id: string
  email: string
  full_name: string
  role: Role
}

export type Progress = { filled: number; total: number; percent: number }

export type ConversionStatus = 'NOT_CONVERTED' | 'CONVERTING' | 'CONVERTED' | 'CONVERSION_FAILED'

export type CustomerCard = {
  id: string
  lead_ref: string
  business_name: string | null
  owner_name?: string | null
  loan_stage?: string | null
  promoter: string | null
  mobile: string | null
  location: string | null
  loan_required: string | null
  purpose: string | null
  opportunity_grade: string | null
  status: string | null
  next_action: string | null
  next_action_date: string | null
  conversion_status: ConversionStatus
  zoho_lead_id: string | null
  progress: Progress
  meeting_count: number
  last_meeting_at: string | null
}

export type SectionProgress = { key: string; label: string; filled: number; total: number }

export type CustomerDetail = CustomerCard & {
  owner: { id: string; full_name: string }
  converted_at: string | null
  lead_sync_status: 'NOT_QUEUED' | 'PENDING' | 'SYNCING' | 'SYNCED' | 'FAILED'
  lead_sync_error: string | null
  lead_sync_attempts: number
  sections: SectionProgress[]
  values: Record<string, string>
}

export type CustomerList = { total: number; items: CustomerCard[] }

export type DuplicateMatch = {
  id: string
  lead_ref: string
  conversion_status: ConversionStatus
  last_meeting_at: string | null
  business_name: string | null
  promoter: string | null
  mobile: string | null
  loan_required: string | null
  purpose: string | null
  likely_product: string | null
}

export type FieldType = 'system' | 'text' | 'long_text' | 'phone' | 'number' | 'date' | 'single_select'

export type FieldDef = {
  key: string
  label: string
  field_type: FieldType
  options: string[] | null
  unit: string | null
  section: string
  display_order: number
  counts_toward_progress: boolean
  system_source: 'application_ref' | 'meeting_date' | 'staff_name' | null
}

export type Section = { key: string; label: string; display_order: number }

export type FieldCatalog = { version: number; progress_total: number; sections: Section[]; fields: FieldDef[] }

export type GpsPoint = { latitude: number; longitude: number; accuracy_m: number; captured_at: string }

export type FieldChange = {
  field: string
  old: string | null
  new: string | null
  type: 'NEW' | 'UPDATED' | 'CLEARED'
}

export type SyncStatus = 'NOT_QUEUED' | 'PENDING' | 'SYNCING' | 'SYNCED' | 'FAILED'

export type Meeting = {
  id: string
  customer_id: string
  sequence_no: number
  staff: { id: string; full_name: string | null }
  started_at: string
  ended_at: string | null
  changes: FieldChange[]
  gps_status: 'PENDING' | 'CAPTURED' | 'UNAVAILABLE'
  gps_unavailable_reason: string | null
  place: string | null
  gps_start: GpsPoint | null
  gps_end: GpsPoint | null
  zoho_sync_status: SyncStatus
  zoho_meeting_id: string | null
  zoho_last_error: string | null
}

export type HomeSummary = {
  // the two home-screen tiles: prospects AND leads together, not counting Dropped
  follow_ups_today: number
  overdue: number
  not_converted: number
  converted: number
  sync_pending: number
  sync_failed: number
}

// --- the "Convert to Lead" form: Zoho's own Lead fields -----------------------------------

export type ZohoFieldKind =
  | 'text'
  | 'textarea'
  | 'select'
  | 'email'
  | 'phone'
  | 'url'
  | 'integer'
  | 'decimal'
  | 'boolean'
  | 'date'

export type ZohoFormField = {
  api_name: string
  label: string
  kind: ZohoFieldKind
  required: boolean
  options: string[] | null
  max_length: number | null
  custom: boolean
  value: string | number | boolean | null
  prefilled_from: string | null
}

export type ConvertForm = {
  customer: { id: string; lead_ref: string; name: string | null }
  fields: ZohoFormField[]
}

// --- dashboard and user management -------------------------------------------------------------

export type DashboardTotals = {
  meetings: number
  new_prospects: number
  leads_converted: number
  follow_ups_today: number
  overdue: number
  no_gps: number
  sync_failed: number
  open_customers: number
}

export type DashboardMember = {
  id: string
  full_name: string
  meetings: number
  new_prospects: number
  leads_converted: number
  overdue: number
  no_gps: number
  last_meeting_at: string | null
}

export type DashboardData = {
  scope: 'me' | 'team' | 'person'
  person: { id: string; full_name: string } | null
  period: { key: 'today' | 'week' | 'month'; days: number }
  totals: DashboardTotals
  pipeline: { label: string; count: number }[]
  lead_stages: { label: string; count: number }[]
  members?: DashboardMember[]
}

export type FollowUp = {
  id: string
  customer: {
    id: string
    business_name: string | null
    promoter: string | null
    mobile: string | null
    loan_stage: string | null
    converted: boolean
    owner_name: string | null
  }
  due_at: string
  purpose: string | null
  status: 'PENDING' | 'DONE'
  outcome: string | null
  completed_at: string | null
  when: 'overdue' | 'today' | 'upcoming' | 'done'
}
export type FollowUpList = { items: FollowUp[]; counts: { overdue: number; today: number; upcoming: number } }

export type MessageDraft = { text: string; mobile: string | null; next_action: string | null }
export type SentMessage = { id: string; channel: 'WHATSAPP' | 'SMS' | 'COPY'; body: string; sent_at: string; by: string | null }

// A Zoho deal, read-only: the operations team changes it in Zoho, never here.
export type Deal = {
  id: string
  name: string | null
  amount: number | null
  stage: string | null
  closing_date: string | null
  next_step: string | null
  owner: string | null
  modified_at: string | null
}
export type DealItem = {
  customer_id: string
  business_name: string | null
  promoter: string | null
  mobile: string | null
  sm_name: string | null
  deal: Deal
}
export type DealList = { items: DealItem[]; zoho: boolean }

export type UserRow = {
  id: string
  full_name: string
  email: string
  phone: string | null
  role: Role
  is_active: boolean
  manageable: boolean
}

export type Invite = { token: string; path: string; valid_hours: number; email?: { sent: boolean; to: string | null; error: string | null } }
