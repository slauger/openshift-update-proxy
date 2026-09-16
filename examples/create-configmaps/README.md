# create-configmaps.sh - release signature ConfigMaps for GitOps

[`create-configmaps.sh`](create-configmaps.sh) renders the release image
signatures of all releases in a set of update channels into ready-to-apply
ConfigMaps - **one file per release version and architecture**, so the manifests
can be committed to a GitOps repository and rolled out by Argo CD.

```
manifests/
├── release-signature-4.20.35-amd64.yaml
├── release-signature-4.20.36-amd64.yaml
└── release-signature-4.20.37-amd64.yaml
```

Each file holds a single ConfigMap in the form the Cluster Version Operator
expects - identical to what `oc adm release mirror` and oc-mirror produce:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: release-signature-4.20.37-amd64
  namespace: openshift-config-managed
  labels:
    release.openshift.io/verification-signatures: ""
binaryData:
  sha256-<digest>-1: <base64 signature>
```

The script only writes files. Applying them, pruning removed ones and keeping
the cluster in sync is Argo CD's job.

## Why one file per release

For updates by digest (`oc adm upgrade --to-image ...@sha256:...`) the CVO must
verify the release image signature, which in a disconnected cluster means the
signature has to be present as a ConfigMap. Rendering all of them into a single
bundle works, but every sync run rewrites the whole file - the Git history shows
one large blob changing instead of "these three releases were added". One file
per release keeps diffs and `git log` readable and lets Argo CD track resources
individually.

The ConfigMap name is not what makes a signature work - the CVO discovers the
ConfigMaps via the `release.openshift.io/verification-signatures` label in
`openshift-config-managed` and matches the `binaryData` keys against the digest
it wants to verify. The name exists to keep the repository readable.

## Requirements

- `curl` and `jq`
- network access to a running
  [openshift-update-proxy](https://github.com/slauger/openshift-update-proxy)

The script talks exclusively to the proxy, never directly to `api.openshift.com`
or `mirror.openshift.com` - that is the point in a restricted network.

## Usage

```bash
UPDATE_PROXY_URL=http://update-proxy.example.com:5000 ./create-configmaps.sh
```

Without `CHANNELS`, the script asks the proxy which OpenShift minors are still
supported (`/versions/v1/supported`) and syncs the `stable-*` channel of each of
them. It then walks the update graph of every channel and fetches the signature
for each release via `/configmaps/<version>`.

## Configuration

All configuration is done via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `UPDATE_PROXY_URL` | `http://openshift-update-proxy:5000` | Base URL of the proxy. The default is the in-cluster service name from the Helm chart. |
| `CHANNELS` | discovered | Space-separated list of update channels, e.g. `"stable-4.20 eus-4.20"`. Setting it skips the discovery. |
| `CHANNEL_PREFIX` | `stable` | Channel prefix used for the discovery and for resolving versions (`eus`, `fast`, `candidate`). |
| `ARCHITECTURES` | `amd64` | Space-separated list of architectures. |
| `OUTPUT_DIR` | `manifests` | Directory the manifests are written to. |
| `FORCE` | `false` | Re-fetch and overwrite manifests that already exist. |

### Examples

```bash
# a single channel into a cluster-specific path
CHANNELS="stable-4.20" OUTPUT_DIR=clusters/prod/signatures ./create-configmaps.sh

# EUS channels instead of stable
CHANNEL_PREFIX=eus ./create-configmaps.sh

# re-fetch everything, e.g. after Red Hat added a second signature
FORCE=true ./create-configmaps.sh
```

## Idempotency

A manifest that already exists is **not** fetched again and **not** rewritten -
the existence check happens before the signature request, so a repeated run
causes no HTTP traffic for known releases and produces no Git diff:

```
$ ./create-configmaps.sh
discovered supported channels: stable-4.22 stable-4.21 stable-4.20 ...
wrote manifests/release-signature-4.20.37-amd64.yaml
done: 1 created, 135 unchanged, 0 without signature
```

Only two requests per run are unavoidable: the update graph per channel (that is
where the version list comes from) and the channel discovery. Both are cached by
the proxy.

Releases without a published signature are counted as `without signature` and
retried on the next run - no empty file is left behind, so freshly published
releases are picked up as soon as their signature appears.

`FORCE=true` is the only way to overwrite existing files. Nothing is ever
deleted; removing a manifest is a deliberate Git commit, and Argo CD prunes the
ConfigMap on the next sync.

## Multiple architectures

The signed digest differs per architecture, so the architecture is part of the
ConfigMap name and of the file name:

```
manifests/
├── release-signature-4.20.37-amd64.yaml
└── release-signature-4.20.37-arm64.yaml
```

Both can live in the same directory and can even be applied to the same cluster
without colliding. Heterogeneous clusters run the multi payload, which has its
own digest - use `ARCHITECTURES=multi` for those.

## GitOps setup

[`sync-release-signatures.yml`](sync-release-signatures.yml) is a GitHub Actions
workflow **for the GitOps repository**: it runs the script on a schedule and
commits the newly added manifests, with a commit message listing the added
versions. Point an Argo CD Application at the resulting `manifests/` directory.

The runner needs network access to the proxy. In a restricted network use a
self-hosted runner, an OpenShift `CronJob` with a Git push step, or a Tekton
pipeline - the script itself only needs `curl` and `jq`.

## Notes

- Old signature ConfigMaps are tiny, stay valid and are still needed by clusters
  on older releases - there is no reason to clean them up on a schedule.
- Argo CD only prunes resources it manages itself, so ConfigMaps created by
  earlier `oc adm release mirror` or oc-mirror runs are not affected.
- The ConfigMaps land in `openshift-config-managed`, so Argo CD needs write
  access to that namespace.
- The ClusterVersion API also has a `spec.signatureStores` field, but it is gated
  behind the TechPreview-only `SignatureStores` feature gate and will not be
  promoted to GA ([OTA-1118](https://issues.redhat.com/browse/OTA-1118)). The
  ConfigMaps are the supported way to provide signatures.
