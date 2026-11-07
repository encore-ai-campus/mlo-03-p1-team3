const admin = db.getSiblingDB('admin');
if (admin.auth('podobank-admin', process.env.MONGODB_ADMIN_PASSWORD).ok !== 1) {
  throw new Error('Monitoring account setup authentication failed');
}
// Only the two event collections are readable; no application write privileges.
const metricsRole = {role: 'podobankEventMetrics', privileges: [
  {resource: {db: 'podobank', collection: 'events_bronze'}, actions: ['find']},
  {resource: {db: 'podobank', collection: 'card_payment_locations'}, actions: ['find']}
], roles: []};
const role = admin.getRole(metricsRole.role, {showPrivileges: true});
let roleChanged = false;
if (!role) { admin.createRole(metricsRole); roleChanged = true; }
else if (JSON.stringify(role.privileges) !== JSON.stringify(metricsRole.privileges)) {
  admin.updateRole(metricsRole.role, {privileges: metricsRole.privileges, roles: []});
  roleChanged = true;
}
const roles = [{role: 'clusterMonitor', db: 'admin'}, {role: 'read', db: 'local'},
               {role: metricsRole.role, db: 'admin'}];
const existing = admin.getUser('prometheus');
let authenticated = false;
try {
  const probe = new Mongo('mongodb://127.0.0.1:27017');
  authenticated = probe.getDB('admin').auth('prometheus', process.env.METRICS_MONGODB_PASSWORD).ok === 1;
  probe.close();
} catch (_) { authenticated = false; }
const sameRoles = existing && existing.roles.length === roles.length && roles.every(
  r => existing.roles.some(e => e.role === r.role && e.db === r.db)
);
if (authenticated && sameRoles) print(roleChanged ? 'CHANGED' : 'UNCHANGED');
else {
  if (existing) admin.updateUser('prometheus', {pwd: process.env.METRICS_MONGODB_PASSWORD, roles});
  else admin.createUser({user: 'prometheus', pwd: process.env.METRICS_MONGODB_PASSWORD, roles});
  print('CHANGED');
}
