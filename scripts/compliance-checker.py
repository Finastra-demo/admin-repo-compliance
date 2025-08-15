#!/usr/bin/env python3
"""
Repository Compliance Checker for GitHub Organizations - Complete Version
Automatically scans repositories and applies compliance labels

This script:
- Scans ALL repositories in the specified organization (with pagination)
- Checks compliance against defined rules
- Applies colored labels to non-compliant repositories
- Generates HTML dashboard and JSON report
- Creates issues in admin repository for tracking
- Handles all edge cases and provides detailed debugging

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
import time
from datetime import datetime, timedelta
from github import Github
from github.GithubException import GithubException

def main():
    """Main function to run compliance checking"""
    print("🚀 Repository Compliance Checker Starting...")
    print(f"📅 Scan Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    
    # Initialize configuration
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        print("❌ Error: GITHUB_TOKEN environment variable is required")
        print("💡 Set it with: export GITHUB_TOKEN=ghp_your_token_here")
        exit(1)
    
    org_name = os.environ.get('TARGET_ORG', 'finastra-demo')
    dry_run = os.environ.get('DRY_RUN', 'false').lower() == 'true'
    
    print(f"🔍 Scanning organization: {org_name}")
    print(f"🧪 Dry run mode: {dry_run}")
    print(f"🔑 Token length: {len(token)} characters")
    
    try:
        # Initialize GitHub client
        g = Github(token)
        
        # Test GitHub API access first
        try:
            rate_limit = g.get_rate_limit()
            print(f"📊 GitHub API rate limit: {rate_limit.core.remaining}/{rate_limit.core.limit}")
        except Exception as e:
            print(f"⚠️ Could not check rate limit: {e}")
        
        # Get organization
        try:
            org = g.get_organization(org_name)
            print(f"🏢 Organization: {org.login}")
            print(f"📊 Public repos: {org.public_repos}")
            
            # Get additional org info
            try:
                total_private_repos = org.total_private_repos
                print(f"🔒 Private repos: {total_private_repos}")
                print(f"📊 Total repos (public + private): {org.public_repos + total_private_repos}")
            except:
                print(f"🔒 Private repo count: Not accessible")
                
        except Exception as e:
            print(f"❌ Error accessing organization '{org_name}': {e}")
            print(f"💡 Check if:")
            print(f"   • Organization name is correct")
            print(f"   • Your token has access to this organization")
            print(f"   • You are a member of the organization")
            exit(1)
        
        # Define compliance rules
        compliance_rules = get_compliance_rules(org_name)
        print(f"📋 Compliance rules loaded for {org_name}")
        print(f"🎯 Rules: {compliance_rules['description']}")
        
        # Get all repositories with improved pagination
        print(f"📊 Starting repository discovery...")
        repositories = get_all_repositories_with_pagination(g, org, org_name)
        
        if not repositories:
            print(f"❌ No repositories found!")
            print(f"🔍 Troubleshooting suggestions:")
            print(f"   • Check token permissions (repo, metadata)")
            print(f"   • Verify organization membership")
            print(f"   • Try with a personal access token")
            exit(1)
        
        total_repos = len(repositories)
        print(f"✅ Successfully discovered {total_repos} repositories")
        
        # Scan all repositories
        compliance_issues = []
        successful_scans = 0
        failed_scans = 0
        
        print(f"📊 Starting repository compliance scan...")
        print(f"{'='*60}")
        
        for i, repo in enumerate(repositories, 1):
            try:
                print(f"📊 Checking ({i}/{total_repos}): {repo.name}")
                
                # Check repository compliance
                issues = check_repository_compliance(repo, compliance_rules)
                
                if issues['violations']:
                    compliance_issues.append(issues)
                    print(f"❌ Found {len(issues['violations'])} issues in {repo.name}")
                    
                    # Apply labels if not in dry run mode
                    if not dry_run:
                        success_count = apply_compliance_labels(repo, issues['labels'])
                        if success_count > 0:
                            print(f"  ✅ Applied {success_count}/{len(issues['labels'])} labels")
                    else:
                        print(f"🧪 Would apply labels: {', '.join(issues['labels'])}")
                else:
                    print(f"✅ {repo.name} is compliant")
                
                successful_scans += 1
                
                # Small delay to be respectful to GitHub API
                if i % 10 == 0:
                    time.sleep(1)
                    
            except Exception as e:
                print(f"❌ Error scanning {repo.name}: {e}")
                failed_scans += 1
                continue
        
        print(f"{'='*60}")
        print(f"📊 Repository scan completed")
        print(f"✅ Successful scans: {successful_scans}")
        print(f"❌ Failed scans: {failed_scans}")
        
        # Generate compliance report
        report = generate_compliance_report(org_name, compliance_issues, total_repos)
        print(f"📄 Generated JSON compliance report")
        
        # Create issues in admin repository if not dry run
        if not dry_run and compliance_issues:
            try:
                create_compliance_issues(g, org_name, compliance_issues, report)
                print(f"📋 Created compliance tracking issues")
            except Exception as e:
                print(f"❌ Error creating issues: {e}")
        elif dry_run and compliance_issues:
            print(f"🧪 Would create {len(compliance_issues)} compliance issues in admin repo")
        
        # Generate HTML dashboard
        generate_html_dashboard(report)
        print(f"📊 Generated HTML dashboard")
        
        # Print summary
        print_summary(report)
        
        # Final recommendations
        print_recommendations(report, dry_run)
        
    except Exception as e:
        print(f"❌ Fatal error during compliance check: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

def get_all_repositories_with_pagination(github_client, org, org_name):
    """Get all repositories with proper pagination handling"""
    print(f"🔍 Fetching all repositories from {org_name}...")
    
    repositories = []
    
    # Try different methods to get repositories
    methods = [
        ("Primary method (org.get_repos)", lambda: list(org.get_repos(type='all', sort='updated'))),
        ("Public repos only", lambda: list(org.get_repos(type='public', sort='updated'))),
        ("Member repos", lambda: list(org.get_repos(type='member', sort='updated'))),
        ("Direct API method", lambda: get_repos_via_api(github_client, org_name))
    ]
    
    for method_name, method_func in methods:
        try:
            print(f"🔄 Trying {method_name}...")
            repos = method_func()
            if repos:
                repositories = repos
                print(f"✅ {method_name} successful: {len(repos)} repositories")
                break
            else:
                print(f"⚠️ {method_name} returned 0 repositories")
        except Exception as e:
            print(f"❌ {method_name} failed: {e}")
            continue
    
    # If still no repositories, try to debug the issue
    if not repositories:
        print(f"🔍 Debugging repository access...")
        debug_repository_access(github_client, org_name)
    
    return repositories

def get_repos_via_api(github_client, org_name):
    """Get repositories using direct API calls with pagination"""
    repositories = []
    page = 1
    per_page = 100
    
    while True:
        try:
            # Use the low-level API for better control
            headers, data = github_client._Github__requester.requestJsonAndCheck(
                "GET", 
                f"/orgs/{org_name}/repos",
                parameters={
                    'type': 'all',
                    'sort': 'updated', 
                    'direction': 'desc',
                    'per_page': per_page,
                    'page': page
                }
            )
            
            if not data:
                break
                
            print(f"📄 API Page {page}: {len(data)} repositories")
            
            # Convert to Repository objects
            for repo_data in data:
                try:
                    repo = github_client.get_repo(repo_data['full_name'])
                    repositories.append(repo)
                except Exception as e:
                    print(f"⚠️ Could not access repo {repo_data['name']}: {e}")
                    continue
            
            # If we got fewer than per_page results, we're done
            if len(data) < per_page:
                break
                
            page += 1
            
            # Safety check to prevent infinite loops
            if page > 20:  # Max 2000 repositories
                print(f"⚠️ Reached maximum page limit, stopping at page {page}")
                break
                
        except Exception as e:
            print(f"❌ API error on page {page}: {e}")
            break
    
    return repositories

def debug_repository_access(github_client, org_name):
    """Debug repository access issues"""
    try:
        # Check user info
        user = github_client.get_user()
        print(f"👤 Authenticated as: {user.login}")
        
        # Check organization membership
        try:
            orgs = list(user.get_orgs())
            org_names = [org.login for org in orgs]
            print(f"🏢 User organizations: {org_names}")
            
            if org_name not in org_names:
                print(f"⚠️ User is not a member of {org_name}")
                print(f"💡 You may only have access to specific repositories")
        except Exception as e:
            print(f"⚠️ Could not check organizations: {e}")
        
        # Try to get repositories the user has access to
        try:
            user_repos = list(user.get_repos(affiliation='organization_member'))
            org_repos = [repo for repo in user_repos if repo.organization and repo.organization.login == org_name]
            print(f"📊 Accessible repos in {org_name}: {len(org_repos)}")
            
            if org_repos:
                print(f"📋 Accessible repositories:")
                for repo in org_repos[:10]:  # Show first 10
                    print(f"   • {repo.name} ({repo.visibility})")
                if len(org_repos) > 10:
                    print(f"   ... and {len(org_repos) - 10} more")
                    
        except Exception as e:
            print(f"⚠️ Could not check user repositories: {e}")
            
    except Exception as e:
        print(f"❌ Debug failed: {e}")

def get_compliance_rules(org_name):
    """Get compliance rules based on organization"""
    if org_name == 'finastra-demo':
        return {
            'required_prefix': 'FD-',
            'naming_pattern': r'^FD-[a-z0-9]+-[a-z0-9-]+$',
            'description': 'Finastra Demo organization rules - all repos must start with FD-'
        }
    elif org_name.lower() in ['arctiqteam', 'arctiq-team']:
        return {
            'required_prefixes': ['a-', 'e-', 't-', 'p-', 'action-', 'collab-'],
            'naming_pattern': r'^(a|e|t|p|action|collab)-[a-z0-9]+-[a-z0-9-]+$',
            'description': 'Arctiq Team organization rules - prefixed naming convention'
        }
    else:
        # Generic rules for other organizations
        return {
            'required_prefixes': ['a-', 'e-', 't-', 'p-'],
            'naming_pattern': r'^[a-z]+-[a-z0-9]+-[a-z0-9-]+$',
            'description': 'Generic organization rules - standard prefixed naming'
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
        'last_push': repo.pushed_at.isoformat() if repo.pushed_at else None,
        'created_at': repo.created_at.isoformat() if repo.created_at else None,
        'default_branch': repo.default_branch,
        'archived': repo.archived
    }
    
    # Skip archived repositories
    if repo.archived:
        print(f"  ℹ️ Skipping archived repository: {repo.name}")
        return issues
    
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
    
    # Check 6: Repository Size and Quality
    check_repository_quality(repo, issues)
    
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
            if not re.match(pattern, repo.name, re.IGNORECASE):
                issues['violations'].append('Repository name does not follow naming pattern')
                issues['labels'].append('naming:non-compliant')
                
    except Exception as e:
        print(f"⚠️ Error checking naming for {repo.name}: {e}")

def check_required_files(repo, issues):
    """Check for required files in repository"""
    try:
        # Check for README
        readme_found = False
        readme_files = ['README.md', 'README.rst', 'README.txt', 'readme.md', 'Readme.md']
        
        for readme_name in readme_files:
            try:
                readme = repo.get_contents(readme_name)
                readme_content = readme.decoded_content.decode('utf-8', errors='ignore')
                if len(readme_content) >= 100:
                    readme_found = True
                    break
                else:
                    issues['violations'].append(f'{readme_name} file is too short (< 100 characters)')
                    issues['labels'].append('missing:readme')
                    break
            except:
                continue
        
        if not readme_found and not any(label.startswith('missing:readme') for label in issues['labels']):
            issues['violations'].append('No README file found')
            issues['labels'].append('missing:readme')
        
        # Check for .gitignore
        try:
            repo.get_contents('.gitignore')
        except:
            issues['violations'].append('No .gitignore file found')
            issues['labels'].append('missing:gitignore')
        
        # Check for LICENSE (public repos only)
        if not repo.private:
            license_found = False
            license_files = ['LICENSE', 'LICENSE.md', 'LICENSE.txt', 'license', 'License']
            
            for license_name in license_files:
                try:
                    repo.get_contents(license_name)
                    license_found = True
                    break
                except:
                    continue
            
            if not license_found:
                issues['violations'].append('No LICENSE file found (required for public repositories)')
                issues['labels'].append('missing:license')
        
        # Check for CODEOWNERS
        codeowners_found = False
        codeowners_locations = ['CODEOWNERS', '.github/CODEOWNERS', 'docs/CODEOWNERS']
        
        for location in codeowners_locations:
            try:
                repo.get_contents(location)
                codeowners_found = True
                break
            except:
                continue
        
        if not codeowners_found:
            issues['violations'].append('No CODEOWNERS file found')
            issues['labels'].append('missing:codeowners')
                
    except Exception as e:
        print(f"⚠️ Error checking files for {repo.name}: {e}")

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
                    # Check protection details if accessible
                    try:
                        protection = default_branch.get_protection()
                        if not protection.required_status_checks:
                            issues['violations'].append('Branch protection lacks required status checks')
                            issues['labels'].append('security:insufficient-protection')
                    except:
                        # Protection exists but details not accessible
                        pass
            except Exception:
                issues['violations'].append(f'Cannot access default branch: {repo.default_branch}')
                issues['labels'].append('security:branch-access-error')
                
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
            # Calculate days since last push using UTC
            now = datetime.utcnow()
            pushed_at = repo.pushed_at
            
            # Handle timezone-aware datetime by converting to naive UTC
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

def check_repository_quality(repo, issues):
    """Check repository size and content quality"""
    try:
        # Check repository size (in KB)
        if repo.size == 0:
            issues['violations'].append('Repository appears to be empty')
            issues['labels'].append('quality:empty')
        elif repo.size < 10:  # Less than 10KB
            issues['violations'].append('Repository has minimal content (< 10KB)')
            issues['labels'].append('quality:minimal')
            
        # Check if repository has topics (for discoverability)
        try:
            topics = repo.get_topics()
            if len(topics) == 0:
                issues['violations'].append('Repository has no topics for discoverability')
                issues['labels'].append('missing:topics')
        except:
            pass  # Topics API might not be accessible
            
    except Exception as e:
        print(f"⚠️ Error checking quality for {repo.name}: {e}")

def apply_compliance_labels(repo, labels):
    """Apply compliance labels to repository"""
    if not labels:
        return 0
    
    # Define label colors
    label_colors = {
        'naming:missing-prefix': 'f66a0a',           # Orange
        'naming:non-compliant': 'f66a0a',            # Orange
        'missing:readme': 'd73a49',                  # Red
        'missing:gitignore': 'd73a49',               # Red
        'missing:license': 'fbca04',                 # Yellow
        'missing:codeowners': 'fbca04',              # Yellow
        'missing:description': 'fbca04',             # Yellow
        'missing:topics': 'fbca04',                  # Yellow
        'security:no-branch-protection': 'd73a49',   # Red
        'security:insufficient-protection': 'f66a0a', # Orange
        'security:branch-access-error': '6a737d',    # Gray
        'activity:stale': 'f66a0a',                  # Orange
        'activity:archived': '24292e',               # Black
        'activity:never-used': '6a737d',             # Gray
        'quality:empty': '6a737d',                   # Gray
        'quality:minimal': '6a737d',                 # Gray
    }
    
    success_count = 0
    
    for label_name in labels:
        try:
            # Check if label already exists in repository
            existing_labels = [label.name for label in repo.get_labels()]
            
            if label_name not in existing_labels:
                # Create label with appropriate color
                color = label_colors.get(label_name, '6a737d')  # Default gray
                description = f"Compliance issue: {label_name.replace(':', ' - ')}"
                
                repo.create_label(label_name, color, description)
                success_count += 1
                print(f"  ✅ Applied label: {label_name}")
            else:
                success_count += 1
                print(f"  ℹ️ Label already exists: {label_name}")
                
        except Exception as e:
            print(f"  ❌ Error applying label {label_name}: {e}")
    
    return success_count

def generate_compliance_report(org_name, issues, total_repos):
    """Generate comprehensive compliance report"""
    compliant_repos = total_repos - len(issues)
    compliance_rate = (compliant_repos / total_repos * 100) if total_repos > 0 else 100
    
    # Analyze issue types
    issue_categories = {}
    label_counts = {}
    
    for issue in issues:
        for violation in issue['violations']:
            # Categorize by first word of violation
            category = violation.split()[0].lower()
            issue_categories[category] = issue_categories.get(category, 0) + 1
        
        for label in issue['labels']:
            label_counts[label] = label_counts.get(label, 0) + 1
    
    # Analyze by repository characteristics
    repo_analysis = {
        'by_visibility': {'public': 0, 'private': 0},
        'by_language': {},
        'by_size': {'empty': 0, 'small': 0, 'medium': 0, 'large': 0}
    }
    
    for issue in issues:
        # Count by visibility
        repo_analysis['by_visibility'][issue['visibility']] += 1
        
        # Count by language
        lang = issue['language']
        repo_analysis['by_language'][lang] = repo_analysis['by_language'].get(lang, 0) + 1
        
        # Count by size
        size = issue['size']
        if size == 0:
            repo_analysis['by_size']['empty'] += 1
        elif size < 100:
            repo_analysis['by_size']['small'] += 1
        elif size < 1000:
            repo_analysis['by_size']['medium'] += 1
        else:
            repo_analysis['by_size']['large'] += 1
    
    report = {
        'metadata': {
            'organization': org_name,
            'scan_date': datetime.utcnow().isoformat(),
            'generated_by': 'Repository Compliance Checker v2.0',
            'total_repositories_scanned': total_repos
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
            'repository_analysis': repo_analysis,
            'top_violations': sorted(issue_categories.items(), key=lambda x: x[1], reverse=True)[:10]
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
            # Create labels if they don't exist
            ensure_admin_labels_exist(admin_repo)
            
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
        raise

def ensure_admin_labels_exist(admin_repo):
    """Ensure required labels exist in admin repository"""
    required_labels = {
        'compliance-report': 'e1e4e8',
        'automated': '0366d6',
        'high-priority-compliance': 'd73a49'
    }
    
    existing_labels = [label.name for label in admin_repo.get_labels()]
    
    for label_name, color in required_labels.items():
        if label_name not in existing_labels:
            try:
                admin_repo.create_label(label_name, color, f"Automated compliance tracking: {label_name}")
            except:
                pass  # Label might already exist

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
        body += f"- **{violation_type.title()}**: {count} occurrences ({percentage:.1f}%)\n"
    
    body += f"""

## 🏷️ Applied Labels

"""
    
    for label, count in sorted(analysis['label_distribution'].items()):
        body += f"- `{label}`: {count} repositories\n"
    
    body += f"""

## 📊 Repository Analysis

### By Visibility
- **Public:** {analysis['repository_analysis']['by_visibility']['public']} repositories
- **Private:** {analysis['repository_analysis']['by_visibility']['private']} repositories

### By Language
"""
    
    for lang, count in sorted(analysis['repository_analysis']['by_language'].items(), key=lambda x: x[1], reverse=True)[:5]:
        body += f"- **{lang}:** {count} repositories\n"
    
    body += f"""

## 📋 Non-Compliant Repositories Summary

"""
    
    for repo in report['repositories'][:10]:  # Show first 10
        body += f"### [{repo['name']}]({repo['url']})\n"
        body += f"**Visibility:** {repo['visibility']} | **Size:** {repo['size']}KB | **Language:** {repo['language']}\n"
        
        violation_count = len(repo['violations'])
        body += f"**Issues:** {violation_count} violations\n"
        
        # Show first 3 violations
        for violation in repo['violations'][:3]:
            body += f"- ❌ {violation}\n"
        
        if violation_count > 3:
            body += f"- ... and {violation_count - 3} more issues\n"
        
        body += "\n"
    
    if len(report['repositories']) > 10:
        body += f"*... and {len(report['repositories']) - 10} more non-compliant repositories*\n\n"
    
    body += f"""

## 🎯 Recommended Actions

### 🔴 Critical (Immediate Action Required)
- Fix repositories with `security:no-branch-protection` labels
- Add README files to repositories with `missing:readme` labels

### 🟠 High Priority (This Week)
- Address naming convention violations (`naming:missing-prefix`)
- Review and archive stale repositories (`activity:stale`)

### 🟡 Medium Priority (This Month)  
- Add missing files (.gitignore, CODEOWNERS, LICENSE)
- Improve repository descriptions

## 📊 Dashboard
View the full compliance dashboard at: https://{org_name}.github.io/admin-repo-compliance

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
    
    created_count = 0
    updated_count = 0
    
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
**Last Updated:** {repo_issue['last_push'] or 'Never'}

## 🔍 Issues Found

"""
            
            critical_count = 0
            for i, violation in enumerate(repo_issue['violations'], 1):
                label = labels[min(i-1, len(labels)-1)] if labels else ""
                if label in ['missing:readme', 'security:no-branch-protection']:
                    priority_icon = "🔴 CRITICAL"
                    critical_count += 1
                elif label in high_priority_labels:
                    priority_icon = "🟠 HIGH"
                else:
                    priority_icon = "🟡 MEDIUM"
                
                issue_body += f"{i}. {priority_icon} {violation}\n"
            
            issue_body += f"""

## 🛠️ Fix Instructions

### Quick Fixes
```bash
# Clone the repository
git clone {repo_url}
cd {repo_name}
```

"""
            
            if 'naming:missing-prefix' in labels:
                org_prefix = "FD-" if "finastra" in repo_url.lower() else "t-"
                issue_body += f"""
#### Fix Naming Convention
```bash
# Rename repository to include required prefix
gh repo rename {repo_name} {org_prefix}{repo_name}
```
"""
            
            if 'missing:readme' in labels:
                issue_body += f"""
#### Add README
```bash
cat > README.md << 'EOF'
# {repo_name}

## Description
Brief description of this repository's purpose.

## Usage
Instructions for using this repository.

## Contributing
Guidelines for contributing to this project.
EOF

git add README.md
git commit -m "Add README file for compliance"
```
"""
            
            if 'missing:gitignore' in labels:
                issue_body += f"""
#### Add .gitignore
```bash
# Create appropriate .gitignore for your technology stack
curl -o .gitignore https://raw.githubusercontent.com/github/gitignore/main/Global/VisualStudioCode.gitignore

git add .gitignore
git commit -m "Add .gitignore file for compliance"
```
"""
            
            if 'security:no-branch-protection' in labels:
                issue_body += f"""
#### Enable Branch Protection
1. Go to repository Settings → Branches
2. Click "Add rule" for the default branch
3. Enable:
   - ✅ Require pull request reviews before merging
   - ✅ Require status checks to pass before merging
   - ✅ Restrict pushes that create files larger than 100MB
"""
            
            issue_body += f"""

## ✅ Completion Checklist
"""
            
            for violation in repo_issue['violations']:
                issue_body += f"- [ ] {violation}\n"
            
            issue_body += f"""

## 🏷️ Applied Labels
{', '.join([f'`{label}`' for label in labels])}

## 🔄 Re-run Compliance Check
After making fixes, the compliance checker will automatically re-run tomorrow, or you can trigger it manually from the Actions tab.

---
*This issue will be automatically updated when compliance status changes*
"""
            
            # Check if issue already exists for this repo
            existing_issues = list(admin_repo.get_issues(state='open', labels=['high-priority-compliance']))
            repo_issue_exists = False
            
            for existing_issue in existing_issues:
                if repo_name in existing_issue.title:
                    existing_issue.edit(body=issue_body)
                    print(f"📝 Updated high-priority issue for {repo_name}")
                    updated_count += 1
                    repo_issue_exists = True
                    break
            
            if not repo_issue_exists:
                try:
                    new_issue = admin_repo.create_issue(
                        title=issue_title,
                        body=issue_body,
                        labels=['high-priority-compliance', 'automated', repo_name]
                    )
                    print(f"🚨 Created high-priority issue for {repo_name}: #{new_issue.number}")
                    created_count += 1
                except Exception as e:
                    print(f"❌ Failed to create issue for {repo_name}: {e}")
    
    if created_count > 0:
        print(f"📋 Created {created_count} new high-priority issues")
    if updated_count > 0:
        print(f"📝 Updated {updated_count} existing high-priority issues")

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
            --text-color: #24292f;
            --muted-color: #586069;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--light-gray);
            color: var(--text-color);
            line-height: 1.6;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        .header {{
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            margin-bottom: 30px;
            text-align: center;
            border-left: 6px solid var(--primary-color);
        }}
        
        .header h1 {{
            font-size: 2.5rem;
            margin-bottom: 10px;
            color: var(--primary-color);
            font-weight: 700;
        }}
        
        .header .subtitle {{
            color: var(--muted-color);
            font-size: 1.1rem;
            margin-bottom: 15px;
        }}
        
        .status-badge {{
            display: inline-block;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 1rem;
        }}
        
        .status-excellent {{ background: #d4edda; color: #155724; }}
        .status-good {{ background: #d1ecf1; color: #0c5460; }}
        .status-needs-improvement {{ background: #fff3cd; color: #856404; }}
        .status-critical {{ background: #f8d7da; color: #721c24; }}
        
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 25px;
            margin-bottom: 40px;
        }}
        
        .metric-card {{
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            text-align: center;
            border-left: 6px solid var(--primary-color);
            transition: transform 0.2s ease;
        }}
        
        .metric-card:hover {{
            transform: translateY(-2px);
        }}
        
        .metric-card.success {{ border-left-color: var(--success-color); }}
        .metric-card.danger {{ border-left-color: var(--danger-color); }}
        .metric-card.warning {{ border-left-color: var(--warning-color); }}
        
        .metric-card h3 {{
            font-size: 0.9rem;
            color: var(--muted-color);
            margin-bottom: 15px;
            text-transform: uppercase;
            letter-spacing: 1px;
            font-weight: 600;
        }}
        
        .metric-card .value {{
            font-size: 3rem;
            font-weight: 700;
            margin-bottom: 10px;
            line-height: 1;
        }}
        
        .metric-card .percentage {{
            font-size: 1.2rem;
            color: var(--muted-color);
            font-weight: 500;
        }}
        
        .success {{ color: var(--success-color); }}
        .danger {{ color: var(--danger-color); }}
        .warning {{ color: var(--warning-color); }}
        .primary {{ color: var(--primary-color); }}
        
        .charts-section {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 40px;
        }}
        
        .chart-card {{
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            border-left: 6px solid var(--info-color);
        }}
        
        .chart-card h3 {{
            margin-bottom: 25px;
            color: var(--text-color);
            font-size: 1.3rem;
            font-weight: 600;
        }}
        
        .violation-item, .label-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid var(--border-color);
        }}
        
        .violation-item:last-child, .label-item:last-child {{
            border-bottom: none;
        }}
        
        .label-badge {{
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 600;
            color: white;
            font-family: 'Courier New', monospace;
        }}
        
        .count-badge {{
            background: var(--light-gray);
            color: var(--text-color);
            padding: 4px 12px;
            border-radius: 12px;
            font-weight: 600;
            font-size: 0.9rem;
        }}
        
        .repositories-section {{
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            border-left: 6px solid var(--warning-color);
        }}
        
        .repositories-section h2 {{
            margin-bottom: 25px;
            color: var(--text-color);
            font-size: 1.5rem;
            font-weight: 600;
        }}
        
        .repository-card {{
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 25px;
            margin-bottom: 20px;
            background: #fafbfc;
            transition: box-shadow 0.2s ease;
        }}
        
        .repository-card:hover {{
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}
        
        .repository-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 20px;
        }}
        
        .repository-name {{
            font-size: 1.3rem;
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
            color: var(--muted-color);
            text-align: right;
        }}
        
        .violations-list {{
            margin-top: 20px;
        }}
        
        .violation-badge {{
            display: inline-block;
            background: #fff5f5;
            color: #c53030;
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 0.85rem;
            margin: 3px;
            border: 1px solid #fed7d7;
            font-weight: 500;
        }}
        
        .footer {{
            text-align: center;
            margin-top: 50px;
            padding: 30px;
            background: white;
            border-radius: 12px;
            color: var(--muted-color);
            border-left: 6px solid var(--primary-color);
        }}
        
        .footer a {{
            color: var(--primary-color);
            text-decoration: none;
            font-weight: 600;
        }}
        
        .success-message {{
            background: linear-gradient(135deg, #d4edda, #c3e6cb);
            color: #155724;
            padding: 40px;
            border-radius: 12px;
            text-align: center;
            margin: 30px 0;
            border-left: 6px solid var(--success-color);
        }}
        
        .success-message h2 {{
            font-size: 2rem;
            margin-bottom: 15px;
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
            
            .repository-header {{
                flex-direction: column;
                align-items: flex-start;
            }}
            
            .repository-meta {{
                text-align: left;
                margin-top: 10px;
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
"""
    
    # Add status badge based on compliance rate
    compliance_rate = summary['compliance_rate']
    if compliance_rate >= 90:
        status_class = "status-excellent"
        status_text = "Excellent Compliance"
    elif compliance_rate >= 70:
        status_class = "status-good"
        status_text = "Good Compliance"
    elif compliance_rate >= 50:
        status_class = "status-needs-improvement"  
        status_text = "Needs Improvement"
    else:
        status_class = "status-critical"
        status_text = "Critical - Action Required"
    
    html_content += f"""
            <div class="status-badge {status_class}">
                {status_text} ({compliance_rate}%)
            </div>
        </div>
        
        <div class="metrics-grid">
            <div class="metric-card">
                <h3>📊 Total Repositories</h3>
                <div class="value primary">{summary['total_repositories']}</div>
                <div class="percentage">Scanned</div>
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
    
    for violation_type, count in analysis['top_violations'][:8]:
        percentage = (count / total_violations * 100) if total_violations > 0 else 0
        html_content += f"""
                <div class="violation-item">
                    <span style="font-weight: 500;">{violation_type.title()}</span>
                    <span class="count-badge">{count} ({percentage:.1f}%)</span>
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
    
    for label, count in sorted(analysis['label_distribution'].items(), key=lambda x: x[1], reverse=True)[:8]:
        label_category = label.split(':')[0]
        color = label_colors.get(label_category, '#6a737d')
        
        html_content += f"""
                <div class="label-item">
                    <span class="label-badge" style="background-color: {color};">{label}</span>
                    <span class="count-badge">{count}</span>
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
        
        # Show repositories sorted by number of violations
        sorted_repos = sorted(report['repositories'], key=lambda x: len(x['violations']), reverse=True)
        
        for repo in sorted_repos[:15]:  # Show top 15 most problematic
            html_content += f"""
            <div class="repository-card">
                <div class="repository-header">
                    <div class="repository-name">
                        <a href="{repo['url']}" target="_blank">{repo['name']}</a>
                    </div>
                    <div class="repository-meta">
                        <strong>{repo['visibility'].title()}</strong><br>
                        {repo['size']}KB • {repo['language']}<br>
                        {len(repo['violations'])} issues
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
        
        if len(report['repositories']) > 15:
            html_content += f"""
            <div style="text-align: center; padding: 20px; color: var(--muted-color);">
                <em>... and {len(report['repositories']) - 15} more non-compliant repositories</em>
            </div>
"""
        
        html_content += "</div>"
    else:
        html_content += """
        <div class="success-message">
            <h2>🎉 Congratulations!</h2>
            <p style="font-size: 1.3rem; margin-top: 15px;">All repositories are compliant with governance standards.</p>
            <p style="margin-top: 10px;">Your organization maintains excellent repository hygiene!</p>
        </div>
"""
    
    html_content += f"""
        <div class="footer">
            <p><strong>Repository Compliance Checker v2.0</strong></p>
            <p>Generated automatically for {metadata['organization']} • Next scan: Tomorrow at 02:00 UTC</p>
            <p style="margin-top: 15px;">
                <a href="compliance-report.json" target="_blank">📄 Download JSON Report</a> |
                <a href="https://github.com/{metadata['organization']}/admin-repo-compliance/actions" target="_blank">🔧 View Workflow Runs</a> |
                <a href="https://github.com/{metadata['organization']}/admin-repo-compliance/issues" target="_blank">📋 Track Issues</a>
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
    
    print(f"\n{'='*80}")
    print(f"📊 REPOSITORY COMPLIANCE SUMMARY")
    print(f"{'='*80}")
    print(f"🏢 Organization: {report['metadata']['organization']}")
    print(f"📅 Scan Date: {report['metadata']['scan_date']}")
    print(f"📊 Total Repositories: {summary['total_repositories']}")
    print(f"✅ Compliant: {summary['compliant_repositories']} ({(summary['compliant_repositories']/summary['total_repositories']*100):.1f}%)")
    print(f"❌ Non-Compliant: {summary['non_compliant_repositories']} ({(summary['non_compliant_repositories']/summary['total_repositories']*100):.1f}%)")
    print(f"📈 Compliance Rate: {summary['compliance_rate']}%")
    
    if analysis['top_violations']:
        print(f"\n🚨 TOP VIOLATIONS:")
        for violation_type, count in analysis['top_violations'][:5]:
            print(f"   • {violation_type.title()}: {count} occurrences")
    
    if analysis['label_distribution']:
        print(f"\n🏷️ LABELS APPLIED:")
        for label, count in sorted(analysis['label_distribution'].items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"   • {label}: {count}")
    
    print(f"\n📄 Generated Reports:")
    print(f"   • compliance-report.json (detailed data)")
    print(f"   • compliance-dashboard.html (visual dashboard)")
    
    print(f"\n{'='*80}")

def print_recommendations(report, dry_run):
    """Print actionable recommendations"""
    summary = report['summary']
    analysis = report['analysis']
    
    print(f"\n💡 RECOMMENDATIONS & NEXT STEPS")
    print(f"{'='*80}")
    
    if summary['compliance_rate'] == 100:
        print(f"🎉 Excellent! All repositories are compliant.")
        print(f"✅ Continue monitoring with daily scans")
        print(f"✅ Consider implementing stricter rules")
        
    elif summary['compliance_rate'] >= 80:
        print(f"🎯 Good compliance rate! Focus on remaining issues:")
        
    elif summary['compliance_rate'] >= 60:
        print(f"⚠️ Moderate compliance. Action needed:")
        
    else:
        print(f"🚨 Low compliance rate. Immediate action required:")
    
    # Specific recommendations based on violations
    label_counts = analysis['label_distribution']
    
    if label_counts.get('naming:missing-prefix', 0) > 0:
        count = label_counts['naming:missing-prefix']
        print(f"\n🔤 NAMING ISSUES ({count} repositories):")
        print(f"   1. Review repositories missing required prefixes")
        print(f"   2. Consider bulk rename operations")
        print(f"   3. Implement naming validation for new repos")
    
    if label_counts.get('security:no-branch-protection', 0) > 0:
        count = label_counts['security:no-branch-protection']
        print(f"\n🔒 SECURITY ISSUES ({count} repositories):")
        print(f"   1. Enable branch protection rules IMMEDIATELY")
        print(f"   2. Require pull request reviews")
        print(f"   3. Set up automated security scanning")
    
    if label_counts.get('missing:readme', 0) > 0:
        count = label_counts['missing:readme']
        print(f"\n📄 DOCUMENTATION ISSUES ({count} repositories):")
        print(f"   1. Add README files to improve discoverability")
        print(f"   2. Use repository templates for consistency")
        print(f"   3. Include usage and contribution guidelines")
    
    archive_candidates = label_counts.get('activity:archived', 0) + label_counts.get('activity:stale', 0)
    if archive_candidates > 0:
        print(f"\n🗃️ ARCHIVE OPPORTUNITIES ({archive_candidates} repositories):")
        print(f"   1. Review stale repositories for archival")
        print(f"   2. Clean up unused experimental projects")
        print(f"   3. Preserve important historical projects")
    
    print(f"\n🎯 IMMEDIATE ACTIONS:")
    print(f"   1. Review high-priority issues in admin repository")
    print(f"   2. Fix security-related violations first")
    print(f"   3. Implement repository templates")
    print(f"   4. Set up automated compliance monitoring")
    
    if dry_run:
        print(f"\n🧪 DRY RUN COMPLETED:")
        print(f"   • Run again with dry_run=false to apply changes")
        print(f"   • Labels and issues will be created automatically")
        print(f"   • Dashboard will be deployed to GitHub Pages")
    else:
        print(f"\n✅ PRODUCTION RUN COMPLETED:")
        print(f"   • Labels applied to non-compliant repositories")
        print(f"   • Issues created for tracking progress")
        print(f"   • Dashboard deployed (check GitHub Pages)")
    
    print(f"\n📊 View the dashboard at:")
    org_name = report['metadata']['organization']
    print(f"   https://{org_name}.github.io/admin-repo-compliance")

if __name__ == '__main__':
    main()
