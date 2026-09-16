#!/bin/bash
#
# Fetch release image signatures for all releases in the configured update
# channels via openshift-update-proxy and write one ConfigMap manifest per
# release version and architecture
# (manifests/release-signature-<version>-<arch>.yaml), ready to be committed to
# a GitOps repository.
#
# Requirements: curl, jq
#
# Environment variables:
#
#   UPDATE_PROXY_URL  base URL of the proxy (default: http://openshift-update-proxy:5000)
#   CHANNELS          update channels (default: discovered via /versions/v1/supported)
#   CHANNEL_PREFIX    channel prefix for the discovery (default: stable)
#   ARCHITECTURES     architectures (default: amd64)
#   OUTPUT_DIR        output directory (default: manifests)
#   FORCE             overwrite manifests that already exist (default: false)
#
# See README.md in this directory for details and a GitOps setup.

set -euo pipefail

UPDATE_PROXY_URL="${UPDATE_PROXY_URL:-http://openshift-update-proxy:5000}"
UPDATE_PROXY_URL="${UPDATE_PROXY_URL%/}"
CHANNEL_PREFIX="${CHANNEL_PREFIX:-stable}"
ARCHITECTURES="${ARCHITECTURES:-amd64}"
OUTPUT_DIR="${OUTPUT_DIR:-manifests}"
FORCE="${FORCE:-false}"

if [ -z "${CHANNELS:-}" ]; then
  if ! CHANNELS=$(curl -Lsf "${UPDATE_PROXY_URL}/versions/v1/supported?channel_prefix=${CHANNEL_PREFIX}" \
    | jq -r '[.versions[] | select(.latest_release != null) | .channel] | join(" ")'); then
    echo "error: failed to discover supported channels from ${UPDATE_PROXY_URL}" >&2
    exit 1
  fi
  echo "discovered supported channels: ${CHANNELS}"
fi

fetch_versions() {
  local channel arch graph
  for arch in ${ARCHITECTURES}; do
    for channel in ${CHANNELS}; do
      # the update graph API returns an empty node list for unknown channels
      if ! graph=$(curl -Lsf -H 'Accept: application/json' \
        "${UPDATE_PROXY_URL}/api/upgrades_info/v1/graph?channel=${channel}&arch=${arch}"); then
        echo "warning: failed to fetch update graph for ${channel}/${arch}" >&2
        continue
      fi
      jq -r --arg arch "${arch}" \
        '.nodes[]? | select(.version != null) | "\(.version) \($arch)"' <<<"${graph}"
    done
  done | sort -uV
}

mkdir -p "${OUTPUT_DIR}"

created=0
skipped=0
failed=0

# requesting by version makes the proxy name the ConfigMaps
# release-signature-<version>-<arch> instead of signature-sha256-<digest prefix>
while read -r version arch; do
  [ -n "${version}" ] || continue
  manifest="${OUTPUT_DIR}/release-signature-${version}-${arch}.yaml"

  # existing manifests are never re-fetched and never rewritten
  if [ -f "${manifest}" ] && [ "${FORCE}" != "true" ]; then
    skipped=$((skipped + 1))
    continue
  fi

  if ! configmap=$(curl -Lsf \
    "${UPDATE_PROXY_URL}/configmaps/${version}?arch=${arch}&channel_prefix=${CHANNEL_PREFIX}"); then
    echo "warning: no signature found for ${version} (${arch}), skipping" >&2
    failed=$((failed + 1))
    continue
  fi

  printf '%s\n' "${configmap}" >"${manifest}"
  echo "wrote ${manifest}"
  created=$((created + 1))
done < <(fetch_versions)

if [ "${created}" -eq 0 ] && [ "${skipped}" -eq 0 ]; then
  echo "error: no signatures fetched - check UPDATE_PROXY_URL and CHANNELS" >&2
  exit 1
fi

echo "done: ${created} created, ${skipped} unchanged, ${failed} without signature"
