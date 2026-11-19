#!/usr/bin/env bash
# MongoDB authentication for Omniai-copy (Wave 6).
#
#   scripts/mongo_auth.sh rehearse   copy omni_platform into a private mongod on 127.0.0.1:27996 with auth on,
#                                    create the users, prove what each may and may not do, then delete the copy.
#                                    Touches nothing live.
#   sudo scripts/mongo_auth.sh apply in the maintenance window: create the same users on the live mongod (it has
#                                    none, so the localhost exception allows it) and save their URLs under /etc/omni:
#                                    mongo-credentials (all, root only), mongo-app.env and mongo-backup.env (root only,
#                                    read by systemd for omni-backend and omni-backup through drop-ins, so .env is not
#                                    touched: systemd's MONGODB_URL wins over .env), mongo-test.env and mongo-read.env
#                                    (root:<user> 640, for test runs and read-only checks). Then switch on authorization
#                                    in /etc/mongod.conf (old file kept as /etc/mongod.conf.pre-auth), restart mongod
#                                    and omni-backend, and check every user and /api/health.
#   sudo scripts/mongo_auth.sh undo  authorization off again (the pre-auth mongod.conf), restart mongod and the backend.
#                                    Users and drop-ins stay: their URLs also work without authorization.
#
# Users (all in the admin database): omniAdmin root; omniApp readWrite + dbAdmin on omni_platform only (the backend
# creates its own indexes); omniBackup the built-in backup role (mongodump); omniTest readWriteAnyDatabase +
# dbAdminAnyDatabase for the test suites' throwaway omni_test_* databases (MONGO_TEST_URL), never for the app;
# omniRead read on omni_platform only, for checks by hand (MONGO_READ_URL).
set -euo pipefail

DB=omni_platform
PORT=27996
OMNI_USER="${SUDO_USER:-azureuser}"
export GLIBC_TUNABLES=glibc.pthread.rseq=1   # kernel 7.x: mongod's version check (see the mongod drop-in)

pw() { openssl rand -base64 30 | tr -d '/+=' | cut -c1-32; }

create_users() {  # $1 = mongosh URI without credentials (localhost exception)
  local uri="$1"
  ADMIN_PW=$(pw); APP_PW=$(pw); BACKUP_PW=$(pw); TEST_PW=$(pw); READ_PW=$(pw)
  mongosh --quiet "$uri/admin" --eval "
    db.createUser({user:'omniAdmin', pwd:'$ADMIN_PW', roles:['root']});
  "
  mongosh --quiet "$uri/admin" -u omniAdmin -p "$ADMIN_PW" --authenticationDatabase admin --eval "
    db.createUser({user:'omniApp', pwd:'$APP_PW', roles:[{role:'readWrite', db:'$DB'}, {role:'dbAdmin', db:'$DB'}]});
    db.createUser({user:'omniBackup', pwd:'$BACKUP_PW', roles:['backup']});
    db.createUser({user:'omniTest', pwd:'$TEST_PW', roles:['readWriteAnyDatabase', 'dbAdminAnyDatabase']});
    db.createUser({user:'omniRead', pwd:'$READ_PW', roles:[{role:'read', db:'$DB'}]});
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
  local rd="mongodb://omniRead:$READ_PW@$hp/$DB?authSource=admin"
  out=$(mongosh --quiet "$rd" --eval 'try { db.users.countDocuments(); db.x_read_check.insertOne({a:1}); print("wrote") } catch (e) { print(e.codeName === "Unauthorized" ? "read-only" : "error") }' 2>&1 | tail -1)
  expect "omniRead: reads $DB, every write refused" "$out" read-only
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

wait_for() {  # $1 = description, $2.. = command; up to 60 s
  local what="$1"; shift
  for _ in $(seq 1 60); do "$@" >/dev/null 2>&1 && return 0; sleep 1; done
  echo "$what did not come back within 60 s"; return 1
}

backend_up() { [ "$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1/api/health)" = 200 ]; }

apply() {
  [ "$(id -u)" = 0 ] || { echo "apply needs root (sudo)"; exit 1; }
  grep -q '^security:' /etc/mongod.conf && { echo "/etc/mongod.conf already has a security section; stopping"; exit 1; }
  local group; group=$(id -gn "$OMNI_USER")
  create_users "mongodb://127.0.0.1:27017"
  install -d -m 755 /etc/omni   # also holds tls/, which the backend reads; each file below has its own mode
  local base="127.0.0.1:27017"
  write() {  # $1 = file, $2 = mode, $3 = group, rest = lines
    local f="$1" mode="$2" grp="$3"; shift 3
    ( umask 077; printf '%s\n' "$@" > "$f.tmp" ); chown "root:$grp" "$f.tmp"; chmod "$mode" "$f.tmp"; mv "$f.tmp" "$f"
  }
  write /etc/omni/mongo-credentials 600 root \
    "MONGODB_URL=mongodb://omniApp:$APP_PW@$base/$DB?authSource=admin" \
    "MONGODB_URI_BACKUP=mongodb://omniBackup:$BACKUP_PW@$base/?authSource=admin" \
    "MONGO_TEST_URL=mongodb://omniTest:$TEST_PW@$base/?authSource=admin" \
    "MONGO_READ_URL=mongodb://omniRead:$READ_PW@$base/$DB?authSource=admin" \
    "MONGODB_ADMIN_URL=mongodb://omniAdmin:$ADMIN_PW@$base/admin"
  write /etc/omni/mongo-app.env 600 root "MONGODB_URL=mongodb://omniApp:$APP_PW@$base/$DB?authSource=admin"
  write /etc/omni/mongo-backup.env 600 root "MONGODB_URI=mongodb://omniBackup:$BACKUP_PW@$base/?authSource=admin"
  write /etc/omni/mongo-test.env 640 "$group" "MONGO_TEST_URL=mongodb://omniTest:$TEST_PW@$base/?authSource=admin"
  write /etc/omni/mongo-read.env 640 "$group" "MONGO_READ_URL=mongodb://omniRead:$READ_PW@$base/$DB?authSource=admin"
  for unit in omni-backend omni-backup; do
    install -d -m 755 "/etc/systemd/system/$unit.service.d"
    printf '[Service]\n# MongoDB credentials (scripts/mongo_auth.sh); they win over the URL in .env.\nEnvironmentFile=/etc/omni/%s\n' \
      "$([ $unit = omni-backend ] && echo mongo-app.env || echo mongo-backup.env)" > "/etc/systemd/system/$unit.service.d/20-mongo-auth.conf"
  done
  systemctl daemon-reload
  cp /etc/mongod.conf /etc/mongod.conf.pre-auth
  printf '\nsecurity:\n  authorization: enabled\n' >> /etc/mongod.conf
  echo "== authorization on: restarting mongod and omni-backend"
  systemctl restart mongod
  wait_for "mongod" mongosh --quiet "mongodb://omniApp:$APP_PW@$base/$DB?authSource=admin" --eval 'db.runCommand({ping: 1})'
  systemctl restart omni-backend
  wait_for "the backend (/api/health)" backend_up && echo "PASS backend: /api/health answers 200"
  check "$base"
  echo "== done. URLs: /etc/omni/mongo-credentials (root only). Undo: sudo $0 undo"
}

undo() {
  [ "$(id -u)" = 0 ] || { echo "undo needs root (sudo)"; exit 1; }
  [ -f /etc/mongod.conf.pre-auth ] || { echo "no /etc/mongod.conf.pre-auth to restore"; exit 1; }
  cp /etc/mongod.conf.pre-auth /etc/mongod.conf
  systemctl restart mongod
  wait_for "mongod" mongosh --quiet "mongodb://127.0.0.1:27017/admin" --eval 'db.runCommand({ping: 1})'
  systemctl restart omni-backend
  wait_for "the backend (/api/health)" backend_up && echo "authorization is off again; the backend answers"
}

case "${1:-}" in
  rehearse) rehearse ;;
  apply) apply ;;
  undo) undo ;;
  *) echo "usage: $0 rehearse | apply | undo"; exit 2 ;;
esac
