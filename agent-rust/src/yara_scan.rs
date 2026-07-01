/*!
 * YARA-equivalent malware scanner via PowerShell string matching.
 * Checks running processes and common staging directories against
 * known malware signatures: Mimikatz, LaZagne, Ransomware, WannaCry,
 * ProcessInjection, ReflectiveDLL.
 */
use serde_json::{json, Value};

struct Rule {
    name:     &'static str,
    category: &'static str,
    strings:  &'static [&'static str],
}

static RULES: &[Rule] = &[
    Rule { name: "MimikatzSignatures",      category: "credential_dumper",
           strings: &["sekurlsa", "lsadump", "mimikatz", "logonpasswords", "wdigest"] },
    Rule { name: "LaZagneCredentialDumper", category: "credential_dumper",
           strings: &["lazagne", "credentialfiles", "wlancredentials", "pypykatz"] },
    Rule { name: "RansomwareGeneric",       category: "ransomware",
           strings: &["your files are encrypted", "how_to_restore", "ransomnote", ".locked"] },
    Rule { name: "WannaCryIndicators",      category: "ransomware",
           strings: &["wannacry", "wncry", "tasksche", "wcry@123", "wanadecryptor"] },
    Rule { name: "ProcessInjectionAPIs",    category: "injection",
           strings: &["virtualallocex", "writeprocessmemory", "createremotethread", "ntqueueapcthread"] },
    Rule { name: "ReflectiveDLLInjection", category: "injection",
           strings: &["reflectivedllinjection", "reflectiveloader", "loadremotelibraryr"] },
];

async fn ps(cmd: &str) -> String {
    match tokio::process::Command::new(crate::http::PS_EXE)
        .args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", cmd])
        .output().await
    {
        Ok(out) => String::from_utf8_lossy(&out.stdout).to_lowercase(),
        Err(_)  => String::new(),
    }
}

pub async fn run_yara_scan(extra_paths: &[&str]) -> Value {
    // Scan running process names for in-memory indicators
    let proc_text = ps("Get-Process | Select-Object -ExpandProperty Name").await;
    let mut hits: Vec<Value> = Vec::new();

    for line in proc_text.lines() {
        let proc = line.trim();
        if proc.is_empty() { continue; }
        for rule in RULES {
            if rule.strings.iter().any(|s| proc.contains(s)) {
                hits.push(json!({
                    "rule": rule.name, "category": rule.category,
                    "target": proc, "match_type": "process_name"
                }));
            }
        }
    }

    // File-content scan on common staging directories
    let default_dirs: &[&str] = &[r"C:\Temp", r"C:\Users\Public\Downloads", r"C:\Windows\Temp"];
    let dirs: Vec<&str> = if extra_paths.is_empty() {
        default_dirs.to_vec()
    } else {
        extra_paths.to_vec()
    };

    let dir_args = dirs.iter()
        .map(|d| format!("'{}'", d.replace('\'', "''")))
        .collect::<Vec<_>>()
        .join(", ");

    let script = format!(r#"
$out = @()
foreach ($d in @({dir_args})) {{
    if (-not (Test-Path $d)) {{ continue }}
    Get-ChildItem -Path $d -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object {{ $_.Length -lt 2MB }} |
        ForEach-Object {{
            $c = try {{ [System.IO.File]::ReadAllText($_.FullName) }} catch {{ '' }}
            $out += "$($_.FullName): $c"
        }}
}}
$out -join "`n"
"#);

    let file_text = ps(&script).await;
    for rule in RULES {
        if rule.strings.iter().any(|s| file_text.contains(s)) {
            let already = hits.iter().any(|h| {
                h.get("rule").and_then(|r| r.as_str()) == Some(rule.name) &&
                h.get("match_type").and_then(|t| t.as_str()) != Some("process_name")
            });
            if !already {
                hits.push(json!({
                    "rule": rule.name, "category": rule.category,
                    "target": "staged_files", "match_type": "file_content"
                }));
            }
        }
    }

    json!({
        "status": "success",
        "threats_found": !hits.is_empty(),
        "match_count": hits.len(),
        "rules_applied": RULES.len(),
        "matches": hits,
        "scan_paths": dirs,
    })
}
