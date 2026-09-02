# Required branch protection

Protect the default branch and require these GitHub Actions checks before merge:

- `backend-python-3.11`
- `backend-python-3.12`
- `backend-python-3.13`
- `contracts-lock-migrations-mcp`
- `performance-100k-baseline`
- `frontend-node-20`

Also require pull requests, dismiss stale approvals after new commits, and block force pushes.
The repository administrator must enable these settings after the workflow exists on GitHub,
and remove any previously configured `backend-python-3.10` or `backend-python-3.14` required
checks so that the required-check list matches the supported matrix above.
