#!/bin/bash

export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

export https_proxy=$PROXYROUTE

S3_PRIVATE_ENDPOINT_FOR_NO_PROXY="$(echo $VCAP_SERVICES | jq --raw-output --arg service_name "fac-private-s3" ".[][] | select(.name == \$service_name) | .credentials.endpoint")"
S3_PRIVATE_FIPS_ENDPOINT_FOR_NO_PROXY="$(echo $VCAP_SERVICES | jq --raw-output --arg service_name "fac-private-s3" ".[][] | select(.name == \$service_name) | .credentials.fips_endpoint")"
export no_proxy="${S3_PRIVATE_ENDPOINT_FOR_NO_PROXY},${S3_PRIVATE_FIPS_ENDPOINT_FOR_NO_PROXY},apps.internal"

export NEW_RELIC_LICENSE_KEY="$(echo "$VCAP_SERVICES" | jq --raw-output --arg service_name "newrelic-creds" ".[][] | select(.name == \$service_name) | .credentials.NEW_RELIC_LICENSE_KEY")"

# Set the application name for New Relic telemetry.
export NEW_RELIC_APP_NAME="$(echo "$VCAP_APPLICATION" | jq -r .application_name)-$(echo "$VCAP_APPLICATION" | jq -r .space_name)"

# Set the environment name for New Relic telemetry.
export NEW_RELIC_ENVIRONMENT="$(echo "$VCAP_APPLICATION" | jq -r .space_name)"

# Set Agent logging to stdout to be captured by CF Logs
export NEW_RELIC_LOG=stdout

# Logging level, (critical, error, warning, info and debug). Default to info
export NEW_RELIC_LOG_LEVEL=info

# https://docs.newrelic.com/docs/security/security-privacy/compliance/fedramp-compliant-endpoints/
export NEW_RELIC_HOST="gov-collector.newrelic.com"
# https://docs.newrelic.com/docs/apm/agents/python-agent/configuration/python-agent-configuration/#proxy
export NEW_RELIC_PROXY_HOST="$https_proxy"