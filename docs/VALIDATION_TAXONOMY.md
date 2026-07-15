# Validation Taxonomy

## What can be validated with what evidence?

| Evidence | Reader | Metadata | Image analysis | Force spectroscopy | Physical model fitting |
|---|---:|---:|---:|---:|---:|
| Raw file only | Yes | Partial | No | No | No |
| Raw + processed image | Yes | Partial | Candidate | No | No |
| Raw + processed curve | Yes | Partial | N/A | Candidate | Candidate |
| Raw + method parameters | Yes | Better | Candidate | Candidate | Candidate |
| Raw + code + output | Yes | Better | Strong candidate | Strong candidate | Strong candidate |
| Published scalar only | No | No | Weak reference | Weak reference | Weak reference |

“Candidate” still requires matched conventions, units, and parameters.

## Utility class decision tree

```text
AFM/SPM relevance established?
├── no → incomplete
└── yes
    ├── distinct raw + processed/reference?
    │   ├── yes + method/code → benchmark_ready
    │   └── yes, no method/code → crosscheck_candidate
    ├── raw only → reader_fixture
    ├── processed only → processed_reference_only
    ├── code/docs only → documentation_only
    └── otherwise → incomplete
```

## Reference software

Gwyddion may provide an independent reference for image operations when the
version, parameters, units, and operation order are recorded. It is not a
universal reference for all force-spectroscopy models or proprietary metadata.
