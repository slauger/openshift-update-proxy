#!/bin/bash
#
# Fetch release image signatures for all releases in the configured update
# channels via openshift-update-proxy and apply them as ConfigMaps.
#
# Requirements: curl, jq, oc (only when APPLY=true)
#
# Configuration (environment variables):
#
#   UPDATE_PROXY_URL  Base URL of the openshift-update-proxy
#                     (default: http://openshift-update-proxy:5000, the
#                     in-cluster service name from the Helm chart)
#   CHANNELS          Space-separated list of update channels (default: all
#                     currently supported versions, discovered via the
#                     /versions/v1/supported endpoint)
#   CHANNEL_PREFIX    Channel prefix for the discovery (default: stable)
#   ARCHITECTURES     Space-separated list of architectures (default: amd64)
#   OUTPUT_FILE       Bundle file to write (default: bundle.yaml)
#   APPLY             Apply the bundle with oc (default: true)
#
# Examples:
#
#   UPDATE_PROXY_URL=http://update-proxy.internal:5000 ./create-configmaps.sh
#   CHANNELS="stable-4.20 eus-4.20" APPLY=false ./create-configmaps.sh
#   CHANNEL_PREFIX=eus ./create-configmaps.sh

set -euo pipefail

UPDATE_PROXY_URL="${UPDATE_PROXY_URL:-http://openshift-update-proxy:5000}"
UPDATE_PROXY_URL="${UPDATE_PROXY_URL%/}"
CHANNEL_PREFIX="${CHANNEL_PREFIX:-stable}"
ARCHITECTURES="${ARCHITECTURES:-amd64}"
OUTPUT_FILE="${OUTPUT_FILE:-bundle.yaml}"
APPLY="${APPLY:-true}"

if [ -z "${CHANNELS:-}" ]; then
  if ! CHANNELS=$(curl -Lsf "${UPDATE_PROXY_URL}/versions/v1/supported?channel_prefix=${CHANNEL_PREFIX}" \
    | jq -r '[.versions[] | select(.latest_release != null) | .channel] | join(" ")'); then
    echo "error: failed to discover supported channels from ${UPDATE_PROXY_URL}" >&2
    exit 1
  fi
  echo "discovered supported channels: ${CHANNELS}"
fi

fetch_digests() {
  local channel arch graph
  for channel in ${CHANNELS}; do
    for arch in ${ARCHITECTURES}; do
      # the update graph API returns an empty node list for unknown channels
      if ! graph=$(curl -Lsf -H 'Accept: application/json' \
        "${UPDATE_PROXY_URL}/api/upgrades_info/v1/graph?channel=${channel}&arch=${arch}"); then
        echo "warning: failed to fetch update graph for ${channel}/${arch}" >&2
        continue
      fi
      jq -r '.nodes[]?.payload | sub(".*:"; "")' <<<"${graph}"
    done
  done | sort -u
}

bundle=$(mktemp)
trap 'rm -f "${bundle}"' EXIT

count=0
while read -r digest; do
  if ! configmap=$(curl -Lsf "${UPDATE_PROXY_URL}/configmaps/sha256=${digest}"); then
    echo "warning: no signature found for sha256:${digest}, skipping" >&2
    continue
  fi
  printf -- "---\n%s\n" "${configmap}" >>"${bundle}"
  count=$((count + 1))
done < <(fetch_digests)

if [ "${count}" -eq 0 ]; then
  echo "error: no signatures fetched - check UPDATE_PROXY_URL and CHANNELS" >&2
  exit 1
fi

mv "${bundle}" "${OUTPUT_FILE}"
trap - EXIT
echo "wrote ${count} signature configmaps to ${OUTPUT_FILE}"

if [ "${APPLY}" = "true" ]; then
  oc apply -f "${OUTPUT_FILE}"
fi
