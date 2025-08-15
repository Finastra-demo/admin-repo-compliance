#!/usr/bin/env python3
"""
Repository Compliance Checker for GitHub Organizations
Automatically scans repositories and applies compliance labels

This script:
- Scans all repositories in the specified organization
- Checks compliance against defined rules
- Applies colored labels to non-compliant repositories
- Generates HTML dashboard and JSON report
- Creates issues in admin repository for tracking

Environment Variables:
- GITHUB_TOKEN: GitHub personal access token (required)
- TARGET_ORG: Organization to scan (default: finastra-demo)
- DRY_RUN: Set to 'true' for testing without applying changes

Usage:
    export GITHUB_TOKEN=ghp_xxxxx
    export TARGET_ORG=finastra-demo
    export DRY_RUN=true
    python scripts/compliance-checker.py
"""

import os
import json
import re
from datetime import datetime, timedelta
from github import Github

def main():
    """Main function to run compliance checking"""
    print("🚀 Repository Compliance Checker Starting...")
    
    # Initialize configuration
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        print("❌ Error: GITHUB_TOKEN environment variable is required")
        exit(1)
    
    org_name = os.environ.get('TARGET_ORG', 'finastra-demo')
    dry_run = os.environ.get('DRY_RUN', 'false').lower() == 'true'
    
    print(f"🔍 Scanning organization: {org_name}")
    print(f"🧪 Dry run mode: {dry_run}")
    
    try:
        # Initialize GitHub client
        g = Github(token)
        org = g.get_organization(org_name)
        
        # Define compliance rules based on organization
        compliance_rules = get_compliance_rules(org_name)
        print(f"📋 Compliance rules loaded for {org_name}")
        
        # Scan all repositories
        compliance_issues = []
        total_repos = 0
        
        print(f"📊 Starting repository scan...")
        
        for repo in org.get_repos():
            total_repos += 1
            print(f"📊 Checking ({total_repos}): {repo.name}")
            
            # Check repository compliance
            issues = check_repository_compliance(repo, compliance_rules)
            
            if issues['violations']:
                compliance_issues.append(issues)
                print(f"❌ Found {len(issues['violations'])} issues in {repo.name}")
                
                # Apply labels if not in dry run mode
                if not dry_run:
                    apply_compliance_labels(repo, issues['labels'])
                else:
                    print(f"🧪 Would apply labels: {', '.join(issues['labels'])}")
            else:
                print(f"✅ {repo.name} is compliant")
        
        print(f"\n📊 Repository scan completed")
        
        # Generate compliance report
        report = generate_compliance_report(org_name, compliance_issues, total_repos)
        print(f"📄 Generated JSON compliance report")
        
        # Create issues in admin repository if not dry run
        if not dry_run and compliance_issues:
            create_compliance_issues(g, org_name, compliance_issues, report)
        elif dry_run and compliance_issues:
            print(f"🧪 Would create {len(compliance_issues)} compliance issues in admin repo")
        
        # Generate HTML dashboard
        generate_html_dashboard(report)
        print(f"📊 Generated HTML dashboard")
        
        # Print summary
        print_summary(report)
        
    except Exception as e:
        print(f"❌ Error during compliance check: {e}")
        exit(1)

def get_compliance_rules(org_name):
    """Get compliance rules based on organization"""
    if org_name == 'finastra-demo':
        return {
            'required_prefix': 'FD-',
            'naming_pattern': r'^FD-[a-z0-9]+-[a-z0-9-]+$',
            'description': 'Finastra Demo organization rules'
        }
    elif org_name.lower() in ['arctiqteam', 'arctiq-team']:
        return {
            'required_prefixes': ['a-', 'e-', 't-', 'p-', 'action-', 'collab-'],
            'naming_pattern': r'^(a|e|t|p|action|collab)-[a-z0-9]+-[a-z0-9-]+$',
            'description': 'Arctiq Team organization rules'
        }
    else:
        # Generic rules for other organizations
        return {
            'required_prefixes': ['a-', 'e-', 't-', 'p-'],
            'naming_pattern': r'^[a-z]+-[a-z0-9]+-[a-z0-9-]+$',
            'description': 'Generic organization rules'
        }

def check_repository_compliance(repo, rules):
    """Check a single repository for compliance issues"""
    issues = {
        'name': repo.name,
        'url': repo.html_url,
        'visibility': 'private' if repo.private else 'public',
        'violations': [],
        'labels': [],
        'size': repo.size,
        'language': repo.language or 'Unknown',
        'last_push': repo.pushed_at.isoformat() if repo.pushed_at else None
    }
    
    # Check 1: Naming Convention
    check_naming_convention(repo, rules, issues)
    
    # Check 2: Required Files
    check_required_files(repo, issues)
    
    # Check 3: Branch Protection
    check_branch_protection(repo, issues)
    
    # Check 4: Repository Description
    check_repository_description(repo, issues)
    
    # Check 5: Activity Status
    check_activity_status(repo, issues)
    
    # Check 6: Repository Size
    check_repository_size(repo, issues)
    
    return issues

def check_naming_convention(repo, rules, issues):
    """Check repository naming convention"""
    try:
        if 'required_prefix' in rules:
            # Single prefix requirement (e.g., Finastra-demo)
            required_prefix = rules['required_prefix']
            if not repo.name.startswith(required_prefix):
                issues['violations'].append(f'Repository name must start with "{required_prefix}"')
                issues['labels'].append('naming:missing-prefix')
        elif 'required_prefixes' in rules:
            # Multiple prefix options (e.g., Arctiq)
            required_prefixes = rules['required_prefixes']
            if not any(repo.name.startswith(prefix) for prefix in required_prefixes):
                issues['violations'].append(f'Repository name must start with one of: {", ".join(required_prefixes)}')
                issues['labels'].append('naming:missing-prefix')
        
        # Check naming pattern if defined
        if 'naming_pattern' in rules:
            pattern = rules['naming_pattern']
            if not re.match(pattern, repo.name):
                issues['violations'].append('Repository name does not follow naming pattern')
                issues['labels'].append('naming:non-compliant')
                
    except Exception as e:
        print(f"⚠️ Error checking naming convention for {repo.name}: {e}")

def check_required_files(repo, issues):
    """Check for required files in repository"""
    try:
        # Check for README
        try:
            readme = repo.get_readme()
            readme_content = readme.decoded_content.decode('utf-8', errors='ignore')
            if len(readme_content) < 100:
                issues['violations'].append('README file is too short (< 100 characters)')
                issues['labels'].append('missing:readme')
        except Exception:
            issues['violations'].append('No README file found')
            issues['labels'].append('missing:readme')
        
        # Check for .gitignore
        try:
            repo.get_contents('.gitignore')
        except Exception:
            issues['violations'].append('No .gitignore file found')
            issues['labels'].append('missing:gitignore')
        
        # Check for LICENSE (public repos only)
        if not repo.private:
            try:
                repo.get_contents('LICENSE')
            except Exception:
                try:
                    repo.get_contents('LICENSE.md')
                except Exception:
                    try:
                        repo.get_contents('LICENSE.txt')
                    except Exception:
                        issues['violations'].append('No LICENSE file found (required for public repositories)')
                        issues['labels'].append('missing:license')
        
        # Check for CODEOWNERS
        try:
            repo.get_contents('CODEOWNERS')
        except Exception:
            try:
                repo.get_contents('.github/CODEOWNERS')
            except Exception:
                issues['violations'].append('No CODEOWNERS file found')
                issues['labels'].append('missing:codeowners')
                
    except Exception as e:
        print(f"⚠️ Error checking required files for {repo.name}: {e}")

def check_branch_protection(repo, issues):
    """Check branch protection settings"""
    try:
        if repo.default_branch:
            try:
                default_branch = repo.get_branch(repo.default_branch)
                if not default_branch.protected:
                    issues['violations'].append('Default branch has no protection rules')
                    issues['labels'].append('security:no-branch-protection')
                else:
                    # Check protection details
                    protection = default_branch.get_protection()
                    if not protection.required_status_checks:
                        issues['violations'].append('Branch protection lacks required status checks')
                        issues['labels'].append('security:insufficient-protection')
            except Exception as branch_error:
                print(f"⚠️ Error checking branch {repo.default_branch}: {branch_error}")
                
    except Exception as e:
        print(f"⚠️ Error checking branch protection for {repo.name}: {e}")

def check_repository_description(repo, issues):
    """Check repository description"""
    try:
        if not repo.description or len(repo.description.strip()) < 10:
            issues['violations'].append('Repository description missing or too short (< 10 characters)')
            issues['labels'].append('missing:description')
            
    except Exception as e:
        print(f"⚠️ Error checking description for {repo.name}: {e}")

def check_activity_status(repo, issues):
    """Check repository activity status"""
    try:
        if repo.pushed_at:
            # Calculate days since last push
            now = datetime.utcnow()
            pushed_at = repo.pushed_at
            
            # Handle timezone-aware datetime
            if hasattr(pushed_at, 'tzinfo') and pushed_at.tzinfo is not None:
                pushed_at = pushed_at.replace(tzinfo=None)
            
            days_since_push = (now - pushed_at).days
            
            if days_since_push > 365:
                issues['violations'].append(f'Repository inactive for {days_since_push} days (1+ years)')
                issues['labels'].append('activity:archived')
            elif days_since_push > 180:
                issues['violations'].append(f'Repository stale for {days_since_push} days (6+ months)')
                issues['labels'].append('activity:stale')
        else:
            issues['violations'].append('Repository has never been pushed to')
            issues['labels'].append('activity:never-used')
            
    except Exception as e:
        print(f"⚠️ Error checking activity for {repo.name}: {e}")

def check_repository_size(repo, issues):
    """Check repository size and content"""
    try:
        # Check repository size (in KB)
        if repo.size == 0:
            issues['violations'].append('Repository appears to be empty')
            issues['labels'].append('quality:empty')
        elif repo.size < 10:  # Less than 10KB
            issues['violations'].append('Repository has minimal content (< 10KB)')
            issues['labels'].append('quality:minimal')
            
    except Exception as e:
        print(f"⚠️ Error checking size for {repo.name}: {e}")

def apply_compliance_labels(repo, labels):
    """Apply compliance labels to repository"""
    if not labels:
        return
    
    # Define label colors
    label_colors = {
        'naming:missing-prefix': 'f66a0a',           # Orange
        'naming:non-compliant': 'f66a0a',            # Orange
        'missing:readme': 'd73a49',                  # Red
        'missing:gitignore': 'd73a49',               # Red
        'missing:license': 'fbca04',                 # Yellow
        'missing:codeowners': 'fbca04',              # Yellow
        'missing:description': 'fbca04',             # Yellow
        'security:no-branch-protection': 'd73a49',   # Red
        'security:insufficient-protection': 'f66a0a', # Orange
        'activity:stale': 'f66a0a',                  # Orange
        'activity:archived': '24292e',               # Black
        'activity:never-used': '6a737d',             # Gray
        'quality:empty': '6a737d',                   # Gray
        'quality:minimal': '6a737d',                 # Gray
    }
    
    for label_name in labels:
        try:
            # Check if label already exists in repository
            existing_labels = [label.name for label in repo.get_labels()]
            
            if label_name not in existing_labels:
                # Create label with appropriate color
                color = label_colors.get(label_name, '6a737d')  # Default gray
                description = f"Compliance issue: {label_name.replace(':', ' - ')}"
                
                repo.create_label(label_name, color, description)
                print(f"  ✅ Applied label: {label_name}")
            else:
                print(f"  ℹ️ Label already exists: {label_name}")
                
        except Exception as e:
            print(f"  ❌ Error applying label {label_name}: {e}")

def generate_compliance_report(org_name, issues, total_repos):
    """Generate comprehensive compliance report"""
    compliant_repos = total_repos - len(issues)
    compliance_rate = (compliant_repos / total_repos * 100) if total_repos > 0 else 100
    
    # Analyze issue types
    issue_categories = {}
    label_counts = {}
    
    for issue in issues:
        for violation in issue['violations']:
            category = violation.split()[0].lower()
            issue_categories[category] = issue_categories.get(category, 0) + 1
        
        for label in issue['labels']:
            label_counts[label] = label_counts.get(label, 0) + 1
    
    report = {
        'metadata': {
            'organization': org_name,
            'scan_date': datetime.utcnow().isoformat(),
            'generated_by': 'Repository Compliance Checker',
            'version': '1.0'
        },
        'summary': {
            'total_repositories': total_repos,
            'compliant_repositories': compliant_repos,
            'non_compliant_repositories': len(issues),
            'compliance_rate': round(compliance_rate, 1)
        },
        'analysis': {
            'issue_categories': issue_categories,
            'label_distribution': label_counts,
            'top_violations': sorted(issue_categories.items(), key=lambda x: x[1], reverse=True)[:5]
        },
        'repositories': issues
    }
    
    # Save JSON report
    with open('compliance-report.json', 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    return report

def create_compliance_issues(github_client, org_name, compliance_issues, report):
    """Create tracking issues in admin repository"""
    try:
        admin_repo = github_client.get_repo(f"{org_name}/admin-repo-compliance")
        
        # Create or update daily summary issue
        today = datetime.now().strftime('%Y-%m-%d')
        summary_title = f"📊 Repository Compliance Report - {today}"
        
        summary_body = generate_summary_issue_body(org_name, report)
        
        # Check for existing summary issue today
        existing_issues = list(admin_repo.get_issues(state='open', labels=['compliance-report']))
        today_issue = None
        
        for issue in existing_issues:
            if today in issue.title:
                today_issue = issue
                break
        
        if today_issue:
            today_issue.edit(body=summary_body)
            print(f"📝 Updated existing compliance report: #{today_issue.number}")
        else:
            new_issue = admin_repo.create_issue(
                title=summary_title,
                body=summary_body,
                labels=['compliance-report', 'automated', f'scan-{today}']
            )
            print(f"📋 Created compliance report issue: #{new_issue.number}")
        
        # Create individual high-priority issues
        create_high_priority_issues(admin_repo, compliance_issues)
        
    except Exception as e:
        print(f"❌ Error creating compliance issues: {e}")

def generate_summary_issue_body(org_name, report):
    """Generate issue body for summary report"""
    metadata = report['metadata']
    summary = report['summary']
    analysis = report['analysis']
    
    body = f"""# 📊 Repository Compliance Summary

**Organization:** {metadata['organization']}  
**Scan Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC  
**Compliance Rate:** {summary['compliance_rate']}%

## 📈 Overview

| Metric | Count | Percentage |
|--------|-------|------------|
| 📊 Total Repositories | {summary['total_repositories']} | 100% |
| ✅ Compliant | {summary['compliant_repositories']} | {(summary['compliant_repositories']/summary['total_repositories']*100):.1f}% |
| ❌ Non-Compliant | {summary['non_compliant_repositories']} | {(summary['non_compliant_repositories']/summary['total_repositories']*100):.1f}% |

## 🚨 Top Violation Types

"""
    
    for violation_type, count in analysis['top_violations']:
        percentage = (count / summary['non_compliant_repositories'] * 100) if summary['non_compliant_repositories'] > 0 else 0
        body += f"- **{violation_type.title()}**: {count} repositories ({percentage:.1f}%)\n"
    
    body += f"""

## 🏷️ Applied Labels

"""
    
    for label, count in sorted(analysis['label_distribution'].items()):
        body += f"- `{label}`: {count} repositories\n"
    
    body += f"""

## 📋 Non-Compliant Repositories

"""
    
    for repo in report['repositories']:
        body += f"### [{repo['name']}]({repo['url']})\n"
        body += f"**Visibility:** {repo['visibility']} | **Size:** {repo['size']}KB | **Language:** {repo['language']}\n\n"
        
        for violation in repo['violations']:
            body += f"- ❌ {violation}\n"
        
        body += f"**Labels Applied:** {', '.join([f'`{label}`' for label in repo['labels']])}\n\n"
    
    body += f"""

## 🎯 Recommended Actions

1. **High Priority:** Fix repositories with security issues (red labels)
2. **Medium Priority:** Address naming convention violations (orange labels)  
3. **Low Priority:** Improve documentation and add missing files (yellow labels)
4. **Maintenance:** Review archived/stale repositories for potential deletion

## 📊 Trend Analysis

*Historical compliance tracking will be available after multiple scans*

---
*This report was generated automatically by the Repository Compliance Checker*
*Next scan: Tomorrow at 02:00 UTC*
"""
    
    return body

def create_high_priority_issues(admin_repo, compliance_issues):
    """Create individual issues for high-priority violations"""
    high_priority_labels = [
        'missing:readme',
        'missing:gitignore', 
        'security:no-branch-protection',
        'naming:missing-prefix'
    ]
    
    for repo_issue in compliance_issues:
        repo_name = repo_issue['name']
        repo_url = repo_issue['url']
        labels = repo_issue['labels']
        
        # Check if this repository has high-priority issues
        has_high_priority = any(label in high_priority_labels for label in labels)
        
        if has_high_priority:
            issue_title = f"🚨 High Priority Compliance - {repo_name}"
            
            issue_body = f"""# 🚨 High Priority Compliance Issues

**Repository:** [{repo_name}]({repo_url})  
**Priority:** High  
**Visibility:** {repo_issue['visibility']}

## 🔍 Issues Found

"""
            
            for violation in repo_issue['violations']:
                priority = "🔴 CRITICAL" if any(label in ['missing:readme', 'security:no-branch-protection'] for label in labels) else "🟠 HIGH"
                issue_body += f"- {priority} {violation}\n"
            
            issue_body += f"""

## 🛠️ Fix Instructions

### For Naming Issues:
```bash
# If repository name needs FD- prefix:
gh repo rename {repo_name} FD-{repo_name}
```

### For Missing Files:
```bash
# Add README
echo "# {repo_name}" > README.md

# Add .gitignore
curl -o .gitignore https://raw.githubusercontent.com/github/gitignore/main/Global/JetBrains.gitignore

# Add CODEOWNERS  
echo "* @{repo_name.split('-')[0]}-team" > CODEOWNERS
```

### For Branch Protection:
1. Go to repository Settings → Branches
2. Add rule for default branch
3. Enable "Require pull request reviews before merging"

## 🏷️ Labels Applied
{', '.join([f'`{label}`' for label in labels])}

## ✅ Completion Checklist
- [ ] Fix naming convention
- [ ] Add missing files
- [ ] Enable branch protection
- [ ] Update repository description
- [ ] Re-run compliance check

---
*This issue will be automatically closed when compliance issues are resolved*
"""
            
            # Check if issue already exists for this repo
            existing_issues = list(admin_repo.get_issues(state='open', labels=['high-priority-compliance']))
            repo_issue_exists = False
            
            for existing_issue in existing_issues:
                if repo_name in existing_issue.title:
                    existing_issue.edit(body=issue_body)
                    print(f"📝 Updated high-priority issue for {repo_name}")
                    repo_issue_exists = True
                    break
            
            if not repo_issue_exists:
                new_issue = admin_repo.create_issue(
                    title=issue_title,
                    body=issue_body,
                    labels=['high-priority-compliance', 'automated', repo_name]
                )
                print(f"🚨 Created high-priority issue for {repo_name}: #{new_issue.number}")

def generate_html_dashboard(report):
    """Generate beautiful HTML compliance dashboard"""
    metadata = report['metadata']
    summary = report['summary']
    analysis = report['analysis']
    
    # Calculate additional metrics
    total_violations = sum(analysis['issue_categories'].values())
    critical_issues = sum(count for label, count in analysis['label_distribution'].items() 
                         if label.startswith(('missing:readme', 'security:')))
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Repository Compliance Dashboard - {metadata['organization']}</title>
    <style>
        :root {{
            --primary-color: #0366d6;
            --success-color: #28a745;
            --warning-color: #ffc107;
            --danger-color: #dc3545;
            --info-color: #17a2b8;
            --light-gray: #f8f9fa;
            --border-color: #e1e4e8;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--light-gray);
            color: #24292f;
            line-height: 1.6;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        .header {{
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 30px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5rem;
            margin-bottom: 10px;
            color: var(--primary-color);
        }}
        
        .header .subtitle {{
            color: #586069;
            font-size: 1.1rem;
        }}
        
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .metric-card {{
            background: white;
            padding: 25px;
            border-radius: 12px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
            border-left: 5px solid var(--primary-color);
        }}
        
        .metric-card.success {{ border-left-color: var(--success-color); }}
        .metric-card.danger {{ border-left-color: var(--danger-color); }}
        .metric-card.warning {{ border-left-color: var(--warning-color); }}
        
        .metric-card h3 {{
            font-size: 0.9rem;
            color: #586069;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .metric-card .value {{
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 5px;
        }}
        
        .metric-card .percentage {{
            font-size: 1.1rem;
            color: #586069;
        }}
        
        .success {{ color: var(--success-color); }}
        .danger {{ color: var(--danger-color); }}
        .warning {{ color: var(--warning-color); }}
        .primary {{ color: var(--primary-color); }}
        
        .charts-section {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 30px;
        }}
        
        .chart-card {{
            background: white;
            padding: 25px;
            border-radius: 12px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        
        .chart-card h3 {{
            margin-bottom: 20px;
            color: #24292f;
        }}
        
        .violation-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid var(--border-color);
        }}
        
        .violation-item:last-child {{
            border-bottom: none;
        }}
        
        .label-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 0;
        }}
        
        .label-badge {{
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 0.8rem;
            font-weight: 500;
            color: white;
        }}
        
        .repositories-section {{
            background: white;
            padding: 25px;
            border-radius: 12px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        
        .repository-card {{
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            background: #fafbfc;
        }}
        
        .repository-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}
        
        .repository-name {{
            font-size: 1.2rem;
            font-weight: 600;
        }}
        
        .repository-name a {{
            color: var(--primary-color);
            text-decoration: none;
        }}
        
        .repository-name a:hover {{
            text-decoration: underline;
        }}
        
        .repository-meta {{
            font-size: 0.9rem;
            color: #586069;
        }}
        
        .violations-list {{
            margin-top: 15px;
        }}
        
        .violation-badge {{
            display: inline-block;
            background: #fff5f5;
            color: #c53030;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.8rem;
            margin: 2px;
            border: 1px solid #fed7d7;
        }}
        
        .footer {{
            text-align: center;
            margin-top: 40px;
            padding: 20px;
            background: white;
            border-radius: 12px;
            color: #586069;
        }}
        
        @media (max-width: 768px) {{
            .charts-section {{
                grid-template-columns: 1fr;
            }}
            
            .metrics-grid {{
                grid-template-columns: 1fr;
            }}
            
            .header h1 {{
                font-size: 2rem;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏢 {metadata['organization']}</h1>
            <h2>Repository Compliance Dashboard</h2>
            <p class="subtitle">Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
        </div>
        
        <div class="metrics-grid">
            <div class="metric-card">
                <h3>📊 Total Repositories</h3>
                <div class="value primary">{summary['total_repositories']}</div>
            </div>
            
            <div class="metric-card success">
                <h3>✅ Compliant</h3>
                <div class="value success">{summary['compliant_repositories']}</div>
                <div class="percentage">({(summary['compliant_repositories']/summary['total_repositories']*100):.1f}%)</div>
            </div>
            
            <div class="metric-card danger">
                <h3>❌ Non-Compliant</h3>
                <div class="value danger">{summary['non_compliant_repositories']}</div>
                <div class="percentage">({(summary['non_compliant_repositories']/summary['total_repositories']*100):.1f}%)</div>
            </div>
            
            <div class="metric-card warning">
                <h3>🔥 Critical Issues</h3>
                <div class="value warning">{critical_issues}</div>
                <div class="percentage">Security & Core</div>
            </div>
        </div>
        
        <div class="charts-section">
            <div class="chart-card">
                <h3>🚨 Top Violation Types</h3>
"""
    
    for violation_type, count in analysis['top_violations']:
        percentage = (count / summary['non_compliant_repositories'] * 100) if summary['non_compliant_repositories'] > 0 else 0
        html_content += f"""
                <div class="violation-item">
                    <span>{violation_type.title()}</span>
                    <span><strong>{count}</strong> ({percentage:.1f}%)</span>
                </div>"""
    
    html_content += """
            </div>
            
            <div class="chart-card">
                <h3>🏷️ Applied Labels</h3>
"""
    
    label_colors = {
        'naming': '#f66a0a',
        'missing': '#d73a49', 
        'security': '#d73a49',
        'activity': '#24292e',
        'quality': '#6a737d'
    }
    
    for label, count in sorted(analysis['label_distribution'].items()):
        label_category = label.split(':')[0]
        color = label_colors.get(label_category, '#6a737d')
        
        html_content += f"""
                <div class="label-item">
                    <span class="label-badge" style="background-color: {color};">{label}</span>
                    <span><strong>{count}</strong></span>
                </div>"""
    
    html_content += """
            </div>
        </div>
"""
    
    if report['repositories']:
        html_content += """
        <div class="repositories-section">
            <h2>🚨 Non-Compliant Repositories</h2>
"""
        
        for repo in report['repositories']:
            html_content += f"""
            <div class="repository-card">
                <div class="repository-header">
                    <div class="repository-name">
                        <a href="{repo['url']}" target="_blank">{repo['name']}</a>
                    </div>
                    <div class="repository-meta">
                        {repo['visibility']} • {repo['size']}KB • {repo['language']}
                    </div>
                </div>
                <div class="violations-list">
"""
            
            for violation in repo['violations']:
                html_content += f'<span class="violation-badge">❌ {violation}</span>'
            
            html_content += """
                </div>
            </div>
"""
        
        html_content += "</div>"
    else:
        html_content += """
        <div class="repositories-section">
            <div style="text-align: center; padding: 40px; color: var(--success-color);">
                <h2>🎉 Congratulations!</h2>
                <p style="font-size: 1.2rem; margin-top: 10px;">All repositories are compliant with governance standards.</p>
            </div>
        </div>
"""
    
    html_content += f"""
        <div class="footer">
            <p><strong>Repository Compliance Checker v1.0</strong></p>
            <p>Generated automatically • Next scan: Tomorrow at 02:00 UTC</p>
            <p style="margin-top: 10px;">
                <a href="compliance-report.json" target="_blank">📄 Download JSON Report</a>
            </p>
        </div>
    </div>
</body>
</html>"""
    
    # Save HTML dashboard
    with open('compliance-dashboard.html', 'w', encoding='utf-8') as f:
        f.write(html_content)

def print_summary(report):
    """Print summary to console"""
    summary = report['summary']
    analysis = report['analysis']
    
    print(f"\n{'='*60}")
    print(f"📊 COMPLIANCE SUMMARY")
    print(f"{'='*60}")
    print(f"Organization: {report['metadata']['organization']}")
    print(f"Total Repositories: {summary['total_repositories']}")
    print(f"✅ Compliant: {summary['compliant_repositories']} ({(summary['compliant_repositories']/summary['total_repositories']*100):.1f}%)")
    print(f"❌ Non-Compliant: {summary['non_compliant_repositories']} ({(summary['non_compliant_repositories']/summary['total_repositories']*100):.1f}%)")
    print(f"📈 Compliance Rate: {summary['compliance_rate']}%")
    
    if analysis['top_violations']:
        print(f"\n🚨 TOP VIOLATIONS:")
        for violation_type, count in analysis['top_violations']:
            print(f"   • {violation_type.title()}: {count} repositories")
    
    if analysis['label_distribution']:
        print(f"\n🏷️ LABELS APPLIED:")
        for label, count in sorted(analysis['label_distribution'].items()):
            print(f"   • {label}: {count}")
    
    print(f"\n📄 Reports Generated:")
    print(f"   • compliance-report.json")
    print(f"   • compliance-dashboard.html")
    
    print(f"\n{'='*60}")

if __name__ == '__main__':
    main()