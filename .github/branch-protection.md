# Merge checks

On 2026-11-18 GitHub reported no classic protection on main and no required status checks in its effective rulesets. Workflow checks run independently of administrative merge enforcement.

Recommended required check names are `backend-python-3.11`, `backend-python-3.12`, `backend-python-3.13`, `contracts-lock-migrations-mcp`, `performance-100k-baseline`, `frontend-node-20`, and `offline-browser`. Keep the performance job name stable even when it records a documentation-only skip. The release job verifies the archive before attaching it to a GitHub release. See the [operator guide](../docs/development/reliability-and-release.md).
