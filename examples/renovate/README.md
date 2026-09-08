# Renovate integration for OLM operator updates

Renovate can keep pinned operator versions (`startingCSV` in OLM `Subscription`
manifests) up to date using the `/operators/v1/` endpoints of
openshift-update-proxy as a [custom datasource](https://docs.renovatebot.com/modules/datasource/custom/).

## Files

- [`renovate.json`](renovate.json) - custom datasource + regex manager configuration
- [`subscription.yaml`](subscription.yaml) - a pinned OLM Subscription managed by Argo CD
- [`acm-policy.yaml`](acm-policy.yaml) - the same Subscription embedded in an ACM Policy

## How it works

The regex manager extracts three values from every matched Subscription:

| Capture group | YAML field | Used for |
|---------------|------------|----------|
| `currentChannel` | `spec.channel` | channel segment of the datasource URL |
| `packageName` | `spec.name` | package segment of the datasource URL |
| `catalogSource` | `spec.source` | catalog segment of the datasource URL (`redhat-operators`, `certified-operators`, `community-operators`, `redhat-marketplace`) |
| `currentValue` | `spec.startingCSV` (version suffix after `.v`) | current version |

Renovate then queries

```
http://update-proxy.example.com:5000/operators/v1/{{catalogSource}}/{{packageName}}/{{currentChannel}}/releases
```

which already returns the exact format Renovate expects
(`{"releases": [{"version": "1.21.4", ...}]}`), so no `transformTemplates`
are needed. When a newer version exists in the channel, Renovate opens a PR
bumping `startingCSV: openshift-gitops-operator.v1.21.0` to
`startingCSV: openshift-gitops-operator.v1.21.4`.

With `installPlanApproval: Manual` (or ACM enforcing the Subscription), merging
the PR is what rolls out the operator update - the catalog may already contain
newer versions, but the cluster only moves when the pinned CSV changes.

## Notes

- The regex relies on the alphabetical field order of `Subscription.spec`
  (`channel` before `name` before `source` before `startingCSV`). Keep one
  Subscription per file, or at least ensure every matched document contains a
  `startingCSV`, so the lazy quantifiers do not match across documents.
- Append `?ocp_version=4.16` to the `registryUrlTemplate` to only see versions
  shipped in the catalog for that OpenShift minor version.
- The `packageRules` entry filters out patched builds
  (e.g. `1.13.3+0.1741683398.p`): their CSV names encode the suffix with a `-`
  instead of `+`, so a naive replacement would produce an invalid CSV name.
  Remove the rule only if you handle those versions yourself.
- Discover available channels and the default channel via
  `GET /operators/v1/<catalog>/<package>/channels`.
