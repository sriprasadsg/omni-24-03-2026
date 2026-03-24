#!/bin/bash
# audit_compliance.sh
# Generates a Markdown-formatted compliance evidence report for Linux systems.

HOSTNAME=$(hostname)
IP_ADDR=$(hostname -I | cut -d' ' -f1)
DATE=$(date)

OUTPUT_FILE="compliance_evidence_${HOSTNAME}.md"

echo "# System Compliance Audit - Evidence" > "$OUTPUT_FILE"
echo "**Date:** $DATE" >> "$OUTPUT_FILE"
echo "**Asset:** $HOSTNAME ($IP_ADDR)" >> "$OUTPUT_FILE"
echo "**Control:** Linux Baseline Audit" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

echo "## 1. User Account Status" >> "$OUTPUT_FILE"
echo "Active user accounts with login shells:" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"
echo "| Username | UID | GID | Shell |" >> "$OUTPUT_FILE"
echo "|----------|-----|-----|-------|" >> "$OUTPUT_FILE"
awk -F: '($3 >= 1000 || $3 == 0) && $7 !~ /nologin|false/ {printf "| %-8s | %-3s | %-3s | %-5s |\n", $1, $3, $4, $7}' /etc/passwd >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

echo "## 2. Password Policy Configuration" >> "$OUTPUT_FILE"
echo "From \`/etc/login.defs\`:" >> "$OUTPUT_FILE"
echo "\`\`\`bash" >> "$OUTPUT_FILE"
grep "^PASS_" /etc/login.defs >> "$OUTPUT_FILE"
echo "\`\`\`" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

echo "## 3. SSH Configuration" >> "$OUTPUT_FILE"
echo "From \`/etc/ssh/sshd_config\` (Safety Checks):" >> "$OUTPUT_FILE"
echo "\`\`\`bash" >> "$OUTPUT_FILE"
grep -E "PermitRootLogin|PasswordAuthentication|PubkeyAuthentication" /etc/ssh/sshd_config 2>/dev/null || echo "Info: sshd_config not readable or not found." >> "$OUTPUT_FILE"
echo "\`\`\`" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

echo "## 4. Recent Sudo Commands" >> "$OUTPUT_FILE"
echo "\`\`\`log" >> "$OUTPUT_FILE"
if [ -f /var/log/auth.log ]; then
    grep "sudo:" /var/log/auth.log | tail -n 5 >> "$OUTPUT_FILE"
elif [ -f /var/log/secure ]; then
    grep "sudo:" /var/log/secure | tail -n 5 >> "$OUTPUT_FILE"
else
    echo "No auth log found." >> "$OUTPUT_FILE"
fi
echo "\`\`\`" >> "$OUTPUT_FILE"

echo "Report generated: $OUTPUT_FILE"
cat "$OUTPUT_FILE"
