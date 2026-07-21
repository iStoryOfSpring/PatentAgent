# Required branch protection

Protect the default branch and require these GitHub Actions checks before merge:

- `backend-python-3.10`
- `backend-python-3.11`
- `backend-python-3.12`
- `contracts-lock-migrations-mcp`
- `frontend-node-20`

Also require pull requests, dismiss stale approvals after new commits, and block force pushes.
The repository administrator must enable these settings after the workflow exists on GitHub.
