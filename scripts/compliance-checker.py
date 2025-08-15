#!/usr/bin/env python3
"""
Repository Compliance Checker for Finastra-demo Organization
Automatically scans repositories and applies compliance labels
"""

import os
import json
import re
from datetime import datetime, timedelta
from github import Github

def main():
    # Initialize
    token = os.environ['GITHUB_TOKEN']
    org_name = os.environ.get('TARGET_ORG', 'finastra-demo')
    dry_run = os.environ.get('DRY_RUN', 'false').lower() == 'true'
    
    print(f"🔍 Scanning organization: {org_name}")
    print(f"🧪 Dry run mode: {dry_run}")
    
    g = Github(token)
    org = g.get_organization(org_name)
    
    # Define compliance rules based on organization
    if org_name == 'finastra-demo':
        required_prefix = 'FD-'
        naming_pattern = r'^FD-[a-z0-9]+-[a-z0-9-]+$'
    else:
        # Default Arctiq rules
        required_prefixes = ['a-', 'e-', 't-', 'p-', 'action-', 'collab-']
        naming_pattern = r'^(a|e|t|p|action|collab)-[a-z0-9]+-[a-z0-9-]+$'
    
    compliance_issues = []
    
    # Scan all repositories
    for repo in org.get_repos():
        print(f"📊 Checking: {repo.name}")
        
        issues = check_repository_compliance(repo, org_name, required_prefix if org_name == 'finastra-demo' else required_prefixes)
        
        if issues['violations']:
            compliance_issues.append(issues)
            print(f"❌ Found {len(issues['violations'])} issues")
            
            # Apply labels (if not dry run)
            if not dry_run:
                apply_compliance_labels(repo, issues['labels'])
        else:
            print(f"✅ Compliant")
    
    # Generate reports
    report = generate_compliance_report(org_name, compliance_issues)
    
    # Create issues in admin repo (if not dry run)
    if not dry_run and compliance_issues:
        create_compliance_issues(g, org_name, compliance_issues)
    
    # Generate dashboard
    generate_html_dashboard(report)
    
    print(f"\n📊 SUMMARY")
    print(f"Total repos: {org.get_repos().totalCount}")
    print(f"Non-compliant: {len(compliance_issues)}")
    print(f"Compliance rate: {((org.get_repos().totalCount - len(compliance_issues)) / org.get_repos().totalCount * 100):.1f}%")

def check_repository_compliance(repo, org_name, required_prefix):
    """Check a single repository for compliance issues"""
    issues = {
        'name': repo.name,
        'url': repo.html_url,
        'visibility': 'private' if repo.private else 'public',
        'violations': [],
        'labels': []
    }
    
    # Check 1: Naming Convention
    if org_name == 'finastra-demo':
        if not repo.name.startswith(required_prefix):
            issues['violations'].append(f'Repository name must start with "{required_prefix}"')
            issues['labels'].append('naming:missing-prefix')
    else:
        # Arctiq naming rules
        if not any(repo.name.startswith(prefix) for prefix in required_prefix):
            issues['violations'].append(f'Repository name must start with one of: {required_prefix}')
            issues['labels'].append('naming:missing-prefix')
    
    # Check 2: Required Files
    try:
        # README check
        try:
            readme = repo.get_readme()
            if len(readme.decoded_content.decode('utf-8', errors='ignore')) < 100:
                issues['violations'].append('README file is too short (< 100 characters)')
                issues['labels'].append('missing:readme')
        except:
            issues['violations'].append('No README file found')
            issues['labels'].append('missing:readme')
        
        # .gitignore check
        try:
            repo.get_contents('.gitignore')
        except:
            issues['violations'].append('No .gitignore file found')
            issues['labels'].append('missing:gitignore')
        
        # LICENSE check (public repos only)
        if not repo.private:
            try:
                repo.get_contents('LICENSE')
            except:
                issues['violations'].append('No LICENSE file found (required for public repositories)')
                issues['labels'].append('missing:license')
        
        # CODEOWNERS check
        try:
            repo.get_contents('CODEOWNERS')
        except:
            try:
                repo.get_contents('.github/CODEOWNERS')
            except:
                issues['violations'].append('No CODEOWNERS file found')
                issues['labels'].append('missing:codeowners')
    
    except Exception as e:
        print(f"⚠️ Error checking files for {repo.name}: {e}")
    
    # Check 3: Branch Protection
    try:
        default_branch = repo.get_branch(repo.default_branch)
        if not default_branch.protected:
            issues['violations'].append('Default branch has no protection rules')
            issues['labels'].append('security:no-branch-protection')
    except Exception as e:
        print(f"⚠️ Error checking branch protection: {e}")
    
    # Check 4: Repository Description
    if not repo.description or len(repo.description.strip()) < 10:
        issues['violations'].append('Repository description missing or too short')
        issues['labels'].append('missing:description')
    
    # Check 5: Activity Status
    if repo.pushed_at:
        now_utc = datetime.now(timezone.utc)
        pushed_at_utc = repo.pushed_at
        if pushed_at_utc.tzinfo is None:
            pushed_at_utc = pushed_at_utc.replace(tzinfo=timezone.utc)
        days_since_push = (now_utc - pushed_at_utc).days
        if days_since_push > 365:
            issues['violations'].append(f'Repository inactive for {days_since_push} days (1+ years)')
            issues['labels'].append('activity:archived')
        elif days_since_push > 180:
            issues['violations'].append(f'Repository stale for {days_since_push} days (6+ months)')
            issues['labels'].append('activity:stale')
    
    return issues

def apply_compliance_labels(repo, labels):
    """Apply compliance labels to repository"""
    label_colors = {
        'naming:missing-prefix': 'f66a0a',       # Orange
        'missing:readme': 'd73a49',              # Red
        'missing:gitignore': 'd73a49',           # Red
        'missing:license': 'fbca04',             # Yellow
        'missing:codeowners': 'fbca04',          # Yellow
        'missing:description': 'fbca04',         # Yellow
        'security:no-branch-protection': 'd73a49', # Red
        'activity:stale': 'f66a0a',              # Orange
        'activity:archived': '24292e',           # Black
    }
    
    for label_name in labels:
        try:
            # Check if label exists in repo
            repo_labels = [label.name for label in repo.get_labels()]
            
            if label_name not in repo_labels:
                # Create label
                color = label_colors.get(label_name, '6a737d')
                repo.create_label(label_name, color, f"Compliance: {label_name}")
                print(f"  ✅ Applied label: {label_name}")
        except Exception as e:
            print(f"  ❌ Error applying label {label_name}: {e}")

def generate_compliance_report(org_name, issues):
    """Generate compliance report"""
    report = {
        'organization': org_name,
        'scan_date': datetime.now().isoformat(),
        'total_issues': len(issues),
        'issues': issues
    }
    
    # Save JSON report
    with open('compliance-report.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    return report

def create_compliance_issues(github_client, org_name, compliance_issues):
    """Create issues in admin repository"""
    try:
        admin_repo = github_client.get_repo(f"{org_name}/admin-repo-compliance")
        
        # Create summary issue
        today = datetime.now().strftime('%Y-%m-%d')
        title = f"Repository Compliance Report - {today}"
        
        body = f"""# Repository Compliance Summary
        
**Organization:** {org_name}
**Scan Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC
**Non-Compliant Repositories:** {len(compliance_issues)}

## 🚨 Issues Found

"""
        
        for issue in compliance_issues:
            body += f"### [{issue['name']}]({issue['url']})\n"
            for violation in issue['violations']:
                body += f"- ❌ {violation}\n"
            body += "\n"
        
        body += """
---
*This report was generated automatically by the Repository Compliance Checker*
"""
        
        # Create or update issue
        admin_repo.create_issue(
            title=title,
            body=body,
            labels=['compliance-report', 'automated']
        )
        print(f"📋 Created compliance report issue")
        
    except Exception as e:
        print(f"❌ Error creating issues: {e}")

def generate_html_dashboard(report):
    """Generate HTML compliance dashboard"""
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Repository Compliance Dashboard</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f6f8fa; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .metrics {{ display: flex; justify-content: space-around; margin: 20px 0; }}
        .metric {{ text-align: center; padding: 20px; background: #f6f8fa; border-radius: 8px; min-width: 150px; }}
        .metric h3 {{ margin: 0; color: #586069; }}
        .metric h2 {{ margin: 10px 0 0 0; font-size: 2em; }}
        .compliant {{ color: #28a745; }}
        .non-compliant {{ color: #d73a49; }}
        .repository {{ background: #f6f8fa; margin: 10px 0; padding: 15px; border-radius: 6px; }}
        .violation {{ color: #d73a49; margin: 5px 0; }}
        .timestamp {{ color: #586069; font-size: 0.9em; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏢 {report['organization']} - Repository Compliance Dashboard</h1>
            <p class="timestamp">Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
        </div>
        
        <div class="metrics">
            <div class="metric">
                <h3>🚨 Non-Compliant</h3>
                <h2 class="non-compliant">{report['total_issues']}</h2>
            </div>
        </div>
        
        <h2>🚨 Non-Compliant Repositories</h2>
"""
    
    if report['issues']:
        for issue in report['issues']:
            html += f"""
        <div class="repository">
            <h3><a href="{issue['url']}" target="_blank">{issue['name']}</a></h3>
            <p><strong>Visibility:</strong> {issue['visibility']}</p>
"""
            for violation in issue['violations']:
                html += f'<div class="violation">❌ {violation}</div>'
            
            html += "</div>"
    else:
        html += "<p>🎉 All repositories are compliant!</p>"
    
    html += """
    </div>
</body>
</html>"""
    
    with open('compliance-dashboard.html', 'w') as f:
        f.write(html)
    
    print("📊 Generated HTML dashboard")

if __name__ == '__main__':
    main()
