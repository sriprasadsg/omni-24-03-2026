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
    let mut hits: Vec<Value> = Vec::new();

    // Scan running processes: name + executable path + SHA256 (tab-delimited per line).
    // The SHA256 lets the backend enrich each hit against VirusTotal server-side.
    let proc_script = "Get-Process -EA SilentlyContinue | Where-Object { $_.Path } | ForEach-Object { \
        $h = try { (Get-FileHash -Algorithm SHA256 -LiteralPath $_.Path -EA Stop).Hash } catch { '' }; \
        \"$($_.Name)`t$($_.Path)`t$h\" }";
    let proc_text = ps(proc_script).await;
    for line in proc_text.lines() {
        let mut parts = line.splitn(3, '\t');
        let name = parts.next().unwrap_or("").trim();
        let path = parts.next().unwrap_or("").trim();
        let sha  = parts.next().unwrap_or("").trim();
        if name.is_empty() { continue; }
        for rule in RULES {
            if rule.strings.iter().any(|s| name.contains(s) || path.contains(s)) {
                hits.push(json!({
                    "rule": rule.name, "category": rule.category,
                    "target": if path.is_empty() { name } else { path },
                    "match_type": "process_name", "sha256": sha,
                }));
            }
        }
    }

    // File-content scan on common staging directories.
    // Each candidate file is emitted as `path<TAB>sha256<TAB>sanitized_content`
    // so matches carry a concrete path + hash for downstream VirusTotal lookup.
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
            $c = try {{ ([System.IO.File]::ReadAllText($_.FullName) -replace '[\r\n\t]',' ') }} catch {{ '' }}
            $h = try {{ (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName -EA Stop).Hash }} catch {{ '' }}
            $out += "$($_.FullName)`t$h`t$c"
        }}
}}
$out -join "`n"
"#);

    let file_text = ps(&script).await;
    for line in file_text.lines() {
        let mut parts = line.splitn(3, '\t');
        let path    = parts.next().unwrap_or("").trim();
        let sha     = parts.next().unwrap_or("").trim();
        let content = parts.next().unwrap_or("");
        if path.is_empty() { continue; }
        for rule in RULES {
            if rule.strings.iter().any(|s| content.contains(s)) {
                hits.push(json!({
                    "rule": rule.name, "category": rule.category,
                    "target": path, "match_type": "file_content", "sha256": sha,
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
