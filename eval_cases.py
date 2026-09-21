EVAL_CASES = [

    {
        "id": "E01",
        "name": "Strong understandable PRD",
        "prd_text": """
Feature: Saved Views

Problem:
Operations managers repeatedly configure the same table columns and filters
when reviewing account health.

Evidence:
Five customer interviews found that four users recreate the same views
several times per week. Product usage data also shows frequent repeated
filter combinations.

User:
Operations managers managing 50+ customer accounts.

Desired outcome:
Reduce repetitive setup when users return to common account-review workflows.

Scope:
Users can save the current filters and visible columns as a named view.
Users can reopen, rename, and delete saved views.

Requirements:
- Save current view
- Give the view a name
- Reopen a saved view
- Rename a saved view
- Delete a saved view
- Maximum 20 saved views per user

Success metric:
At least 30% of eligible operations managers use a saved view within
60 days of launch.
""",
        "expected_status": "REVIEW",
        "expected_tool_use": False,
        "purpose": "Reviewer should recognize a reasonably strong PRD and avoid manufacturing major gaps."
    },

    {
        "id": "E02",
        "name": "Too ambiguous to review",
        "prd_text": """
We need to improve the customer experience.

Customers are having issues and we should make the product easier to use.

We should build something that improves the workflow.
""",
        "expected_status": "ASK",
        "expected_tool_use": False,
        "purpose": "Reviewer should ask for minimum clarification because the proposal itself cannot be understood."
    },

    {
        "id": "E03",
        "name": "Weak but understandable PRD",
        "prd_text": """
Feature: Bulk User Deactivation

Admins currently deactivate users one at a time.

We propose allowing admins to select multiple users and deactivate them
in one action.

The feature will be available from the user-management page.
""",
        "expected_status": "REVIEW",
        "expected_tool_use": False,
        "purpose": "Missing detail should become review feedback, not automatically trigger ASK."
    },

    {
        "id": "E04",
        "name": "Mixed supporting evidence",
        "prd_text": """
Feature: Saved Filters

Operations managers repeatedly recreate filters.

Customer interviews show this is a recurring problem.

We propose allowing users to save and reuse filters.
""",
        "supporting_text": """
Interview 1:
Operations manager recreates the same account-status filters every morning.

Interview 2:
Operations manager uses different filters every session and does not see
value in saving them.

Interview 3:
Operations manager recreates two common filter combinations several times
per week.
""",
        "expected_status": "REVIEW",
        "expected_tool_use": True,
        "purpose": "Agent should inspect relevant evidence and recognize that the evidence is mixed."
    },

    {
        "id": "E05",
        "name": "Blank process sections",
        "prd_text": """
Feature: Session Timeout Control

Problem:
Enterprise admins want tighter control over inactive sessions.

Evidence:
Three enterprise customers requested configurable session timeout.

Scope:
Admins can choose an inactivity timeout of 15, 30, or 60 minutes.

Requirements:
- Setting available only to administrators
- Default remains 60 minutes
- Existing sessions follow the new policy after their next login

Success metric:
Percentage of eligible enterprise accounts configuring a custom timeout.

Approval:

Feasibility Review:

Design Approval:

Tech Approval:
""",
        "expected_status": "REVIEW",
        "expected_tool_use": False,
        "purpose": "Blank process sections may be noted as unclear but should not automatically make product content critically weak."
    },

    {
        "id": "E06",
        "name": "Irrelevant conditional template sections",
        "prd_text": """
Feature: Rename Saved Report

Problem:
Users cannot correct report names after creating them.

Evidence:
Multiple support requests ask how to rename existing reports.

Scope:
A report owner can rename a saved report from the report menu.

Requirements:
- Rename option appears in the existing actions menu
- New name must be between 1 and 80 characters
- Duplicate names are allowed

Success metric:
Reduction in support requests related to incorrect report names.

Email Notifications:

In-app Messages:

Migration:
""",
        "expected_status": "REVIEW",
        "expected_tool_use": False,
        "purpose": "Reviewer should not demand email, migration, or messaging simply because template headings exist."
    },

    {
        "id": "E07",
        "name": "Scope contradiction",
        "prd_text": """
Feature: Restore Attachments

Objective:
Allow users to restore attachments together with deleted invoices.

Scope:
Restore workflow for invoice attachments.

Requirements:
- User can restore invoice attachments
- User can choose whether attachments are included
- User can also export attachments for invoices, bills, payments, customers,
  vendors, expenses, and credit memos
- Export activity appears in the export report
""",
        "expected_status": "REVIEW",
        "expected_tool_use": False,
        "purpose": "Reviewer should identify that requirements introduce a material Export capability outside stated scope."
    },

    {
        "id": "E08",
        "name": "Polished solution with weak problem",
        "prd_text": """
Feature: Smart Dashboard Layouts

Scope:
Users can select Compact, Standard, or Expanded dashboard layouts.

Requirements:
- Layout selector in Settings
- Preference persists across sessions
- Responsive layout supported
- Keyboard navigation supported
- Empty, loading, and error states designed
- Analytics events emitted for every layout change
- Rollback supported through feature flag

Design:
High-fidelity designs are complete.

Success metric:
Number of layout changes per month.
""",
        "expected_status": "REVIEW",
        "expected_tool_use": False,
        "purpose": "Detailed implementation should not distract reviewer from missing problem, user need, and evidence."
    },

    {
        "id": "E09",
        "name": "Early research without solution",
        "prd_text": """
Research topic: Endpoint backup opportunity

What we heard:
- Three IT admins said employee device data is sometimes lost when laptops are
  replaced or employees leave.
- Two admins already rely on cloud folder redirection and are unsure whether
  a separate endpoint backup product would add enough value.
- One customer asked specifically about backing up Downloads and Desktop.

Current conclusion:
There may be an opportunity for endpoint protection, but the customer need is
not yet consistent enough to recommend a solution. Next step is to interview
more customers with mixed cloud-suite deployment models and understand which
local data actually remains outside cloud sync.
""",
        "expected_status": "REVIEW",
        "expected_tool_use": False,
        "purpose": "Early research should be reviewed as research, not penalized for lacking requirements, rollout, or a chosen solution."
    },

    {
        "id": "E10",
        "name": "External content with inconsistent ROI claim",
        "prd_text": """
Draft customer article: The cost of manual recovery

Assumptions:
- Labor cost is $100/hour.
- Scenario A requires 10 hours of manual work = $1,000.
- Scenario B requires 20 hours of manual work = $2,000.
- Scenario C requires 100 hours of manual work = $10,000.

Headline conclusion:
Across all three scenarios, manual recovery costs only $3,000 while our product
reduces recovery cost to $20.

Product claim:
Our product restores every dataset instantly with zero manual intervention.
""",
        "expected_status": "REVIEW",
        "expected_tool_use": False,
        "purpose": "External content should trigger claim-integrity review for inconsistent totals and unsupported absolute product claims."
    },

    {
        "id": "E11",
        "name": "Feasibility note with explicit engineering dependency",
        "prd_text": """
Proposal: Preserve mailbox folder permissions during restore

Customer need:
Enterprise admins expect restored folders to retain the same delegated access
where the source platform allows it.

Product direction:
Preserve permissions by default when the source API exposes them.

Known dependency:
Engineering still needs to verify whether the target API supports recreating
all permission types and whether any require elevated scopes. This feasibility
question is explicitly open and will determine the final supported matrix.

Next step:
Engineering feasibility review, then finalize supported permission types.
""",
        "expected_status": "REVIEW",
        "expected_tool_use": False,
        "purpose": "A clearly tracked engineering feasibility dependency should not be treated as missing PM thinking merely because the answer is unresolved."
    },

    {
        "id": "E12",
        "name": "Post-launch analysis with weak conclusion",
        "prd_text": """
Post-launch review: Bulk onboarding

Expected outcome:
Reduce time required for partners to onboard multiple customer accounts.

Observed after launch:
- Median onboarding completion time fell from 42 minutes to 25 minutes.
- Completion rate increased from 71% to 74%.
- Support tickets about CSV formatting increased from 8 to 21 per month.

Conclusion:
The launch was fully successful and no further work is required.
""",
        "expected_status": "REVIEW",
        "expected_tool_use": False,
        "purpose": "Post-launch work should be judged on whether the conclusion follows from outcomes and trade-offs, not on missing PRD sections."
    }

]