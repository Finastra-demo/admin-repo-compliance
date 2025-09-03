# Repository Compliance Monitor 

# Test Bot 1

Automated repository compliance monitoring for the Finastra-demo organization.

## Features
- 🔍 Daily scanning of all repositories
- 🏷️ Automatic compliance label application
- 📊 Compliance dashboard generation
- 📋 Issue tracking for non-compliant repositories

## Usage

### Manual Scan
1. Go to Actions tab
2. Select "Repository Compliance Checker"
3. Click "Run workflow"
4. Configure options:
   - **target_org**: finastra-demo
   - **dry_run**: true (for testing)
   - **fix_issues**: false

### View Results
- **Labels**: Applied directly to repositories
- **Dashboard**: Available at https://finastra-demo.github.io/admin-repo-compliance
- **Issues**: Created in this repository for tracking

## Compliance Rules

### Naming Convention
- All repositories must start with "FD-"
- Format: `FD-{type}-{descriptive-name}`
- Examples: `FD-api-user-service`, `FD-ui-dashboard`

### Required Files
- ✅ README.md (substantial content)
- ✅ .gitignore
- ✅ CODEOWNERS
- ✅ LICENSE (for public repositories)

### Security
- ✅ Branch protection enabled on default branch
- ✅ Repository description present

### Activity
- ⚠️ Repositories inactive for 6+ months flagged as stale
- 🗃️ Repositories inactive for 1+ years flagged for archival

## Labels Applied

| Label | Color | Meaning |
|-------|-------|---------|
| `naming:missing-prefix` | 🟠 Orange | Missing "FD-" prefix |
| `missing:readme` | 🔴 Red | No README file |
| `missing:gitignore` | 🔴 Red | No .gitignore file |
| `security:no-branch-protection` | 🔴 Red | No branch protection |
| `activity:stale` | 🟠 Orange | 6+ months inactive |
| `activity:archived` | ⚫ Black | 1+ years inactive |

