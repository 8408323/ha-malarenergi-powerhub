# Contributing

## Branch naming

Branches must follow the `type/short-description` pattern using lowercase kebab-case:

| Prefix | When to use |
|---|---|
| `feat/` | New feature |
| `fix/` | Bug fix |
| `docs/` | Documentation only |
| `chore/` | CI, deps, tooling, housekeeping |
| `refactor/` | Code restructuring without behaviour change |
| `test/` | Tests only |

Examples: `feat/qr-web-component`, `fix/translations-blank-dialog`, `docs/setup-guide`

## Pull requests

- All PRs target `main`
- Squash merge only (configured in repo settings)
- CI (`test`) must pass
- 1 approval required
- All review threads must be resolved before merge
- Branch is deleted automatically after merge

## Commit messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add QR web component for BankID config flow
fix: revert qr_image placeholder causing blank dialog
docs: complete setup guide with step-by-step instructions
chore: remove redundant strings.json
```
