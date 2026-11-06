const dateTimeFormat = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Seoul',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

export const formatNumber = (value) => value.toLocaleString('ko-KR')

export const formatWon = (value) => `${formatNumber(value)}원`

export const formatSignedWon = (value) => `${value < 0 ? '−' : '+'}${formatWon(Math.abs(value))}`

function dateTimeParts(value) {
  return Object.fromEntries(
    dateTimeFormat.formatToParts(new Date(value)).map(({ type, value: part }) => [type, part]),
  )
}

export function formatDateTime(value) {
  const parts = dateTimeParts(value)
  return `${parts.month}.${parts.day} ${parts.hour}:${parts.minute}`
}

export function formatFullDateTime(value) {
  const parts = dateTimeParts(value)
  return `${parts.year}.${parts.month}.${parts.day} ${parts.hour}:${parts.minute}`
}
