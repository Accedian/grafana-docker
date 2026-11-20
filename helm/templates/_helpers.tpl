{{/* Only a literal HTTPS origin may become a redirect or a server setting. */}}
{{- define "grafana.validatePublicOrigin" -}}
{{- if not (regexMatch "^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?$" .) -}}
{{- fail "Grafana publicOrigin must be an HTTPS DNS or IPv4 origin without a path" -}}
{{- end -}}
{{- $host := regexReplaceAll ":[0-9]+$" (trimPrefix "https://" .) "" | trimSuffix "." -}}
{{- if or (empty $host) (gt (len $host) 253) -}}
{{- fail "Grafana publicOrigin hostname must contain between 1 and 253 characters" -}}
{{- end -}}
{{- $labels := splitList "." $host -}}
{{- range $label := $labels -}}
{{- if not (regexMatch "^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$" $label) -}}
{{- fail "Grafana publicOrigin must contain valid DNS labels of at most 63 characters" -}}
{{- end -}}
{{- end -}}
{{- /* Numeric hosts must be actual IPv4, not browser-dependent legacy IP forms. */ -}}
{{- if regexMatch "^[0-9.]+$" $host -}}
{{- if ne (len $labels) 4 -}}
{{- fail "Grafana publicOrigin IPv4 address must contain four decimal octets" -}}
{{- end -}}
{{- range $octet := $labels -}}
{{- if or (not (regexMatch "^(0|[1-9][0-9]{0,2})$" $octet)) (gt (int $octet) 255) -}}
{{- fail "Grafana publicOrigin IPv4 octets must be between 0 and 255 without leading zeroes" -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- $port := regexFind ":[0-9]+$" . | trimPrefix ":" -}}
{{- if and $port (or (lt (int $port) 1) (gt (int $port) 65535)) -}}
{{- fail "Grafana publicOrigin port must be between 1 and 65535" -}}
{{- end -}}
{{- end -}}

{{/*
Expand the name of the chart.
*/}}
{{- define "grafana.name" -}}
{{- default .Chart.Name .Values.grafana.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "grafana.fullname" -}}
{{- if .Values.grafana.fullnameOverride }}
{{- .Values.grafana.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.grafana.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "grafana.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "grafana.labels" -}}
helm.sh/chart: {{ include "grafana.chart" . }}
{{ include "grafana.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "grafana.selectorLabels" -}}
app.kubernetes.io/name: {{ include "grafana.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "grafana.serviceAccountName" -}}
{{- if .Values.grafana.serviceAccount.create }}
{{- default (include "grafana.fullname" .) .Values.grafana.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.grafana.serviceAccount.name }}
{{- end }}
{{- end }}
