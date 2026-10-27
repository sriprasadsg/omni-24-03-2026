// Evaluates a polkit .rules file against a stub polkit object (plain node, no dependencies).
// Usage: node polkit_rule_harness.js <path-to-rules-file>
// Prints {case: {expected, actual}} as JSON; prints one MISMATCH line per differing case and
// exits 1 when any case differs. Nothing here talks to polkit or systemd.
// The repository root package.json sets "type": "module", so this file is an ES module.
import fs from "node:fs";
import vm from "node:vm";
import process from "node:process";

var rulePath = process.argv[2];
if (!rulePath) {
    console.error("usage: node polkit_rule_harness.js <rules-file>");
    process.exit(2);
}

var rules = [];
var polkit = {
    Result: { YES: "YES", NO: "NO", NOT_HANDLED: "NOT_HANDLED", AUTH_ADMIN: "AUTH_ADMIN" },
    addRule: function (fn) { rules.push(fn); },
    log: function () {}
};
vm.runInNewContext(fs.readFileSync(rulePath, "utf8"), { polkit: polkit }, { filename: rulePath });
if (rules.length !== 1) {
    console.error("expected exactly one addRule call, got " + rules.length);
    process.exit(2);
}

function action(id, details) {
    return {
        id: id,
        lookup: function (key) {
            return Object.prototype.hasOwnProperty.call(details, key) ? details[key] : undefined;
        }
    };
}

function evaluate(user, id, details) {
    var result = rules[0](action(id, details), { user: user });
    // polkit treats a rule that returns nothing as NOT_HANDLED.
    return result === undefined || result === null ? "NOT_HANDLED" : result;
}

var MANAGE = "org.freedesktop.systemd1.manage-units";
var cases = {};
function check(name, expected, actual) { cases[name] = { expected: expected, actual: actual }; }

["mongod.service", "omni-backend.service", "nginx.service"].forEach(function (unit) {
    ["restart", "start", "reset-failed"].forEach(function (verb) {
        check("yes " + unit + " " + verb, "YES",
              evaluate("omni-watchdog", MANAGE, { unit: unit, verb: verb }));
    });
});
check("no stop", "NO", evaluate("omni-watchdog", MANAGE, { unit: "nginx.service", verb: "stop" }));
check("no kill", "NO", evaluate("omni-watchdog", MANAGE, { unit: "nginx.service", verb: "kill" }));
check("no ssh.service", "NO", evaluate("omni-watchdog", MANAGE, { unit: "ssh.service", verb: "restart" }));
check("no ollama.service by default", "NO",
      evaluate("omni-watchdog", MANAGE, { unit: "ollama.service", verb: "restart" }));
check("no unit without suffix", "NO", evaluate("omni-watchdog", MANAGE, { unit: "nginx", verb: "restart" }));
check("no missing unit detail", "NO", evaluate("omni-watchdog", MANAGE, { verb: "restart" }));
check("no missing verb detail", "NO", evaluate("omni-watchdog", MANAGE, { unit: "nginx.service" }));
check("no non-string detail", "NO", evaluate("omni-watchdog", MANAGE, { unit: ["nginx.service"], verb: "restart" }));
check("no manage-unit-files", "NO",
      evaluate("omni-watchdog", "org.freedesktop.systemd1.manage-unit-files", { unit: "nginx.service", verb: "restart" }));
check("no other systemd1 action", "NO",
      evaluate("omni-watchdog", "org.freedesktop.systemd1.reload-daemon", {}));
check("not handled other user", "NOT_HANDLED",
      evaluate("azureuser", MANAGE, { unit: "nginx.service", verb: "restart" }));
check("not handled login1.reboot", "NOT_HANDLED", evaluate("omni-watchdog", "org.freedesktop.login1.reboot", {}));
check("not handled other user login1.reboot", "NOT_HANDLED", evaluate("azureuser", "org.freedesktop.login1.reboot", {}));

var failed = false;
Object.keys(cases).forEach(function (name) {
    if (cases[name].expected !== cases[name].actual) {
        failed = true;
        console.error("MISMATCH " + name + ": expected " + cases[name].expected + " got " + cases[name].actual);
    }
});
console.log(JSON.stringify(cases, null, 2));
process.exit(failed ? 1 : 0);
