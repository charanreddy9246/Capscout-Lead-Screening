// Demo-mode stand-in for the GPS -> address lookup: the nearest well-known area within ~40 km.

type Spot = { lat: number; lng: number; area: string; place: string }

const SPOTS: Spot[] = [
  { lat: 13.085, lng: 80.2101, area: 'AB Block, Anna Nagar, Chennai', place: 'AB Block, 4th Avenue (Santhi Colony Road), Anna Nagar, Chennai, Tamil Nadu 600040' },
  { lat: 17.4948, lng: 78.399, area: 'Kukatpally, Hyderabad', place: 'KPHB Colony, Kukatpally, Hyderabad, Telangana 500072' },
  { lat: 17.4967, lng: 78.3556, area: 'Miyapur, Hyderabad', place: 'Miyapur, Hyderabad, Telangana 500049' },
  { lat: 17.4399, lng: 78.4983, area: 'Secunderabad', place: 'Paradise Circle, Secunderabad, Telangana 500003' },
  { lat: 12.9716, lng: 77.5946, area: 'MG Road, Bengaluru', place: 'MG Road, Bengaluru, Karnataka 560001' },
  { lat: 19.076, lng: 72.8777, area: 'Andheri, Mumbai', place: 'Andheri East, Mumbai, Maharashtra 400069' },
  { lat: 28.6139, lng: 77.209, area: 'Connaught Place, New Delhi', place: 'Connaught Place, New Delhi, Delhi 110001' },
]

function km(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const toRad = (d: number) => (d * Math.PI) / 180
  const dLat = toRad(b.lat - a.lat)
  const dLng = toRad(b.lng - a.lng)
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2
  return 6371 * 2 * Math.asin(Math.sqrt(h))
}

export function demoPlace(lat: number, lng: number): { area: string; place: string } {
  let best: Spot | null = null
  let bestKm = Infinity
  for (const s of SPOTS) {
    const d = km({ lat, lng }, s)
    if (d < bestKm) [best, bestKm] = [s, d]
  }
  if (best && bestKm <= 40) return { area: best.place, place: best.place } // the Location is the full address
  return { area: 'Your current area', place: 'Your current area, India' }
}
