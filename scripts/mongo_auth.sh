#!/usr/bin/env bash
# MongoDB authentication for Omniai-copy (Wave 6).
#
#   scripts/mongo_auth.sh rehearse   copy omni_platform into a private mongod on 127.0.0.1:27996 with auth on,
#                                    create the users, prove what each may and may not do, then delete the copy.
#                                    Touches nothing live.
#   sudo scripts/mongo_auth.sh apply in the maintenance window: create the same users on the live mongod (it has
#                                    none, so the localhost exception allows it), save their passwords to
#                                    /etc/omni/mongo-credentials (root only), switch on authorization in
#                                    /etc/mongod.conf (old file kept as /etc/mongod.conf.pre-auth) and restart mongod.
#                                    Then put the printed omniApp URL into .env as MONGODB_URL, add the omniBackup URL
#                                    to omni-backup as MONGODB_URI, restart omni-backend, and check /api/health.
#                                    Undo: copy /etc/mongod.conf.pre-auth back and restart mongod.
#
# Users (all in the admin database): omniAdmin root; omniApp readWrite + dbAdmin on omni_platform only (the backend
# creates its own indexes); omniBackup the built-in backup role (mongodump); omniTest readWriteAnyDatabase +
# dbAdminAnyDatabase for the test suites' throwaway omni_test_* databases (MONGO_TEST_URL), never for the app.
set -euo pipefail

DB=omni_platform
PORT=27996
export GLIBC_TUNABLES=glibc.pthread.rseq=1   # kernel 7.x: mongod's version check (see the mongod drop-in)

pw() { openssl rand -base64 30 | tr -d '/+=' | cut -c1-32; }

create_users() {  # $1 = mongosh URI without credentials (localhost exception)
  local uri="$1"
  ADMIN_PW=$(pw); APP_PW=$(pw); BACKUP_PW=$(pw); TEST_PW=$(pw)
  mongosh --quiet "$uri/admin" --eval "
    db.createUser({user:'omniAdmin', pwd:'$ADMIN_PW', roles:['root']});
  "
  mongosh --quiet "$uri/admin" -u omniAdmin -p "$ADMIN_PW" --authenticationDatabase admin --eval "
    db.createUser({user:'omniApp', pwd:'$APP_PW', roles:[{role:'readWrite', db:'$DB'}, {role:'dbAdmin', db:'$DB'}]});
    db.createUser({user:'omniBackup', pwd:'$BACKUP_PW', roles:['backup']});
    db.createUser({user:'omniTest', pwd:'$TEST_PW', roles:['readWriteAnyDatabase', 'dbAdminAnyDatabase']});
  "
}

check() {  # $1 = host:port; prints PASS/FAIL lines, exits 1 on any FAIL
  local hp="$1" fail=0
  local app="mongodb://omniApp:$APP_PW@$hp/$DB?authSource=admin"
  expect() { if [ "$2" = "$3" ]; then echo "PASS $1"; else echo "FAIL $1 (got $2, want $3)"; fail=1; fi; }
  out=$(mongosh --quiet "mongodb://$hp/$DB" --eval 'try { db.users.findOne(); print("read") } catch (e) { print("refused") }' 2>&1 | tail -1)
  expect "no credentials: reading is refused" "$out" refused
  out=$(mongosh --quiet "$app" --eval '
    const n = db.users.countDocuments(); db.scim_rehearsal.insertOne({a: 1}); db.scim_rehearsal.createIndex({a: 1});
    db.scim_rehearsal.aggregate([{$match: {a: 1}}]).toArray(); db.scim_rehearsal.drop(); print(n >= 0 ? "ok" : "no")' 2>&1 | tail -1)
  expect "omniApp: read, write, index, aggregate, drop on $DB" "$out" ok
  out=$(mongosh --quiet "$app" --eval 'try { db.getSiblingDB("admin").system.users.findOne(); print("read") } catch (e) { print("refused") }' 2>&1 | tail -1)
  expect "omniApp: the admin user list is refused" "$out" refused
  out=$(mongosh --quiet "$app" --eval 'try { db.getSiblingDB("other_db").x.insertOne({a:1}); print("wrote") } catch (e) { print("refused") }' 2>&1 | tail -1)
  expect "omniApp: other databases are refused" "$out" refused
  if mongodump --quiet --uri "mongodb://omniBackup:$BACKUP_PW@$hp/?authSource=admin" --db "$DB" --archive=/dev/null 2>/dev/null; then
    echo "PASS omniBackup: mongodump of $DB"; else echo "FAIL omniBackup: mongodump of $DB"; fail=1; fi
  out=$(mongosh --quiet "mongodb://omniTest:$TEST_PW@$hp/omni_test_rehearsal?authSource=admin" --eval '
    db.x.insertOne({a:1}); db.dropDatabase(); print("ok")' 2>&1 | tail -1)
  expect "omniTest: a throwaway test database can be created and dropped" "$out" ok
  return $fail
}

cleanup_rehearsal() {  # the copy holds live data (password hashes included): always removed
  mongosh --quiet "mongodb://omniAdmin:${ADMIN_PW:-x}@127.0.0.1:$PORT/admin" --eval "db.shutdownServer()" >/dev/null 2>&1 || true
  sleep 1
  [ -n "${REHEARSAL_DIR:-}" ] && rm -rf "$REHEARSAL_DIR"
}

rehearse() {
  REHEARSAL_DIR=$(mktemp -d /tmp/omni-mongo-rehearsal.XXXXXX)
  local dir="$REHEARSAL_DIR"
  trap cleanup_rehearsal EXIT
  echo "== copying $DB from the live mongod (read only)"
  mongodump --quiet --uri "mongodb://127.0.0.1:27017" --db "$DB" --archive="$dir/dump.archive" --gzip
  mkdir -p "$dir/data"
  mongod --dbpath "$dir/data" --port "$PORT" --bind_ip 127.0.0.1 --auth --fork --logpath "$dir/mongod.log" >/dev/null
  create_users "mongodb://127.0.0.1:$PORT"
  mongorestore --quiet --uri "mongodb://omniAdmin:$ADMIN_PW@127.0.0.1:$PORT/?authSource=admin" --gzip --archive="$dir/dump.archive"
  echo "== restored $(mongosh --quiet "mongodb://omniApp:$APP_PW@127.0.0.1:$PORT/$DB?authSource=admin" --eval 'db.getCollectionNames().length') collections"
  check "127.0.0.1:$PORT"
  echo "== rehearsal passed; the private copy is deleted on exit"
}

apply() {
  [ "$(id -u)" = 0 ] || { echo "apply needs root (sudo)"; exit 1; }
  grep -q '^security:' /etc/mongod.conf && { echo "/etc/mongod.conf already has a security section; stopping"; exit 1; }
  create_users "mongodb://127.0.0.1:27017"
  install -d -m 700 /etc/omni
  umask 077
  cat > /etc/omni/mongo-credentials <<EOF
MONGODB_URL=mongodb://omniApp:$APP_PW@127.0.0.1:27017/$DB?authSource=admin
MONGODB_URI_BACKUP=mongodb://omniBackup:$BACKUP_PW@127.0.0.1:27017/?authSource=admin
MONGO_TEST_URL=mongodb://omniTest:$TEST_PW@127.0.0.1:27017/?authSource=admin
MONGODB_ADMIN_URL=mongodb://omniAdmin:$ADMIN_PW@127.0.0.1:27017/admin
EOF
  cp /etc/mongod.conf /etc/mongod.conf.pre-auth
  printf '\nsecurity:\n  authorization: enabled\n' >> /etc/mongod.conf
  systemctl restart mongod
  sleep 3
  check "127.0.0.1:27017"
  echo "== authorization is on. Credentials: /etc/omni/mongo-credentials (root only)."
  echo "   Next: MONGODB_URL from that file into .env, MONGODB_URI_BACKUP as MONGODB_URI for omni-backup, restart omni-backend."
}

case "${1:-}" in
  rehearse) rehearse ;;
  apply) apply ;;
  *) echo "usage: $0 rehearse | apply"; exit 2 ;;
esac
