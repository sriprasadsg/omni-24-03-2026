{{/*
Expand the name of the chart.
*/}}
{{- define "omni-platform.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "omni-platform.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart label.
*/}}
{{- define "omni-platform.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "omni-platform.labels" -}}
helm.sh/chart: {{ include "omni-platform.chart" . }}
{{ include "omni-platform.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels.
*/}}
{{- define "omni-platform.selectorLabels" -}}
app.kubernetes.io/name: {{ include "omni-platform.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Service account name.
*/}}
{{- define "omni-platform.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "omni-platform.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Secret name — use existing if provided, otherwise the release-based name.
*/}}
{{- define "omni-platform.secretName" -}}
{{- if .Values.secrets.existingSecret }}
{{- .Values.secrets.existingSecret }}
{{- else }}
{{- printf "%s-secrets" (include "omni-platform.fullname" .) }}
{{- end }}
{{- end }}

{{/*
Platform key for the backend Secret, base64-encoded for `data:`.
Args: (list $previousSecretData "<data-key>" "<explicit value or empty>" "fernet"|"master")
An explicit value wins; else a valid value already in the cluster Secret is
kept (upgrades must never rotate keys and orphan encrypted data); else a new
key is generated. "fernet" = url-safe base64 of 32 random bytes (Fernet key; Sprig randBytes already returns base64);
"master" = url-safe base64 of a Fernet key (SECRETS_MASTER_KEY's format).
Values of the wrong length (e.g. the old randAlphaNum ENCRYPTION_KEY, which
Fernet rejects, so nothing was ever encrypted with it) are regenerated.
*/}}
{{- define "omni-platform.platformKey" -}}
{{- $prev := index . 0 -}}
{{- $name := index . 1 -}}
{{- $value := index . 2 -}}
{{- $kind := index . 3 -}}
{{- $wantLen := ternary 60 44 (eq $kind "master") -}}
{{- if $value -}}
{{- $value | b64enc -}}
{{- else if and (hasKey $prev $name) (eq (len (b64dec (index $prev $name))) $wantLen) -}}
{{- index $prev $name -}}
{{- else -}}
{{- $fernet := randBytes 32 | replace "+" "-" | replace "/" "_" -}}
{{- if eq $kind "master" -}}
{{- $fernet | b64enc | replace "+" "-" | replace "/" "_" | b64enc -}}
{{- else -}}
{{- $fernet | b64enc -}}
{{- end -}}
{{- end -}}
{{- end }}
