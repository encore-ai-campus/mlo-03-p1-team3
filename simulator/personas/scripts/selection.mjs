export function selectActiveCustomers(customers, maximum, now = new Date(), random = Math.random) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Seoul', weekday: 'short', hour: 'numeric', hourCycle: 'h23',
  }).formatToParts(now).map(({ type, value }) => [type, value]))
  const weekday = { Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6, Sun: 7 }[parts.weekday]
  const candidates = customers.filter(({ persona }) =>
    persona.preferred_weekdays?.includes(weekday) && persona.preferred_hours?.includes(Number(parts.hour)),
  ).map((customer) => ({
    customer,
    weight: Math.max(0, customer.persona.active_days_per_week ?? 0)
      * Math.max(0, customer.persona.sessions_per_active_day ?? 0),
  })).filter(({ weight }) => weight > 0)
  const selected = []
  while (candidates.length && selected.length < maximum) {
    let draw = random() * candidates.reduce((sum, item) => sum + item.weight, 0)
    let index = candidates.length - 1
    for (let i = 0; i < candidates.length; i += 1) {
      draw -= candidates[i].weight
      if (draw < 0) { index = i; break }
    }
    selected.push(candidates.splice(index, 1)[0].customer)
  }
  return selected
}
