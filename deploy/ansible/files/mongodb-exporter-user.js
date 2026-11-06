const admin = db.getSiblingDB('admin');
if (admin.auth('podobank-admin', process.env.MONGODB_ADMIN_PASSWORD).ok !== 1) {
  throw new Error('Monitoring account setup authentication failed');
}
const roles = [{role: 'clusterMonitor', db: 'admin'}, {role: 'read', db: 'local'}];
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
if (authenticated && sameRoles) print('UNCHANGED');
else {
  if (existing) admin.updateUser('prometheus', {pwd: process.env.METRICS_MONGODB_PASSWORD, roles});
  else admin.createUser({user: 'prometheus', pwd: process.env.METRICS_MONGODB_PASSWORD, roles});
  print('CHANGED');
}
