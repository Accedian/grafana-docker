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

{{/* Quote a user string for alerting YAML, escaping literal $ as $$ (Grafana env expansion). */}}
{{- define "grafana.quoteAlerting" -}}
{{- . | replace "$" "$$" | quote -}}
{{- end }}

{{- define "grafana.escapeAlertingString" -}}
{{- . | replace "$" "$$" -}}
{{- end }}

{{- define "grafana.fileRef" -}}
{{- printf "$__file{%s}" . | quote -}}
{{- end }}

{{/* Boolean helpers return the string "true" or empty. */}}
{{- define "grafana.customerEmailEnabled" -}}
{{- $smtp := default dict .Values.grafana.smtp -}}
{{- $alerting := default dict .Values.grafana.alerting -}}
{{- $cps := default dict $alerting.contactPoints -}}
{{- $email := default dict $cps.email -}}
{{- if and (default false $email.enabled) (default false $smtp.enabled) -}}
true
{{- end -}}
{{- end }}

{{- define "grafana.customerWebhookEnabled" -}}
{{- $alerting := default dict .Values.grafana.alerting -}}
{{- $cps := default dict $alerting.contactPoints -}}
{{- $webhook := default dict $cps.webhook -}}
{{- if default false $webhook.enabled -}}
true
{{- end -}}
{{- end }}

{{- define "grafana.customerPolicyManaged" -}}
{{- $alerting := default dict .Values.grafana.alerting -}}
{{- $np := default dict $alerting.notificationPolicy -}}
{{- if and (default false $np.managed) (or (include "grafana.customerEmailEnabled" .) (include "grafana.customerWebhookEnabled" .)) -}}
true
{{- end -}}
{{- end }}

{{- define "grafana.customerResetPolicies" -}}
{{- $alerting := default dict .Values.grafana.alerting -}}
{{- $np := default dict $alerting.notificationPolicy -}}
{{- if and (default false $np.resetPoliciesOnDisable) (not (include "grafana.customerPolicyManaged" .)) -}}
true
{{- end -}}
{{- end }}

{{- define "grafana.renderNotificationPolicies" -}}
{{- if or (include "grafana.customerPolicyManaged" .) (include "grafana.customerResetPolicies" .) -}}
true
{{- end -}}
{{- end }}

{{- define "grafana.hostnameFromURL" -}}
{{- $raw := . | toString | trim -}}
{{- if hasPrefix "https://" $raw -}}
{{- $raw = trimPrefix "https://" $raw -}}
{{- else if hasPrefix "http://" $raw -}}
{{- $raw = trimPrefix "http://" $raw -}}
{{- end -}}
{{- $raw = regexReplaceAll "[/?#].*$" $raw "" -}}
{{- if contains "@" $raw -}}
{{- $raw = regexReplaceAll "^.*@" $raw "" -}}
{{- end -}}
{{- if hasPrefix "[" $raw -}}
{{- regexReplaceAll "^\\[([^]]+)\\](?::[0-9]+)?$" $raw (printf "$%s" "1") -}}
{{- else -}}
{{- regexReplaceAll ":[0-9]+$" $raw "" -}}
{{- end -}}
{{- end }}

{{- define "grafana.proxyListen" -}}
{{- $raw := . | toString | trim -}}
{{- $defaultPort := "80" -}}
{{- if hasPrefix "https://" $raw -}}
{{- $defaultPort = "443" -}}
{{- $raw = trimPrefix "https://" $raw -}}
{{- else if hasPrefix "http://" $raw -}}
{{- $raw = trimPrefix "http://" $raw -}}
{{- end -}}
{{- $raw = regexReplaceAll "[/?#].*$" $raw "" -}}
{{- if contains "@" $raw -}}
{{- $raw = regexReplaceAll "^.*@" $raw "" -}}
{{- end -}}
{{- $hp := include "grafana.splitHostPort" $raw | trim -}}
{{- $parts := compact (splitList " " $hp) -}}
{{- $host := "" -}}
{{- if ge (len $parts) 1 -}}
{{- $host = index $parts 0 -}}
{{- end -}}
{{- $port := $defaultPort -}}
{{- if ge (len $parts) 2 -}}
{{- $port = index $parts 1 -}}
{{- end -}}
{{- if empty $port -}}
{{- $port = $defaultPort -}}
{{- end -}}
{{- printf "%s %s" $host $port -}}
{{- end }}

{{- define "grafana.deniedProxyHostReason" -}}
{{- $host := lower (trim (default "" .)) -}}
{{- if empty $host -}}
host is empty
{{- else if or (eq $host "localhost") (hasSuffix ".localhost" $host) (eq $host "ip6-localhost") -}}
loopback hostname is not allowed
{{- else if or (eq $host "::1") (eq $host "0:0:0:0:0:0:0:1") (eq $host "::") -}}
IPv6 loopback or unspecified address is not allowed
{{- else if regexMatch "(?i)^fe80:" $host -}}
link-local address is not allowed
{{- else if regexMatch "(?i)^::ffff:" $host -}}
IPv4-mapped IPv6 address is not allowed
{{- else if regexMatch "^127\\." $host -}}
loopback address is not allowed
{{- else if regexMatch "^169\\.254\\." $host -}}
link-local or cloud metadata address is not allowed
{{- else if eq $host "0.0.0.0" -}}
unspecified address is not allowed
{{- end -}}
{{- end }}

{{- define "grafana.splitHostPort" -}}
{{- $raw := . | toString | trim -}}
{{- if hasPrefix "[" $raw -}}
{{- regexReplaceAll "^\\[([^]]+)\\](?::([0-9]+))?$" $raw (printf "$%s $%s" "1" "2") -}}
{{- else -}}
{{- $parts := splitList ":" $raw -}}
{{- if eq (len $parts) 2 -}}
{{- printf "%s %s" (index $parts 0) (index $parts 1) -}}
{{- else -}}
{{- printf "%s " $raw -}}
{{- end -}}
{{- end -}}
{{- end }}

{{/*
Return a denial reason for a hostname, or empty if the host is allowed.
Pass dict with keys host and allowPrivate.
*/}}
{{- define "grafana.deniedHostReason" -}}
{{- $host := lower (trim (default "" .host)) -}}
{{- $allowPrivate := default false .allowPrivate -}}
{{- if empty $host -}}
host is empty
{{- else if or (eq $host "localhost") (hasSuffix ".localhost" $host) (eq $host "ip6-localhost") -}}
loopback hostname is not allowed
{{- else if or (eq $host "::1") (eq $host "0:0:0:0:0:0:0:1") (eq $host "::") -}}
IPv6 loopback or unspecified address is not allowed
{{- else if regexMatch "(?i)^fe80:" $host -}}
link-local address is not allowed
{{- else if regexMatch "(?i)^::ffff:" $host -}}
{{- $mapped := regexReplaceAll "(?i)^::ffff:" $host "" -}}
{{- if regexMatch "^[0-9a-f:]+$" $mapped -}}
IPv4-mapped IPv6 address is not allowed
{{- else -}}
{{- $nested := include "grafana.deniedHostReason" (dict "host" $mapped "allowPrivate" $allowPrivate) | trim -}}
{{- if $nested -}}
IPv4-mapped {{ $nested }}
{{- else -}}
IPv4-mapped IPv6 address is not allowed
{{- end -}}
{{- end -}}
{{- else if or (hasSuffix ".svc" $host) (hasSuffix ".svc.cluster.local" $host) -}}
cluster service hostname is not allowed
{{- else if regexMatch "^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$" $host -}}
{{- $octets := splitList "." $host -}}
{{- $a := index $octets 0 | int -}}
{{- $b := index $octets 1 | int -}}
{{- $c := index $octets 2 | int -}}
{{- $d := index $octets 3 | int -}}
{{- if or (gt $a 255) (gt $b 255) (gt $c 255) (gt $d 255) -}}
invalid IPv4 address
{{- else if eq $a 127 -}}
loopback address is not allowed
{{- else if and (eq $a 0) (eq $b 0) (eq $c 0) (eq $d 0) -}}
unspecified address is not allowed
{{- else if eq $a 169 -}}
{{- if eq $b 254 -}}
link-local or cloud metadata address is not allowed
{{- else if not $allowPrivate -}}
private or reserved address is not allowed
{{- end -}}
{{- else if and (eq $a 10) (not $allowPrivate) -}}
RFC1918 private address is not allowed
{{- else if and (eq $a 192) (eq $b 168) (not $allowPrivate) -}}
RFC1918 private address is not allowed
{{- else if and (eq $a 172) (ge $b 16) (le $b 31) (not $allowPrivate) -}}
RFC1918 private address is not allowed
{{- end -}}
{{- else if and (not (contains "." $host)) (not (contains ":" $host)) -}}
single-label cluster service name is not allowed
{{- end -}}
{{- end }}

{{- define "grafana.validateAlerting" -}}
{{- $smtp := default dict .Values.grafana.smtp -}}
{{- $alerting := default dict .Values.grafana.alerting -}}
{{- $cps := default dict $alerting.contactPoints -}}
{{- $email := default dict $cps.email -}}
{{- $webhook := default dict $cps.webhook -}}
{{- $proxy := default dict .Values.grafana.proxy -}}
{{- $security := default dict .Values.grafana.security -}}
{{- if and (default false $smtp.enabled) -}}
{{- if empty (default "" $smtp.host) -}}
{{- fail "grafana.smtp.host is required when SMTP is enabled" -}}
{{- end -}}
{{- if empty (default "" $smtp.fromAddress) -}}
{{- fail "grafana.smtp.fromAddress is required when SMTP is enabled" -}}
{{- end -}}
{{- $policy := default "OpportunisticStartTLS" $smtp.startTlsPolicy -}}
{{- if not (has $policy (list "OpportunisticStartTLS" "MandatoryStartTLS" "NoStartTLS")) -}}
{{- fail "grafana.smtp.startTlsPolicy must be OpportunisticStartTLS, MandatoryStartTLS, or NoStartTLS" -}}
{{- end -}}
{{- if regexMatch "[\\s;|&`$<>(){}\\n\\r]" (toString $smtp.host) -}}
{{- fail "grafana.smtp.host contains unsupported shell or whitespace characters" -}}
{{- end -}}
{{- $hp := splitList " " (include "grafana.splitHostPort" $smtp.host | trim) -}}
{{- $smtpHostname := index $hp 0 -}}
{{- $smtpPort := "" -}}
{{- if ge (len $hp) 2 -}}
{{- $smtpPort = index $hp 1 -}}
{{- end -}}
{{- if empty $smtpPort -}}
{{- fail "grafana.smtp.host must be host:port" -}}
{{- end -}}
{{- if not (regexMatch "^[0-9]+$" $smtpPort) -}}
{{- fail "grafana.smtp.host port must be numeric" -}}
{{- end -}}
{{- if or (lt (int $smtpPort) 1) (gt (int $smtpPort) 65535) -}}
{{- fail "grafana.smtp.host port must be between 1 and 65535" -}}
{{- end -}}
{{- $smtpDeny := include "grafana.deniedHostReason" (dict "host" $smtpHostname "allowPrivate" (default false $smtp.allowPrivate)) | trim -}}
{{- if $smtpDeny -}}
{{- fail (printf "grafana.smtp.host rejected: %s" $smtpDeny) -}}
{{- end -}}
{{- end -}}
{{- if default false $email.enabled -}}
{{- if not (default false $smtp.enabled) -}}
{{- fail "grafana.alerting.contactPoints.email requires grafana.smtp.enabled" -}}
{{- end -}}
{{- $raw := default "" $email.addresses | toString -}}
{{- if empty (trim $raw) -}}
{{- fail "grafana.alerting.contactPoints.email.addresses is required when email contact points are enabled" -}}
{{- end -}}
{{- $normalized := $raw | replace ";" "," -}}
{{- $parts := splitList "," $normalized -}}
{{- $count := 0 -}}
{{- range $parts -}}
{{- $addr := trim . -}}
{{- if not (empty $addr) -}}
{{- $count = add1 $count -}}
{{- if not (regexMatch "^[^@\\s]+@[^@\\s]+$" $addr) -}}
{{- fail "grafana.alerting.contactPoints.email.addresses must contain valid email addresses" -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- if gt $count 50 -}}
{{- fail "grafana.alerting.contactPoints.email.addresses supports at most 50 recipients" -}}
{{- end -}}
{{- if eq $count 0 -}}
{{- fail "grafana.alerting.contactPoints.email.addresses is required when email contact points are enabled" -}}
{{- end -}}
{{- end -}}
{{- if default false $webhook.enabled -}}
{{- $url := default "" $webhook.url | toString | trim -}}
{{- if empty $url -}}
{{- fail "grafana.alerting.contactPoints.webhook.url is required when the webhook is enabled" -}}
{{- end -}}
{{- if not (hasPrefix "https://" $url) -}}
{{- fail "grafana.alerting.contactPoints.webhook.url must use https://" -}}
{{- end -}}
{{- $method := default "POST" $webhook.httpMethod | upper -}}
{{- if not (has $method (list "POST" "PUT")) -}}
{{- fail "grafana.alerting.contactPoints.webhook.httpMethod must be POST or PUT" -}}
{{- end -}}
{{- $authType := default "none" $webhook.authType -}}
{{- if not (has $authType (list "none" "bearer" "basic")) -}}
{{- fail "grafana.alerting.contactPoints.webhook.authType must be none, bearer, or basic" -}}
{{- end -}}
{{- if and (has $authType (list "bearer" "basic")) (empty (default "" $webhook.existingSecret)) -}}
{{- fail "grafana.alerting.contactPoints.webhook.existingSecret is required for bearer or basic auth" -}}
{{- end -}}
{{- if and (eq $authType "basic") (empty (default "" $webhook.basicAuthUser)) -}}
{{- fail "grafana.alerting.contactPoints.webhook.basicAuthUser is required for basic auth" -}}
{{- end -}}
{{- $whHost := include "grafana.hostnameFromURL" $url | trim -}}
{{- $whDeny := include "grafana.deniedHostReason" (dict "host" $whHost "allowPrivate" (default false $webhook.allowPrivate)) | trim -}}
{{- if $whDeny -}}
{{- fail (printf "grafana.alerting.contactPoints.webhook.url rejected: %s" $whDeny) -}}
{{- end -}}
{{- $maxAlerts := default 0 $webhook.maxAlerts | int -}}
{{- if lt $maxAlerts 0 -}}
{{- fail "grafana.alerting.contactPoints.webhook.maxAlerts must be >= 0" -}}
{{- end -}}
{{- end -}}
{{- $ca := default "" $webhook.caCertPem | toString -}}
{{- if not (empty $ca) -}}
{{- if gt (len $ca) 65536 -}}
{{- fail "grafana.alerting.contactPoints.webhook.caCertPem must be at most 64 KiB" -}}
{{- end -}}
{{- if contains "PRIVATE KEY" $ca -}}
{{- fail "grafana.alerting.contactPoints.webhook.caCertPem must not contain a PRIVATE KEY" -}}
{{- end -}}
{{- if not (contains "BEGIN CERTIFICATE" $ca) -}}
{{- fail "grafana.alerting.contactPoints.webhook.caCertPem must contain a PEM BEGIN CERTIFICATE block" -}}
{{- end -}}
{{- end -}}
{{- if default false $proxy.enabled -}}
{{- if and (empty (default "" $proxy.httpProxy)) (empty (default "" $proxy.httpsProxy)) -}}
{{- fail "grafana.proxy.httpProxy or grafana.proxy.httpsProxy is required when proxy is enabled" -}}
{{- end -}}
{{- range $key := (list "httpProxy" "httpsProxy") -}}
{{- $url := index $proxy $key | default "" | toString | trim -}}
{{- if $url -}}
{{- if not (or (hasPrefix "http://" $url) (hasPrefix "https://" $url)) -}}
{{- fail (printf "grafana.proxy.%s must use http:// or https://" $key) -}}
{{- end -}}
{{- $host := include "grafana.hostnameFromURL" $url | trim -}}
{{- $deny := include "grafana.deniedProxyHostReason" $host | trim -}}
{{- if $deny -}}
{{- fail (printf "grafana.proxy.%s rejected: %s" $key $deny) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end }}
