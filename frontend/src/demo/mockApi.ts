// DEMO MODE: a stand-in for the backend that runs entirely in the browser.
//
// It answers the same requests as the real API, with sample leads kept in this browser's
// localStorage, so the app can be shown (screens, navigation and the main rules) with NO server.
// Nothing here ever reaches Zoho or a database. Switched on only by VITE_DEMO=true (see .env.demo).
// Add ?reset=1 to the address to go back to the original sample data.

import type {
  Role,
  DashboardData,
  Invite,
  ConversionStatus,
  ConvertForm,
  CustomerCard,
  CustomerDetail,
  CustomerList,
  FieldCatalog,
  FieldChange,
  GpsPoint,
  HomeSummary,
  Meeting,
  Staff,
  ZohoFormField,
} from '../api'
import { addDays, isoDate } from '../format'
import catalogJson from './fields_v1.json'
import { demoPlace } from './places'
import { ZOHO_LEAD_FIELDS } from './zohoLeadFields'

export class DemoHttpError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `Request failed (${status})`)
    this.status = status
    this.detail = detail
  }
}

// --- catalogue ------------------------------------------------------------------------------

const FIELDS = catalogJson.fields
const BY_KEY = new Map(FIELDS.map((f) => [f.key, f]))
const PROGRESS_KEYS = new Set(FIELDS.filter((f) => f.counts_toward_progress).map((f) => f.key))

const CATALOG: FieldCatalog = {
  version: catalogJson.version,
  progress_total: PROGRESS_KEYS.size,
  sections: catalogJson.sections,
  fields: FIELDS.map((f) => ({
    key: f.key,
    label: f.label,
    field_type: f.field_type as FieldCatalog['fields'][number]['field_type'],
    options: f.options,
    unit: f.unit,
    section: f.section,
    display_order: f.display_order,
    counts_toward_progress: f.counts_toward_progress,
    system_source: f.system_source as FieldCatalog['fields'][number]['system_source'],
  })),
}

const STAFF: Staff = { id: 'demo-staff-ravi', email: 'ravi@example.com', full_name: 'Ravi Kumar', role: 'SM' }

// In the demo the username picks the role: "super..." is the Super Admin, "admin..." an Admin, anything else an SM.
const staffFor = (d: Db): Staff =>
  d.role === 'SUPER_ADMIN'
    ? { id: 'demo-super', email: 'super@example.com', full_name: 'Developer', role: 'SUPER_ADMIN' }
    : d.role === 'ADMIN'
      ? { id: 'demo-admin', email: 'asha@example.com', full_name: 'Asha Menon', role: 'ADMIN' }
      : STAFF

type DUser = { id: string; full_name: string; email: string; phone: string | null; role: Role; is_active: boolean }
const seedUsers = (): DUser[] => [
  { id: 'demo-staff-ravi', full_name: 'Ravi Kumar', email: 'ravi@example.com', phone: '9000000001', role: 'SM', is_active: true },
  { id: 'u-priya', full_name: 'Priya Sharma', email: 'priya@example.com', phone: '9000000002', role: 'SM', is_active: true },
  { id: 'u-karthik', full_name: 'Karthik N', email: 'karthik@example.com', phone: '9000000003', role: 'SM', is_active: true },
  { id: 'demo-admin', full_name: 'Asha Menon', email: 'asha@example.com', phone: '9000000010', role: 'ADMIN', is_active: true },
  { id: 'u-admin2', full_name: 'Vikram Rao', email: 'vikram@example.com', phone: '9000000011', role: 'ADMIN', is_active: true },
]
// The two other sales managers' numbers are fixed sample values; Ravi's are worked out from his sample customers.
const OTHER_SMS: Record<string, { meetings: number; new_prospects: number; leads_converted: number; overdue: number; no_gps: number; last_h: number | null }> = {
  'u-priya': { meetings: 14, new_prospects: 6, leads_converted: 3, overdue: 1, no_gps: 0, last_h: 5 },
  'u-karthik': { meetings: 9, new_prospects: 4, leads_converted: 1, overdue: 3, no_gps: 2, last_h: 52 },
}
const CONVERT_SECONDS = 4
const SYNC_SECONDS = 3
const PLACE_SECONDS = 2.5

// --- the demo "database" ------------------------------------------------------------------------

type DMeeting = {
  id: string
  seq: number
  started_at: string
  ended_at: string
  created_ms: number
  changes: FieldChange[]
  gps: GpsPoint | null
  reason: string | null
  place: string | null
  failed: boolean
}

type DCustomer = {
  owner?: Role // who owns it: an SM unless an Admin or Super Admin recorded it
  id: string
  ref_no: number
  values: Record<string, string>
  status: ConversionStatus
  zoho_lead_id: string | null
  convert_requested_ms: number | null
  converted_at: string | null
  created_ms: number
  meetings: DMeeting[]
}

type DFollowUp = { id: string; customer_id: string; due_at: string; purpose: string | null; status: 'PENDING' | 'DONE'; outcome: string | null; completed_at: string | null }

type DMessage = { id: string; customer_id: string; channel: string; body: string; sent_at: string; by: string }

type Db = { v: 1; messages?: DMessage[]; next_ref: number; signed_in: boolean; role?: Role; users?: DUser[]; customers: DCustomer[]; followUps?: DFollowUp[] }

const KEY = 'capscout-demo-db-v2' // bumped when the sample data changed, so old browsers get the new data
let db: Db | null = null

const uid = () =>
  typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0
        return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
      })

const hoursAgo = (h: number) => new Date(Date.now() - h * 3_600_000)

function normMobile(raw: string | undefined): string {
  const digits = (raw ?? '').replace(/\D/g, '')
  return digits.length > 10 ? digits.slice(-10) : digits
}

/** Apply typed values to a customer's current values. Returns what changed (the meeting's history). */
function applyValues(c: DCustomer, raw: Record<string, unknown>): FieldChange[] {
  const changes: FieldChange[] = []
  for (const [key, value] of Object.entries(raw)) {
    const spec = BY_KEY.get(key)
    if (!spec || spec.field_type === 'system' || key === 'location') continue // Location comes from GPS only
    let next = String(value ?? '').trim()
    if (spec.field_type === 'phone') next = normMobile(next)
    const old = c.values[key]
    if (!next) {
      if (old !== undefined) {
        delete c.values[key]
        changes.push({ field: key, old, new: null, type: 'CLEARED' })
      }
      continue
    }
    if (old === next) continue
    c.values[key] = next
    changes.push({ field: key, old: old ?? null, new: next, type: old === undefined ? 'NEW' : 'UPDATED' })
  }
  return changes
}

type MeetingInput = {
  id?: string
  started_at: string
  ended_at?: string
  gps_start?: GpsPoint | null
  gps_unavailable_reason?: string | null
  values?: Record<string, unknown>
}

function addMeeting(c: DCustomer, input: MeetingInput, opts: { createdMs?: number; failed?: boolean } = {}): DMeeting {
  const changes = applyValues(c, input.values ?? {})
  const gps = input.gps_start ?? null
  const place = gps ? demoPlace(gps.latitude, gps.longitude) : null
  // The lead's address is set ONCE, from the first meeting that has a GPS place, and then stays fixed.
  if (place && !c.values.location) {
    c.values.location = place.area
    changes.push({ field: 'location', old: null, new: place.area, type: 'NEW' })
  }
  const meeting: DMeeting = {
    id: input.id ?? uid(),
    seq: c.meetings.length + 1,
    started_at: input.started_at,
    ended_at: input.ended_at ?? input.started_at,
    created_ms: opts.createdMs ?? Date.now(),
    changes,
    gps,
    reason: gps ? null : (input.gps_unavailable_reason ?? 'No GPS'),
    place: place?.place ?? null,
    failed: opts.failed ?? false,
  }
  c.meetings.push(meeting)
  // A meeting that sets or clears the Next Action Date replaces the customer's pending follow-ups.
  if (db && 'next_action_date' in (input.values ?? {})) {
    const list = fus(db)
    for (const f of list.filter((x) => x.customer_id === c.id && x.status === 'PENDING')) Object.assign(f, { status: 'DONE', outcome: `Replaced in meeting #${meeting.seq}`, completed_at: new Date().toISOString() })
    const day = c.values.next_action_date
    if (day && isOpen(c))
      list.push({ id: uid(), customer_id: c.id, due_at: new Date(`${day}T${c.values.follow_up_time || '10:00'}:00`).toISOString(), purpose: c.values.next_action ?? null, status: 'PENDING', outcome: null, completed_at: null })
  }
  // "Proceed" sends the prospect to Leads (the phone asked the user to confirm first).
  if (c.values.sm_recommendation === 'Proceed' && c.status === 'NOT_CONVERTED') {
    c.status = 'CONVERTING'
    c.convert_requested_ms = Date.now()
  }
  return meeting
}

// ---- follow-ups: derived from the customers' Next Action Date the first time, then kept here ----
function fus(d: Db): DFollowUp[] {
  d.followUps ??= d.customers
    .filter((c) => c.values.next_action_date && isOpen(c))
    .map((c) => ({ id: uid(), customer_id: c.id, due_at: new Date(`${c.values.next_action_date}T10:00:00`).toISOString(), purpose: c.values.next_action ?? null, status: 'PENDING' as const, outcome: null, completed_at: null }))
  return d.followUps
}

const ownerId = (c: DCustomer) => (c.owner === 'SUPER_ADMIN' ? 'demo-super' : c.owner === 'ADMIN' ? 'demo-admin' : STAFF.id)
const ownerName = (c: DCustomer) => (c.owner === 'SUPER_ADMIN' ? 'Developer' : c.owner === 'ADMIN' ? 'Asha Menon' : 'Ravi Kumar')
const isOpen = (c: DCustomer) => c.values.next_action !== 'Dropped' && !['Reject', 'Cancelled'].includes(c.values.status ?? '')

function newCustomer(refNo?: number): DCustomer {
  const d = load()
  return {
    owner: d.role && d.role !== 'SM' ? d.role : undefined,
    id: uid(),
    ref_no: refNo ?? d.next_ref++,
    values: {},
    status: 'NOT_CONVERTED',
    zoho_lead_id: null,
    convert_requested_ms: null,
    converted_at: null,
    created_ms: Date.now(),
    meetings: [],
  }
}

// --- sample data ----------------------------------------------------------------------------------

function seed(): Db {
  const now = Date.now()
  const today = new Date()
  const customers: DCustomer[] = []
  const make = (
    ref: number,
    meetings: { at: Date; gps: [number, number, number] | null; reason?: string; values: Record<string, string>; failed?: boolean }[],
  ) => {
    const c: DCustomer = { ...newCustomerShell(ref), created_ms: meetings[0].at.getTime() }
    for (const m of meetings) {
      addMeeting(
        c,
        {
          started_at: m.at.toISOString(),
          ended_at: new Date(m.at.getTime() + 20 * 60_000).toISOString(),
          gps_start: m.gps
            ? { latitude: m.gps[0], longitude: m.gps[1], accuracy_m: m.gps[2], captured_at: m.at.toISOString() }
            : null,
          gps_unavailable_reason: m.reason ?? null,
          values: m.values,
        },
        { createdMs: m.at.getTime(), failed: m.failed },
      )
    }
    customers.push(c)
    return c
  }
  const date = (offset: number) => isoDate(addDays(today, offset))

  const charan = make(5, [
    {
      at: hoursAgo(72),
      gps: null,
      reason: 'Location permission denied',
      values: {
        source_type: 'Channel Partnership', source_name: 'Dhanvik Reddy', source_contact: '7894561231',
        customer_type: 'Company', business_name: 'Sri Charan Enterprises', promoter: 'Charan Reddy', mobile: '9875435211',
        poc_name: 'Charan Reddy', poc_mobile: '9875435211', poc_designation: 'Proprietor', poc_email: 'charan@example.com', sector: 'Services',
        constitution: 'Sole Proprietorship', industry: 'Automobiles', vintage_years: '12', loan_required: '5000000',
        purpose: 'Expansion', urgency: '<30 days', secured_unsecured: 'Secured',
        annual_turnover: '1200000', monthly_banking: '3000000', existing_debt: '1200000', monthly_emi: '100000',
        gst_available: 'Yes', itr_financials: 'Yes', bank_statements: 'Yes',
        property_available: 'Yes', 
        overdue: 'No', bounces: 'No', settlement_write_off: 'No',
        documents_readiness: 'Ready', business_quality: 'Strong', banking_quality: 'Strong', credit_risk: 'Manageable',
        opportunity_grade: 'A – Priority', sm_recommendation: 'Proceed',
        next_action_date: date(3),
      },
    },
    { at: hoursAgo(48), gps: [13.085, 80.2101, 14], values: { next_action: 'Sanction', loan_required: '6000000' } },
    { at: hoursAgo(20), gps: [13.0852, 80.2099, 11], values: { loan_required: '7000000' } },
  ])
  charan.status = 'CONVERTED'
  charan.zoho_lead_id = '1236291000001094004'
  charan.converted_at = hoursAgo(47).toISOString()

  make(8, [
    {
      at: hoursAgo(2),
      gps: [17.4948, 78.399, 22],
      values: {
        source_type: 'Field Activity', business_name: "Pragya's Sales and Retails", promoter: 'Pragya', mobile: '9000000011',
        industry: 'Retail', constitution: 'General Partnership', vintage_years: '4', loan_required: '1500000',
        purpose: 'Working Capital', urgency: 'Immediate', secured_unsecured: 'Unsecured',
        annual_turnover: '700000', monthly_banking: '900000', gst_available: 'Yes', itr_financials: 'Unknown',
        bank_statements: 'Yes', business_quality: 'Average', next_action: 'Document collection', next_action_date: date(0),
      },
    },
  ])

  make(10, [
    {
      at: hoursAgo(96),
      gps: [17.4967, 78.3556, 17],
      values: {
        source_type: 'Channel Partnership', source_name: 'Raghav', source_contact: '9811122233',
        business_name: "Vishwath's tech solutions", promoter: 'Vishwath', mobile: '9000000010',
        industry: 'IT services', constitution: 'Private Limited Company', vintage_years: '7', loan_required: '4000000',
        purpose: 'Capex', urgency: '30-60 days', secured_unsecured: 'Open to both',
        annual_turnover: '1700000', monthly_banking: '2800000', existing_debt: '2500000', monthly_emi: '250000',
        gst_available: 'Yes', itr_financials: 'Yes', bank_statements: 'No',
        documents_readiness: 'Partial', business_quality: 'Strong', banking_quality: 'Average', credit_risk: 'Manageable',
        opportunity_grade: 'B – Develop', sm_recommendation: 'Hold',
        next_action: 'Document collection', next_action_date: date(-2),
      },
    },
    {
      at: hoursAgo(24), gps: null, reason: 'GPS switched off', failed: true,
      values: { bank_statements: 'Yes', documents_readiness: 'Ready' },
    },
  ])

  make(11, [
    {
      at: hoursAgo(26),
      gps: [17.4399, 78.4983, 19],
      values: {
        source_type: 'External Referral', source_name: 'CA Ramesh Babu', source_contact: '9988776655',
        business_name: 'Sri Maruthi Automobiles', promoter: 'Maruthi Rao', mobile: '9000000012',
        industry: 'Auto dealership', constitution: 'Sole Proprietorship', vintage_years: '9', loan_required: '6000000',
        purpose: 'Expansion', urgency: '<30 days', secured_unsecured: 'Secured',
        property_available: 'Yes',  overdue: 'No', bounces: 'No',
        business_quality: 'Strong', credit_risk: 'None known', opportunity_grade: 'B – Develop',
        sm_recommendation: 'Hold', next_action: 'Identify bank', next_action_date: date(1),
      },
    },
  ])

  const annapurna = make(9, [
    {
      at: hoursAgo(140),
      gps: [12.9716, 77.5946, 25],
      values: {
        source_type: 'Partner', source_name: 'Prasad', source_contact: '9123456780',
        business_name: 'Annapurna Foods LLP', promoter: 'Lakshmi Devi', mobile: '9000000009',
        industry: 'Food processing', constitution: 'Limited Liability Partnership', vintage_years: '8', loan_required: '1500000',
        purpose: 'Working Capital', urgency: 'Flexible', secured_unsecured: 'Unsecured',
        annual_turnover: '800000', monthly_banking: '1100000', gst_available: 'Yes', itr_financials: 'Yes', bank_statements: 'Yes',
        documents_readiness: 'Partial', business_quality: 'Average', banking_quality: 'Average',
        opportunity_grade: 'B – Develop', sm_recommendation: 'Proceed',
        next_action: 'Document collection', next_action_date: date(-3),
      },
    },
    { at: hoursAgo(50), gps: [12.9719, 77.5949, 21], values: { documents_readiness: 'Ready', next_action: 'Login', next_action_date: date(1) } },
  ])
  annapurna.status = 'CONVERTED'
  annapurna.zoho_lead_id = '1236291000001101009'
  annapurna.converted_at = hoursAgo(49).toISOString()

  // The demo starts with every sample customer already a Lead (the Meetings tab is empty).
  customers.forEach((c, i) => {
    c.status = 'CONVERTED'
    c.zoho_lead_id ??= `12362910000011${String(c.ref_no).padStart(5, '0')}`
    c.converted_at ??= hoursAgo(10 + i).toISOString()
  })

  return { v: 1, next_ref: 12, signed_in: false, customers: customers.map((c) => ({ ...c, created_ms: Math.min(c.created_ms, now) })) }
}

function newCustomerShell(ref: number): DCustomer {
  return {
    id: uid(), ref_no: ref, values: {}, status: 'NOT_CONVERTED', zoho_lead_id: null,
    convert_requested_ms: null, converted_at: null, created_ms: Date.now(), meetings: [],
  }
}

function load(): Db {
  if (db) return db
  try {
    if (new URLSearchParams(location.search).has('reset')) localStorage.removeItem(KEY)
    const raw = localStorage.getItem(KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Db
      if (parsed.v === 1) return (db = parsed)
    }
  } catch {
    // unreadable storage: start from the sample data
  }
  db = seed()
  save()
  return db
}

function save() {
  try {
    localStorage.setItem(KEY, JSON.stringify(db))
  } catch {
    // private window or full storage: the demo still works until the page is closed
  }
}

// --- derived state (time-based: a conversion takes seconds, a sync takes seconds) ------------------

function refresh(c: DCustomer) {
  if (c.status === 'CONVERTING' && c.convert_requested_ms && Date.now() - c.convert_requested_ms >= CONVERT_SECONDS * 1000) {
    c.status = 'CONVERTED'
    const stages = (CATALOG.fields.find((f) => f.key === 'next_action')?.options ?? []) as string[]
    if (!stages.includes(c.values.next_action ?? '')) c.values.next_action = 'Document collection' // a new lead starts at the first stage
    c.zoho_lead_id = `12362910000011${String(c.ref_no).padStart(5, '0')}`
    c.converted_at = new Date().toISOString()
    save()
  }
}

const syncOf = (m: DMeeting): 'PENDING' | 'SYNCED' | 'FAILED' =>
  m.failed ? 'FAILED' : Date.now() - m.created_ms < SYNC_SECONDS * 1000 ? 'PENDING' : 'SYNCED'

const refOf = (c: DCustomer) => `MSME-${String(c.ref_no).padStart(4, '0')}`

// Direct customers are not asked for a source name or contact, so those two do not count for them.
const applicableKeys = (c: DCustomer) =>
  [...PROGRESS_KEYS].filter(
    (k) =>
      !(['source_name', 'source_contact'].includes(k) && c.values.source_type === 'Direct') &&
      !(['property_value', 'existing_mortgage'].includes(k) && c.values.property_available === 'No') &&
      !(['property_available', 'property_value', 'existing_mortgage'].includes(k) && c.values.secured_unsecured === 'Unsecured'),
  )

function progress(c: DCustomer) {
  const keys = applicableKeys(c)
  const filled = keys.filter((k) => k in c.values).length
  const total = keys.length
  return { filled, total, percent: Math.round((filled * 100) / total) }
}

function lastMeetingAt(c: DCustomer): string | null {
  return c.meetings.length ? c.meetings.map((m) => m.started_at).sort().at(-1)! : null
}

function card(c: DCustomer): CustomerCard {
  refresh(c)
  const v = c.values
  return {
    id: c.id,
    lead_ref: refOf(c),
    owner_name: ownerName(c),
    business_name: v.business_name ?? null,
    promoter: v.promoter ?? null,
    mobile: v.mobile ?? null,
    location: v.location ?? null,
    loan_required: v.loan_required ?? null,
    purpose: v.purpose ?? null,
    opportunity_grade: v.opportunity_grade ?? null,
    status: v.status ?? null,
    loan_stage: c.status === 'CONVERTED' ? (v.next_action ?? null) : null,
    next_action: v.next_action ?? null,
    next_action_date: v.next_action_date ?? null,
    conversion_status: c.status,
    zoho_lead_id: c.zoho_lead_id,
    progress: progress(c),
    meeting_count: c.meetings.length,
    last_meeting_at: lastMeetingAt(c),
  }
}

function detail(c: DCustomer): CustomerDetail {
  const base = card(c)
  return {
    ...base,
    owner: { id: ownerId(c), full_name: ownerName(c) },
    converted_at: c.converted_at,
    lead_sync_status: c.status === 'CONVERTING' ? 'PENDING' : c.status === 'CONVERTED' ? 'SYNCED' : 'NOT_QUEUED',
    lead_sync_error: null,
    lead_sync_attempts: 0,
    sections: CATALOG.sections.map((s) => {
      const keys = applicableKeys(c).filter((k) => BY_KEY.get(k)?.section === s.key)
      return { key: s.key, label: s.label, filled: keys.filter((k) => k in c.values).length, total: keys.length }
    }),
    values: { ...c.values },
  }
}

function meetingOut(c: DCustomer, m: DMeeting): Meeting {
  const sync = syncOf(m)
  const placeReady = Date.now() - m.created_ms >= PLACE_SECONDS * 1000
  return {
    id: m.id,
    customer_id: c.id,
    sequence_no: m.seq,
    staff: { id: STAFF.id, full_name: STAFF.full_name },
    started_at: m.started_at,
    ended_at: m.ended_at,
    changes: m.changes,
    gps_status: m.gps ? 'CAPTURED' : 'UNAVAILABLE',
    gps_unavailable_reason: m.gps ? null : m.reason,
    place: m.gps && placeReady ? m.place : null,
    gps_start: m.gps,
    gps_end: null,
    zoho_sync_status: sync,
    zoho_meeting_id: sync === 'SYNCED' ? `12362910000009${String(c.ref_no).padStart(2, '0')}${m.seq}` : null,
    zoho_last_error: sync === 'FAILED' ? 'OAUTH_SCOPE_MISMATCH invalid oauth scope to access this URL' : null,
  }
}

// --- the Convert to Lead form ----------------------------------------------------------------------

function convertForm(c: DCustomer): ConvertForm {
  const v = c.values
  const standard: Record<string, [string | undefined, string]> = {
    Last_Name: [v.promoter ?? v.business_name, 'Promoter'],
    Company: [v.business_name, 'Business Name'],
    Mobile: [v.mobile, 'Mobile'],
    City: [v.location, 'Location'],
  }
  const loanType = [v.likely_product, v.purpose].find((x) => x && ['LAP', 'Business Loan', 'Working Capital'].includes(x))
  const description = [
    'CapScout details (updated automatically)',
    refOf(c),
    '',
    ...FIELDS.filter((f) => f.field_type !== 'system' && v[f.key] !== undefined).map((f) => `${f.label}: ${v[f.key]}`),
  ].join('\n')

  const fields: ZohoFormField[] = ZOHO_LEAD_FIELDS.map((f) => {
    let value: string | null = null
    let from: string | null = null
    if (standard[f.api_name]?.[0]) [value, from] = [standard[f.api_name][0]!, standard[f.api_name][1]]
    else if (f.api_name === 'Loan_Type' && loanType) [value, from] = [loanType, 'Likely Product']
    else if (f.api_name === 'Description') [value, from] = [description, 'everything collected in the app']
    return {
      api_name: f.api_name,
      label: f.label,
      kind: f.kind,
      required: !!f.required,
      options: f.options ?? null,
      max_length: ['text', 'textarea', 'phone', 'email', 'url'].includes(f.kind) ? 255 : null,
      custom: !!f.custom,
      value,
      prefilled_from: from,
    }
  })
  return {
    customer: { id: c.id, lead_ref: refOf(c), name: v.business_name ?? v.promoter ?? null },
    fields,
  }
}

function validateLead(values: Record<string, unknown>): Record<string, string> {
  const errors: Record<string, string> = {}
  for (const f of ZOHO_LEAD_FIELDS) {
    const raw = values[f.api_name]
    const text = raw === undefined || raw === null ? '' : String(raw).trim()
    if (!text) {
      if (f.required) errors[f.api_name] = 'required'
      continue
    }
    if (f.kind === 'email' && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(text)) errors[f.api_name] = 'enter a valid email address'
    else if ((f.kind === 'integer' || f.kind === 'decimal') && Number.isNaN(Number(text))) errors[f.api_name] = 'enter a valid number'
    else if (f.kind === 'select' && !f.options?.some((o) => o.toLowerCase() === text.toLowerCase()))
      errors[f.api_name] = 'choose one of the options'
  }
  return errors
}

// --- routing ------------------------------------------------------------------------------------------

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))
const find = (id: string): DCustomer => {
  const c = load().customers.find((x) => x.id === id)
  if (!c) throw new DemoHttpError(404, 'Not found')
  return c
}
const matchPath = (path: string, re: RegExp) => path.match(re)

export async function demoApi<T>(path: string, init: RequestInit = {}): Promise<T> {
  await sleep(90 + Math.random() * 140) // feels like a real network call
  const method = (init.method ?? 'GET').toUpperCase()
  const url = new URL(path, 'http://demo.local')
  const p = url.pathname
  const q = url.searchParams
  const body = init.body ? (JSON.parse(String(init.body)) as Record<string, any>) : {} // eslint-disable-line @typescript-eslint/no-explicit-any
  const d = load()
  const out = (value: unknown) => value as T

  // ---- sign in (any employee code and password work in the demo) ----
  if (p === '/auth/login' && method === 'POST') {
    if (!String(body.username ?? '').trim() || String(body.phone ?? '').length !== 10 || !String(body.password ?? '')) throw new DemoHttpError(422, 'Enter your username, 10-digit phone number and password')
    const name = String(body.username).trim().toLowerCase()
    d.role = name.startsWith('super') ? 'SUPER_ADMIN' : name.startsWith('admin') ? 'ADMIN' : 'SM'
    d.signed_in = true
    save()
    return out({ ...staffFor(d), email: String(body.username).trim().toLowerCase() })
  }
  if (p === '/auth/set-password' && method === 'POST') {
    if (!String(body.token ?? '').startsWith('demo-token')) throw new DemoHttpError(400, 'This link is not valid any more. Ask your admin for a new one.')
    if (String(body.password ?? '').length < 8) throw new DemoHttpError(422, 'The password must be at least 8 characters.')
    return out({ ok: true, email: 'new.person@example.com' })
  }
  if (p === '/auth/logout') {
    d.signed_in = false
    save()
    return out(undefined)
  }
  if (!d.signed_in) throw new DemoHttpError(401, 'Not signed in')

  if (p === '/me') return out(staffFor(d))
  const role: Role = d.role ?? 'SM'
  // Role decides what you may SEE; OWNERSHIP decides what you may CHANGE (the real server enforces both).
  const ownerOf = (c: DCustomer): Role => c.owner ?? 'SM'
  const isMine = (c: DCustomer) => ownerOf(c) === role
  const inScope = (c: DCustomer) => (role === 'SM' ? isMine(c) : q.get('mine') === 'true' ? isMine(c) : true)
  const mustOwn = (c: DCustomer) => {
    if (!isMine(c)) throw new DemoHttpError(403, 'Only the person who owns this customer can change it.')
  }
  d.users ??= seedUsers()
  const users = d.users
  const canManage = (target: Role) => target !== 'SUPER_ADMIN' && (role === 'SUPER_ADMIN' || (role === 'ADMIN' && target === 'SM'))
  const userOut = (u: DUser) => ({ ...u, manageable: canManage(u.role) && staffFor(d).id !== u.id })
  const invite = (to?: string | null): Invite => ({ token: 'demo-token-' + uid().slice(0, 8), path: '/set-password?token=demo-token', valid_hours: 72, email: { sent: false, to: to ?? null, error: 'This is the demo, so no email is sent.' } })

  // ---- User Management ----
  if (p === '/users' && method === 'GET') {
    if (role === 'SM') throw new DemoHttpError(403, 'You do not have access to this.')
    return out({ items: users.filter((u) => u.role === 'SM' || (role === 'SUPER_ADMIN' && u.role === 'ADMIN')).map(userOut) })
  }
  if (p === '/users' && method === 'POST') {
    if (role === 'SM') throw new DemoHttpError(403, 'You do not have access to this.')
    const target = (body.role ?? 'SM') as Role
    if (!canManage(target)) throw new DemoHttpError(403, target === 'ADMIN' ? 'Only the Super Admin can create an Admin.' : 'You are not allowed to create this account.')
    const phone = String(body.phone ?? '').replace(/\D/g, '').slice(-10)
    if (phone.length !== 10) throw new DemoHttpError(422, 'The mobile must be exactly 10 digits.')
    const email = String(body.email ?? '').trim().toLowerCase()
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) throw new DemoHttpError(422, 'Enter a valid email address.')
    if (users.some((u) => u.phone === phone || u.email.toLowerCase() === email)) throw new DemoHttpError(409, 'That email or mobile is already used.')
    const u: DUser = { id: uid(), full_name: String(body.full_name).trim(), email, phone, role: target, is_active: true }
    users.push(u)
    save()
    return out({ ...userOut(u), invite: invite(u.email) })
  }
  let hit2 = matchPath(p, /^\/users\/([^/]+)(\/invite)?$/)
  if (hit2) {
    const u = users.find((x) => x.id === hit2![1])
    if (!u) throw new DemoHttpError(404, 'Not found')
    if (!canManage(u.role) || role === 'SM') throw new DemoHttpError(403, u.role === 'ADMIN' ? 'Only the Super Admin can change an Admin.' : 'You are not allowed to do this.')
    if (hit2[2]) return out(invite(users.find((x) => x.id === hit2[1])?.email))
    if (staffFor(d).id === u.id && (body.role !== undefined || body.is_active === false)) throw new DemoHttpError(403, 'You cannot change your own role or deactivate yourself.')
    if (body.role !== undefined && body.role !== u.role) {
      if (!canManage(body.role as Role)) throw new DemoHttpError(403, 'Only the Super Admin can promote someone to Admin.')
      u.role = body.role as Role
    }
    if (body.is_active !== undefined) u.is_active = !!body.is_active
    if (body.full_name) u.full_name = String(body.full_name)
    save()
    return out(userOut(u))
  }

  // ---- Dashboard: one screen, the server decides whose numbers ----
  if (p === '/dashboard') {
    const key = (['today', 'week', 'month'].includes(q.get('period') ?? '') ? q.get('period') : 'week') as 'today' | 'week' | 'month'
    const days = { today: 1, week: 7, month: 30 }[key]
    const todayStr = q.get('today') ?? isoDate(new Date())
    const since = Date.now() - days * 86_400_000
    const asked = role !== 'SM' ? q.get('staff_id') : null // an SM always gets their own
    const askedMe = asked === staffFor(d).id && role !== 'SM' // an Admin asking for themselves
    const askedFor = askedMe ? null : asked
    const ravi = (cs: DCustomer[] = d.customers): DashboardData['totals'] => {
      const live = cs.filter(isOpen)
      const meetings = cs.flatMap((c) => c.meetings).filter((m) => new Date(m.started_at).getTime() >= since)
      return {
        meetings: meetings.length,
        new_prospects: cs.filter((c) => c.created_ms >= since).length,
        leads_converted: cs.filter((c) => c.converted_at && new Date(c.converted_at).getTime() >= since).length,
        follow_ups_today: live.filter((c) => c.values.next_action_date === todayStr).length,
        overdue: live.filter((c) => c.values.next_action_date && c.values.next_action_date < todayStr).length,
        no_gps: meetings.filter((m) => !m.gps).length,
        sync_failed: cs.flatMap((c) => c.meetings).filter((m) => syncOf(m) === 'FAILED').length,
        open_customers: live.length,
      }
    }
    const pipeline = (() => {
      const counts = new Map<string, number>()
      for (const c of d.customers.filter((c) => isOpen(c) && c.status !== 'CONVERTED')) counts.set(c.values.status ?? 'Not set', (counts.get(c.values.status ?? 'Not set') ?? 0) + 1)
      return [...counts].map(([label, count]) => ({ label, count })).sort((a, b) => b.count - a.count)
    })()
    const scale = days === 1 ? 0.2 : days === 7 ? 1 : 3.2
    const other = (id: string) => {
      const o = OTHER_SMS[id]
      const n = (v: number) => Math.round(v * scale)
      return { meetings: n(o.meetings), new_prospects: n(o.new_prospects), leads_converted: n(o.leads_converted), overdue: o.overdue, no_gps: n(o.no_gps) }
    }
    const members = users
      .filter((u) => u.role === 'SM' && u.is_active)
      .map((u) => {
        if (u.id === STAFF.id) {
          const t = ravi()
          const last = d.customers.flatMap((c) => c.meetings).map((m) => m.started_at).sort().at(-1) ?? null
          return { id: u.id, full_name: u.full_name, meetings: t.meetings, new_prospects: t.new_prospects, leads_converted: t.leads_converted, overdue: t.overdue, no_gps: t.no_gps, last_meeting_at: last }
        }
        const o = other(u.id)
        return { id: u.id, full_name: u.full_name, ...o, last_meeting_at: OTHER_SMS[u.id] ? new Date(Date.now() - (OTHER_SMS[u.id].last_h ?? 0) * 3_600_000).toISOString() : null }
      })
    const leadStages = (() => {
      const names = (CATALOG.fields.find((f) => f.key === 'next_action')?.options ?? []) as string[]
      const leads = d.customers.filter((c) => c.status === 'CONVERTED')
      return [...names.map((label) => ({ label, count: leads.filter((c) => c.values.next_action === label).length })), { label: 'Not set', count: leads.filter((c) => !names.includes(c.values.next_action ?? '')).length }]
    })()
    const base = { period: { key, from: '', to: '', days }, lead_stages: leadStages }
    if (askedMe) {
      const me = staffFor(d)
      return out({ ...base, scope: 'person', person: { id: me.id, full_name: me.full_name }, totals: ravi(d.customers.filter(isMine)), pipeline: [] } satisfies DashboardData)
    }
    if (role === 'SM' || askedFor === STAFF.id) {
      return out({ ...base, scope: role === 'SM' ? 'me' : 'person', person: { id: STAFF.id, full_name: STAFF.full_name }, totals: ravi(), pipeline } satisfies DashboardData)
    }
    if (askedFor) {
      const u = users.find((x) => x.id === askedFor && x.role === 'SM')
      if (!u) throw new DemoHttpError(404, 'Not found')
      const o = other(u.id)
      const totals = { ...o, follow_ups_today: 1, sync_failed: 0, open_customers: 7 + o.new_prospects }
      return out({ ...base, scope: 'person', person: { id: u.id, full_name: u.full_name }, totals, pipeline: [{ label: 'Qualified', count: 3 }, { label: 'Documents Pending', count: 2 }] } satisfies DashboardData)
    }
    const sum = (f: (m: (typeof members)[number]) => number) => members.reduce((a, m) => a + f(m), 0)
    const t = ravi()
    return out({
      ...base,
      scope: 'team',
      person: null,
      totals: { ...t, meetings: sum((m) => m.meetings), new_prospects: sum((m) => m.new_prospects), leads_converted: sum((m) => m.leads_converted), overdue: sum((m) => m.overdue), no_gps: sum((m) => m.no_gps), open_customers: t.open_customers + 14 },
      pipeline,
      members,
    } satisfies DashboardData)
  }
  // ---- Deals: read-only (in real life straight from Zoho, changed only by the operations team) ----
  if (p === '/deals' && method === 'GET') {
    const sample: Record<string, { name: string; amount: number; stage: string; closing: string; next: string }> = {
      'Sri Charan Enterprises': { name: 'Sri Charan Enterprises loan', amount: 6000000, stage: 'Negotiation/Review', closing: isoDate(addDays(new Date(), 14)), next: 'Bank credit committee on Friday' },
      'Annapurna Foods LLP': { name: 'Annapurna Foods working capital', amount: 2500000, stage: 'Proposal/Price Quote', closing: isoDate(addDays(new Date(), 30)), next: 'Share revised quote' },
    }
    d.customers.forEach(refresh)
    let rows = d.customers.filter((c) => c.status === 'CONVERTED' && sample[c.values.business_name ?? ''] && inScope(c))
    if (q.get('customer_id')) rows = rows.filter((c) => c.id === q.get('customer_id'))
    return out({
      zoho: true,
      items: rows.map((c) => {
        const s = sample[c.values.business_name ?? '']
        return { customer_id: c.id, business_name: c.values.business_name ?? null, promoter: c.values.promoter ?? null, mobile: c.values.mobile ?? null, sm_name: ownerName(c), deal: { id: 'demo-deal-' + c.id.slice(0, 4), name: s.name, amount: s.amount, stage: s.stage, closing_date: s.closing, next_step: s.next, owner: 'Operations', modified_at: new Date().toISOString() } }
      }),
    })
  }

  // ---- Messages to a customer: a draft from the Next Action, then a log of what was sent ----
  const msgHit = matchPath(p, /^\/customers\/([^/]+)\/messages(\/draft)?$/)
  if (msgHit) {
    const c = find(msgHit[1])
    d.messages ??= []
    if (msgHit[2] && method === 'GET') {
      mustOwn(c)
      const starters: Record<string, string> = {
        'Document collection': 'as discussed, please share the pending documents (for example bank statements and KYC) so we can move your application forward.',
        'Identify bank': 'we are matching your requirement with suitable lenders and will update you soon.',
        Disbursement: 'thank you for choosing CapScout. We are glad we could help with your loan.',
        New: 'thank you for meeting with us. I will be in touch shortly about your loan requirement.',
        Qualified: 'thank you for your time. Based on our discussion, we will now shortlist suitable loan options for you.',
        'Documents Pending': 'as discussed, please share the pending documents (for example bank statements and KYC) so we can move your application forward.',
        'Lender Matching': 'we are matching your requirement with suitable lenders and will update you soon.',
        Login: 'your application is being submitted to the lender. We will keep you posted on the progress.',
        Sanction: 'your application is under review for sanction. We will update you as soon as we have news.',
        Disbursed: 'thank you for choosing CapScout. We are glad we could help with your loan.',
        Dropped: 'thank you for your time. If your requirement changes, please contact me anytime.',
      }
      const first = (c.values.promoter ?? c.values.business_name ?? 'there').split(' ')[0]
      const nxt = fus(d).filter((f) => f.customer_id === c.id && f.status === 'PENDING').sort((a, b) => a.due_at.localeCompare(b.due_at))[0]
      const visit = nxt ? ` Our next visit is on ${new Date(nxt.due_at).toLocaleString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}.` : ''
      const text = `Hi ${first}, ${starters[c.values.next_action ?? ''] ?? 'this is Ravi Kumar from CapScout, following up on our meeting.'}${visit} Regards, Ravi Kumar, CapScout`
      return out({ text, mobile: c.values.mobile ?? null, next_action: c.values.next_action ?? null })
    }
    if (!msgHit[2] && method === 'GET') return out({ items: d.messages.filter((m) => m.customer_id === c.id).sort((a, b) => b.sent_at.localeCompare(a.sent_at)).map(({ customer_id: _c, ...m }) => m) })
    if (!msgHit[2] && method === 'POST') {
      mustOwn(c)
      const m: DMessage = { id: uid(), customer_id: c.id, channel: String(body.channel), body: String(body.body ?? '').trim(), sent_at: new Date().toISOString(), by: 'Ravi Kumar' }
      if (!m.body || !['WHATSAPP', 'SMS', 'COPY'].includes(m.channel)) throw new DemoHttpError(422, 'Write a message first.')
      d.messages.push(m)
      save()
      const { customer_id: _c, ...rest } = m
      return out(rest)
    }
  }

  // ---- Follow-ups ----
  if (p === '/follow-ups' || p.startsWith('/follow-ups/')) {
    const list = fus(d)
    const todayStr = isoDate(new Date())
    const whenOf = (f: DFollowUp): 'overdue' | 'today' | 'upcoming' | 'done' => {
      if (f.status === 'DONE') return 'done'
      const day = isoDate(new Date(f.due_at))
      return day < todayStr ? 'overdue' : day === todayStr ? 'today' : 'upcoming'
    }
    const fuOut = (f: DFollowUp) => {
      const c = find(f.customer_id)
      refresh(c)
      return {
        id: f.id,
        customer: { id: c.id, business_name: c.values.business_name ?? null, promoter: c.values.promoter ?? null, mobile: c.values.mobile ?? null, loan_stage: c.status === 'CONVERTED' ? (c.values.next_action ?? null) : null, converted: c.status === 'CONVERTED', owner_name: ownerName(c) },
        due_at: f.due_at, purpose: f.purpose, status: f.status, outcome: f.outcome, completed_at: f.completed_at, when: whenOf(f),
      }
    }
    const mirror = (customerId: string) => {
      const c = find(customerId)
      const next = list.filter((f) => f.customer_id === customerId && f.status === 'PENDING').sort((a, b) => a.due_at.localeCompare(b.due_at))[0]
      if (next) {
        c.values.next_action_date = isoDate(new Date(next.due_at))
        if (next.purpose) c.values.next_action = next.purpose
      } else delete c.values.next_action_date
    }
    if (p === '/follow-ups' && method === 'GET') {
      const wantDone = q.get('status') === 'done'
      const visible = (f: DFollowUp) => inScope(find(f.customer_id))
      let rows = list.filter((f) => visible(f) && (f.status === 'DONE') === wantDone)
      if (q.get('customer_id')) rows = rows.filter((f) => f.customer_id === q.get('customer_id'))
      rows = [...rows].sort((a, b) => (wantDone ? (b.completed_at ?? '').localeCompare(a.completed_at ?? '') : a.due_at.localeCompare(b.due_at)))
      const counts = { overdue: 0, today: 0, upcoming: 0 }
      for (const f of list.filter((x) => visible(x) && x.status === 'PENDING')) counts[whenOf(f) as 'overdue' | 'today' | 'upcoming']++
      return out({ items: rows.map(fuOut), counts })
    }
    if (p === '/follow-ups' && method === 'POST') {
      mustOwn(find(String(body.customer_id)))
      const f: DFollowUp = { id: uid(), customer_id: String(body.customer_id), due_at: String(body.due_at), purpose: String(body.purpose ?? '').trim() || null, status: 'PENDING', outcome: null, completed_at: null }
      list.push(f)
      mirror(f.customer_id)
      save()
      return out(fuOut(f))
    }
    const one = matchPath(p, /^\/follow-ups\/([^/]+)(\/complete)?$/)
    if (one) {
      const f = list.find((x) => x.id === one[1])
      if (!f) throw new DemoHttpError(404, 'Not found')
      mustOwn(find(f.customer_id))
      if (f.status !== 'PENDING') throw new DemoHttpError(409, 'This follow-up is already done.')
      if (one[2] && method === 'POST') {
        Object.assign(f, { status: 'DONE', outcome: String(body.outcome ?? '').trim() || null, completed_at: new Date().toISOString() })
        const n = body.next as { due_at: string; purpose?: string } | undefined
        if (n) list.push({ id: uid(), customer_id: f.customer_id, due_at: n.due_at, purpose: n.purpose || f.purpose, status: 'PENDING', outcome: null, completed_at: null })
        mirror(f.customer_id)
        save()
        return out(fuOut(f))
      }
      if (method === 'PATCH') {
        if (body.due_at) f.due_at = String(body.due_at)
        if (body.purpose !== undefined) f.purpose = String(body.purpose).trim() || null
        mirror(f.customer_id)
        save()
        return out(fuOut(f))
      }
    }
  }
  if (p === '/fields') return out(CATALOG)

  if (p === '/geo/reverse') {
    const near = demoPlace(Number(q.get('lat')), Number(q.get('lng')))
    return out({ place: near.place, area: near.area })
  }

  if (p === '/customers/-/summary') {
    d.customers.forEach(refresh)
    const own = d.customers.filter(inScope)
    const meetings = own.flatMap((c) => c.meetings.map(syncOf))
    const today = q.get('today') ?? isoDate(new Date())
    const live = own.filter(isOpen)
    const due = (c: DCustomer) => c.values.next_action_date
    const summary: HomeSummary = {
      follow_ups_today: live.filter((c) => due(c) === today).length,
      overdue: live.filter((c) => due(c) && due(c)! < today).length,
      not_converted: own.filter((c) => c.status !== 'CONVERTED').length,
      converted: own.filter((c) => c.status === 'CONVERTED').length,
      sync_pending: meetings.filter((s) => s === 'PENDING').length,
      sync_failed: meetings.filter((s) => s === 'FAILED').length,
    }
    return out(summary)
  }

  if (p === '/customers' && method === 'GET') {
    const sid = q.get('staff_id')
    if (sid && sid !== STAFF.id) return out({ total: 0, items: [] } satisfies CustomerList) // the other sample SMs have no customers here
    const converted = q.get('tab') === 'converted'
    const view = q.get('view') // a home-screen tile: prospects and leads together
    const today = q.get('today') ?? isoDate(new Date())
    const needle = (q.get('q') ?? '').trim().toLowerCase()
    d.customers.forEach(refresh)
    const rows = d.customers
      .filter(inScope)
      .filter((c) =>
        view
          ? isOpen(c) &&
            (view === 'followups' ? c.values.next_action_date === today : !!c.values.next_action_date && c.values.next_action_date < today)
          : converted
            ? c.status === 'CONVERTED'
            : c.status !== 'CONVERTED',
      )
      .filter((c) => !needle || ['business_name', 'promoter', 'mobile'].some((k) => (c.values[k] ?? '').toLowerCase().includes(needle)))
      .sort((a, b) => (lastMeetingAt(b) ?? '').localeCompare(lastMeetingAt(a) ?? '') || b.created_ms - a.created_ms)
    const limit = Number(q.get('limit') ?? 50)
    const list: CustomerList = { total: rows.length, items: rows.slice(0, limit).map(card) }
    return out(list)
  }

  // ---- "New lead": a prospect and its Meeting #1 in one step ----
  if (p === '/leads/new' && method === 'POST') {
    const m = body.meeting as MeetingInput
    const existing = d.customers.flatMap((c) => c.meetings.map((x) => ({ c, x }))).find((e) => e.x.id === m.id)
    if (existing) return out({ customer_id: existing.c.id, meeting: meetingOut(existing.c, existing.x) })

    const typed = Object.fromEntries(Object.entries(m.values ?? {}).filter(([k]) => k !== 'location'))
    if (!['business_name', 'promoter', 'mobile'].some((k) => String(typed[k] ?? '').trim())) {
      const message = 'enter at least Business Name, POC or Mobile'
      throw new DemoHttpError(422, { code: 'INVALID_VALUES', errors: { business_name: message, promoter: message, mobile: message } })
    }
    const mobile = normMobile(String(typed.mobile ?? ''))
    if (typed.mobile && mobile.length !== 10)
      throw new DemoHttpError(422, { code: 'INVALID_VALUES', errors: { mobile: 'must be a 10-digit mobile number' } })

    const matches = mobile ? d.customers.filter((c) => c.values.mobile === mobile) : []
    let target: DCustomer | undefined
    const choice = (body.on_duplicate as string | undefined) ?? 'ask'
    if (matches.length && choice === 'ask') {
      throw new DemoHttpError(409, {
        code: 'DUPLICATE_OWN',
        message: 'A customer with this mobile number already exists.',
        choices: ['overwrite', 'create_new', 'cancel'],
        matches: matches.map((c) => ({
          id: c.id, lead_ref: refOf(c), conversion_status: c.status, last_meeting_at: lastMeetingAt(c),
          business_name: c.values.business_name ?? null, promoter: c.values.promoter ?? null, mobile: c.values.mobile ?? null,
          loan_required: c.values.loan_required ?? null, purpose: c.values.purpose ?? null, likely_product: c.values.likely_product ?? null,
        })),
      })
    }
    if (matches.length && choice === 'overwrite') {
      target = matches.find((c) => c.id === body.overwrite_customer_id)
      if (!target) throw new DemoHttpError(422, { code: 'INVALID_VALUES', errors: { overwrite_customer_id: 'choose one of the matching records' } })
    }
    const customer = target ?? newCustomer()
    if (!target) d.customers.push(customer)
    const meeting = addMeeting(customer, { ...m, values: typed })
    save()
    return out({ customer_id: customer.id, meeting: meetingOut(customer, meeting) })
  }

  // ---- one customer ----
  let hit = matchPath(p, /^\/customers\/([^/]+)\/meetings\/([^/]+)\/retry-sync$/)
  if (hit && method === 'POST') {
    const c = find(hit[1])
    const m = c.meetings.find((x) => x.id === hit![2])
    if (!m) throw new DemoHttpError(404, 'Not found')
    if (syncOf(m) === 'FAILED') [m.failed, m.created_ms] = [false, Date.now()]
    save()
    return out(meetingOut(c, m))
  }

  hit = matchPath(p, /^\/customers\/([^/]+)\/meetings$/)
  if (hit) {
    const c = find(hit[1])
    if (method === 'GET') return out({ items: [...c.meetings].reverse().map((m) => meetingOut(c, m)) })
    if (method === 'POST') {
      mustOwn(c)
      const input = body as unknown as MeetingInput
      const again = c.meetings.find((x) => x.id === input.id)
      const meeting = again ?? addMeeting(c, input)
      save()
      return out(meetingOut(c, meeting))
    }
  }

  hit = matchPath(p, /^\/customers\/([^/]+)\/convert-form$/)
  if (hit) {
    mustOwn(find(hit[1]))
    return out(convertForm(find(hit[1])))
  }

  hit = matchPath(p, /^\/customers\/([^/]+)\/convert$/)
  if (hit && method === 'POST') {
    const c = find(hit[1])
    mustOwn(c)
    refresh(c)
    if (body.lead_values) {
      const errors = validateLead(body.lead_values as Record<string, unknown>)
      if (Object.keys(errors).length) throw new DemoHttpError(422, { code: 'INVALID_VALUES', errors })
    }
    if (c.status === 'NOT_CONVERTED' || c.status === 'CONVERSION_FAILED') {
      c.status = 'CONVERTING'
      c.convert_requested_ms = Date.now()
      save()
    }
    return out(detail(c))
  }

  hit = matchPath(p, /^\/customers\/([^/]+)$/)
  if (hit && method === 'GET') return out(detail(find(hit[1])))

  throw new DemoHttpError(404, 'Not found')
}
