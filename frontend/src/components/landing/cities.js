// Example destinations for the landing page. The stops are a sample day to
// show what a TripWise itinerary looks like; real plans come from Geoapify.
export const HERO_CITIES = [
  {
    name: 'Kyoto',
    country: 'Japan',
    lat: 35.0116,
    lon: 135.7681,
    stops: ['Kinkaku-ji', 'Arashiyama Bamboo Grove', 'Pontocho Alley'],
  },
  {
    name: 'Udaipur',
    country: 'India',
    lat: 24.5854,
    lon: 73.7125,
    stops: ['City Palace', 'Lake Pichola', 'Bagore Ki Haveli'],
  },
  {
    name: 'Hallstatt',
    country: 'Austria',
    lat: 47.5622,
    lon: 13.6493,
    stops: ['Market Square', 'Hallstatt Skywalk', 'Lakeside promenade'],
  },
  {
    name: 'Lisbon',
    country: 'Portugal',
    lat: 38.7223,
    lon: -9.1393,
    stops: ['Belém Tower', 'Alfama', 'Bairro Alto'],
  },
  {
    name: 'Marrakesh',
    country: 'Morocco',
    lat: 31.6295,
    lon: -7.9811,
    stops: ['Jardin Majorelle', 'Bahia Palace', 'Jemaa el-Fnaa'],
  },
  {
    name: 'Cusco',
    country: 'Peru',
    lat: -13.532,
    lon: -71.9675,
    stops: ['Plaza de Armas', 'Qorikancha', 'San Blas'],
  },
]

// Real Lisbon places tagged with the planner's interest values, for the
// pace-and-interests preview. The live planner picks from Geoapify instead.
export const PREVIEW_CITY = 'Lisbon'
export const PREVIEW_POOL = [
  { name: 'Jerónimos Monastery', tags: ['history', 'culture'] },
  { name: 'Alfama', tags: ['culture', 'history'] },
  { name: 'Belém Tower', tags: ['history'] },
  { name: 'Time Out Market', tags: ['food'] },
  { name: 'MAAT museum', tags: ['culture'] },
  { name: 'Pastéis de Belém', tags: ['food'] },
  { name: 'LX Factory', tags: ['shopping', 'culture'] },
  { name: 'Bairro Alto', tags: ['nightlife', 'food'] },
  { name: 'Monsanto Forest Park', tags: ['nature'] },
  { name: 'Carcavelos Beach', tags: ['beaches', 'nature'] },
  { name: 'Oceanário de Lisboa', tags: ['entertainment', 'nature'] },
  { name: 'Avenida da Liberdade', tags: ['shopping'] },
  { name: 'Cinema São Jorge', tags: ['entertainment'] },
  { name: 'Costa da Caparica', tags: ['beaches'] },
  { name: 'Pink Street', tags: ['nightlife'] },
]

export const RAIL_CITIES = [
  { name: 'Hallstatt', note: 'Lakeside, slow mornings' },
  { name: 'Udaipur', note: 'Palaces after dark' },
  { name: 'Lisbon', note: 'Hills, trams and tiles' },
  { name: 'Cusco', note: 'Andes and old stone' },
  { name: 'Marrakesh', note: 'Gardens and souks' },
]
