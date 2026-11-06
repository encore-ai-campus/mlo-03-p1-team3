export async function runBatch(customers, run) {
  const results = await Promise.allSettled(customers.map(async (customer) => run(customer)))
  for (const result of results) {
    if (result.status === 'rejected') throw result.reason
  }
  return results.map((result) => result.value)
}
