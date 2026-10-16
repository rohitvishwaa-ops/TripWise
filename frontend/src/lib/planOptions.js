// Options accepted by POST /api/trips (see backend trips.py).

export const INTERESTS = [
  { value: 'culture', label: 'Culture' },
  { value: 'history', label: 'History' },
  { value: 'nature', label: 'Nature' },
  { value: 'food', label: 'Food' },
  { value: 'shopping', label: 'Shopping' },
  { value: 'nightlife', label: 'Nightlife' },
  { value: 'beaches', label: 'Beaches' },
  { value: 'entertainment', label: 'Entertainment' },
]

export const PACES = [
  { value: 'relaxed', label: 'Relaxed', detail: '2 stops a day' },
  { value: 'balanced', label: 'Balanced', detail: '3 stops a day' },
  { value: 'packed', label: 'Packed', detail: 'Up to 5 stops a day' },
]
