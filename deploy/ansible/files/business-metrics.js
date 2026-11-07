// Fixed collections and bounded aggregation; only aggregate counts leave this process.
const connection = new Mongo(process.env.MONGODB_URI);
const target = connection.getDB('podobank');
const events = ['deposit', 'withdrawal', 'transfer', 'loan_application', 'loan_review', 'loan_repayment', 'card_payment'];
const collections = {};
for (const name of ['events_bronze', 'card_payment_locations']) {
  collections[name] = target.getCollection(name).countDocuments({}, {hint: '_id_', maxTimeMS: 5000});
}
const counts = target.events_bronze.aggregate([
  {$match: {event_type: {$in: events}, outcome: {$in: ['success', 'failure']}}},
  {$group: {_id: {event_type: '$event_type', outcome: '$outcome'}, count: {$sum: 1}}},
  {$project: {_id: 0, event_type: '$_id.event_type', outcome: '$_id.outcome', count: 1}}
], {maxTimeMS: 5000, allowDiskUse: false}).toArray();
print(JSON.stringify({collections, events: counts}));
connection.close();
