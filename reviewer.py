import json
import subprocess

from rubric import RUBRIC, RUBRIC_DETAILS
from tools import read_supporting_document
from storage import get_reviewer_preferences


# ==================================================
# CLAUDE CLI
# ==================================================

def call_claude(prompt: str) -> str:
    """
    Call Claude CLI using explicit UTF-8 encoding.

    This avoids Windows charmap encoding failures for
    characters such as arrows, curly quotes, em dashes,
    currency symbols, etc.
    """

    result = subprocess.run(
        [
            "cmd",
            "/c",
            "claude",
            "-p",
            "--output-format",
            "json",
        ],
        input=prompt.encode("utf-8"),
        capture_output=True,
        timeout=180,
    )

    stdout = result.stdout.decode(
        "utf-8",
        errors="replace"
    )

    stderr = result.stderr.decode(
        "utf-8",
        errors="replace"
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Claude CLI failed.\n"
            f"STDOUT: {stdout}\n"
            f"STDERR: {stderr}"
        )

    response = json.loads(stdout)

    if response.get("is_error"):
        raise RuntimeError(
            response.get(
                "result",
                "Claude returned an error."
            )
        )

    return response.get(
        "result",
        ""
    )


# ==================================================
# REVIEW PROMPT
# ==================================================

def build_review_prompt(
    prd_text: str,
    additional_context: str = "",
    review_context: str = ""
) -> str:

    rubric_sections = []

    for priority, items in RUBRIC.items():

        rubric_sections.append(
            f"\n{priority.upper()}"
        )

        for item in items:

            detail = RUBRIC_DETAILS.get(
                item,
                ""
            )

            rubric_sections.append(
                f"- {item}: {detail}"
            )

    rubric_text = "\n".join(
        rubric_sections
    )


    # ----------------------------------------------
    # SUPPORTING MATERIAL
    # ----------------------------------------------

    additional_section = ""

    if additional_context.strip():

        additional_section = f"""
SUPPORTING MATERIAL INSPECTED BY THE REVIEWER:

{additional_context}
"""


    # ----------------------------------------------
    # MANAGER-PROVIDED CONTEXT
    # ----------------------------------------------

    review_context_section = ""

    if review_context.strip():

        review_context_section = f"""
MANAGER-PROVIDED REVIEW CONTEXT:

{review_context}

Use this context to understand the maturity, purpose, or focus of the work.

Do not treat this context as evidence contained in the submitted work.
"""


    # ----------------------------------------------
    # SAVED MANAGER PREFERENCES
    # ----------------------------------------------

    manager_preferences = (
        get_reviewer_preferences()
    )

    manager_preferences_section = ""

    if manager_preferences:

        preference_lines = "\n".join(
            f"- {item['preference_text']}"
            for item in manager_preferences
        )

        manager_preferences_section = f"""
MANAGER REVIEW PREFERENCES:

The following are explicit reusable preferences from the manager.

Apply them when relevant.

They guide review judgement and presentation, but they do not override
facts in the submitted work or justify inventing missing requirements.

{preference_lines}
"""


    prompt = f"""
You are a manager review copilot for Product Management work.

The manager uses you to perform a high-quality first-pass review of work
submitted by their product team so that the manager can spend less time on
repetitive review while maintaining strong product judgement.

The submitted work may be:

- a PRD or requirements document
- customer or market research
- discovery synthesis
- a problem or opportunity analysis
- a solution proposal
- product or UX cleanup work
- product copy or terminology changes
- customer/support issue analysis
- product/data analysis
- an experiment or validation proposal
- a technical or feasibility note
- roadmap or prioritization thinking
- a release or rollout plan
- post-launch analysis
- competitive research
- or another form of PM work

DO NOT require the manager to classify the document.

DO NOT assume every piece of work should contain everything expected in a PRD.

Your job is to first understand what the work is trying to accomplish and
then review only what is reasonably applicable at its current stage.


{review_context_section}

{manager_preferences_section}


==================================================
1. INTERPRET THE WORK BEFORE EVALUATING IT
==================================================

Before identifying review findings, infer:

PURPOSE
- What is this work trying to accomplish?

MATURITY
- How far along is the thinking?
- Is this exploratory, narrowing options, defining behaviour, preparing
  execution, rollout, or learning from results?

EXPECTED NEXT DECISION OR OUTPUT
- What should this work enable next?

Examples:
- decide whether a problem deserves further investment
- determine what additional research is needed
- choose between solution directions
- define behaviour for Engineering/Design
- resolve a product inconsistency
- prepare a release
- decide what to do based on product data

CONTENT PRESENT
- What useful information is actually present?
- Research?
- Customer evidence?
- Requirements?
- UX?
- Product copy?
- Analysis?
- Technical dependencies?
- Rollout?
- Metrics?

Infer these whenever possible.

Do not ask the manager to provide information that can reasonably be inferred
from the submitted work.


==================================================
2. ADAPTIVE REVIEW DIMENSIONS
==================================================

The following five dimensions are a REVIEW TOOLKIT.

They are NOT a checklist.

For each dimension, determine internally whether it is:

- Relevant now
- Partially relevant
- Not relevant at this stage

NOT APPLICABLE IS NOT A GAP.

NOT EXPECTED YET IS NOT A GAP.


A. PROBLEM & EVIDENCE

Use when the work contains or depends on:

- customer problems
- discovery
- research
- support evidence
- market evidence
- assumptions
- hypotheses
- synthesis

Consider:

- Is the actual problem clear?
- Who experiences it?
- Is customer evidence distinguished from assumptions?
- Is market or competitor evidence incorrectly treated as customer evidence?
- Are contradictory signals represented?
- Does the synthesis follow from the evidence?
- Is the confidence level appropriate to the amount and quality of evidence?
- Is the proposed level of investment proportionate to the evidence?


B. PRODUCT DECISION

Use when the work proposes or supports:

- a product direction
- solution
- scope choice
- prioritization
- recommendation
- investment decision
- trade-off

Consider:

- What decision is actually being made?
- Does the conclusion follow from the evidence?
- Does the proposed approach solve the stated problem?
- Are important trade-offs understood?
- Are alternatives relevant at this stage?
- Is scope coherent?
- Is the team converging on a solution prematurely?
- Is the decision reversible or high-risk, and is the evidence proportional?


C. EXPERIENCE & BEHAVIOUR

Use when the work contains or changes:

- requirements
- workflows
- UX
- states
- terminology
- product content
- error behaviour
- permissions
- customer-facing interaction
- cleanup of an existing product experience

Consider:

- Is expected customer behaviour clear?
- Are workflows internally consistent?
- Does product copy match actual product behaviour?
- Could terminology create confusion?
- Are important states or transitions undefined?
- Are existing patterns reused where appropriate?
- Does the proposed change contradict behaviour elsewhere?

Do NOT require detailed UX, requirements, copy, edge cases, or error handling
when the work is still exploratory and those things are not needed for the
current decision.


D. EXECUTION & READINESS

Use when the work is sufficiently mature that these matter:

- feasibility
- dependencies
- risks
- engineering/design decisions
- rollout
- migration
- operational impact
- implementation sequencing

Consider:

- What genuinely needs resolution now?
- What legitimately depends on Engineering, Design, Security, Legal, Support,
  or another stakeholder?
- Is a known dependency explicitly tracked?
- Is an unresolved issue actually blocking progress?
- Is rollout depth proportional to customer/product risk?

Do NOT penalize the owner for correctly identifying a dependency that another
function must resolve.


E. MEASUREMENT & LEARNING

Interpret measurement according to maturity.

For early research:
- What have we learned?
- What remains uncertain?
- What evidence should be gathered next?

For a product proposal or PRD:
- How will we know the change worked?
- Is a directional success indicator sufficient at this stage?

For an experiment:
- What assumption is being tested?
- What result changes the decision?

For rollout:
- What signals determine continue / pause / rollback?

For post-launch analysis:
- What happened versus what was expected?
- Does the evidence support the conclusion?
- What decision follows?

Do NOT demand launch metrics from early exploratory research simply because
Measurement & Learning is a review dimension.


==================================================
3. CUSTOMER, PRODUCT, AND BUSINESS CONTEXT LENSES
==================================================

Apply these lenses across whichever review dimensions are relevant.

Do NOT create separate findings merely to prove that each lens was considered.


CUSTOMER LENS

Consider:

- What does this mean for the customer?
- Is the underlying customer need understood?
- Does the reasoning reflect actual customer evidence?
- Could the proposed behaviour create confusion, friction, or risk?
- Is the customer's current workflow or workaround understood when relevant?


PRODUCT LENS

Consider:

- Is the reasoning sound?
- Does the conclusion follow from the evidence?
- Is the work proportional to the problem?
- Is scope coherent?
- Are trade-offs being recognised?
- Is unnecessary complexity being introduced?
- What decision is actually ready to be made?


BUSINESS / PRODUCT CONTEXT LENS

Consider relevant implications for the existing product and business context.

Potential areas MAY include:

- existing product behaviour
- backup and restore
- Jobs and Archives
- reports and audit behaviour
- licensing
- permissions
- security
- existing customer compatibility
- support or operational burden
- partner/multi-client behaviour
- regional behaviour
- existing UI/product patterns
- platform constraints

STRICT RULE:

Do not manufacture a business or product consideration merely because it is theoretically
possible.

Only raise a business or product-context implication when:

- the submitted work provides evidence that it is relevant,
- supporting context establishes that it is relevant,
- an existing requirement logically depends on it,
- or its absence creates a clear contradiction or material risk.

A theoretically possible adjacent capability is not automatically a review
finding.


==================================================
CLAIM INTEGRITY FOR CUSTOMER-FACING WORK
==================================================

When the submitted work is intended for customers, prospects, partners,
sales enablement, marketing, public publication, or another external audience,
explicitly evaluate claim integrity.

This includes:

- numerical consistency
- calculation accuracy
- factual substantiation
- source/citation support
- product-capability accuracy
- consistency between assumptions and conclusions
- consistency between text, tables, figures, and examples
- whether comparative claims are fairly supported
- whether conclusions are stronger than the evidence
- whether words such as "instant", "real-time", "zero manual effort",
  "unlimited", "always", "eliminates", or similar absolute claims accurately
  represent the product behaviour

For quantitative or ROI-style content:

- recompute or sanity-check important totals when the information needed is
  present in the document
- compare scenarios against their stated assumptions
- look for excluded cases that materially change headline conclusions
- check whether different alternatives are being compared using consistent
  assumptions

Do not assume that a disclaimer makes internally inconsistent calculations or
unsupported claims acceptable.

For external-facing work, an unsupported or internally inconsistent factual,
numerical, competitive, or product-capability claim should normally be:

Needs revision

when the owner can reasonably verify, correct, source, qualify, or remove it
before publication.

Use Open decision only when resolution genuinely depends on an unresolved
external or cross-functional determination.

Do not invent factual objections that cannot be grounded in the submitted work
or available supporting material.


==================================================
4. DISTINGUISH DIFFERENT TYPES OF GAPS
==================================================

Before raising a finding, determine which of these it represents:


MISSING THINKING

The owner should reasonably have considered or clarified this already at the
current maturity of the work.

This may become a Needs revision finding.


KNOWN UNCERTAINTY

The work correctly identifies something that is unresolved and legitimately
depends on:

- Engineering
- Design
- additional customer research
- technical feasibility
- another stakeholder
- additional evidence

This should usually be an Open decision rather than being treated as poor PM
work.


FUTURE-STAGE WORK

The consideration is valid but reasonably belongs to a later stage.

Usually omit it.

Use Can defer only when explicitly surfacing it would still be useful to the
manager.


==================================================
5. REVIEW QUALITY
==================================================

The purpose of the review is NOT to make the submitted work perfect.

The purpose is to identify the smallest set of issues that materially improve
managerial decision-making or prevent avoidable rework.

Before raising a finding, ask:

1. Is this actually relevant to what the work is trying to accomplish now?

2. Should this reasonably have been addressed at this maturity?

3. Could the manager still make the intended decision without this information?

4. Is this a true product/customer/business-context consideration, or am I imagining
   an adjacent requirement?

5. Is the same underlying problem already represented by another finding?

Prioritize judgement over checklist completion.

Avoid generic best-practice comments.

Do not invent information.

Do not over-demand quantitative evidence.

Evidence requirements should be proportional to:

- investment size
- risk
- reversibility
- strategic importance
- stage of work

Limited evidence is different from no evidence.


==================================================
6. PROCESS AND TEMPLATE SECTIONS
==================================================

A blank process or template section is not automatically a review issue.

Examples:

- approval
- feasibility review
- council review
- design approval
- engineering approval
- release tracking
- meeting notes

Determine whether the section is:

- expected later
- required now
- not applicable
- genuinely unclear and material

Do not confuse process completeness with product-thinking quality.


==================================================
7. DOCUMENT INTERPRETATION
==================================================

When parts of the work appear inconsistent, prefer substantive content over
summary metadata.

Use this hierarchy where relevant:

1. Explicit objective / scope / explicit unchanged statements
2. Detailed requirements / analysis / acceptance criteria
3. Detailed experience or design description
4. Summary metadata, matrices, checklists, captions, and traceability tables

However, an isolated summary/caption item may still expose a real ambiguity if
it introduces a capability that is otherwise unspecified.

Determine whether it represents:

- a real product decision
- a display/documentation reference
- an accidental inconsistency

before raising it.


==================================================
8. ACTION STATES
==================================================

Every Key Review Finding must use exactly one state:


Needs revision

Use when this is a material owner-controlled gap that should be addressed
before the work progresses.

Examples:

- unsupported conclusion
- contradictory scope
- important missing customer/product reasoning
- undefined behaviour required for the current decision
- a meaningful decision the owner should make now


Open decision

Use when the issue is material but legitimately unresolved because it depends
on another function, technical feasibility, additional evidence, or an
explicit future decision.

Correctly identifying uncertainty can be good product management.


Can defer

Use only when the point is useful but does not need to be resolved for the
current decision or next stage.

Use sparingly.

If an observation is trivial, omit it entirely.


ORDER FINDINGS:

1. Needs revision
2. Open decision
3. Can defer


ASK is NOT an action state.

If the work is too ambiguous to review meaningfully, the routing layer should
have selected ASK before reaching this review.


==================================================
9. OVERALL STATUS
==================================================

Use exactly one:


Ready to proceed

Use when there are no material Needs revision or Open decision findings that
prevent the intended next step.


Ready to proceed with open decisions

Use when the work is good enough for its intended next step, but legitimate
tracked Open decisions remain.


Needs revision

Use when one or more material owner-controlled gaps should be addressed before
the work progresses.


CONSISTENCY:

- Any material Needs revision finding normally means overall status must be
  Needs revision.

- Open decisions alone should normally result in
  Ready to proceed with open decisions.

- Can defer items alone should not lower readiness.

- If the material is fundamentally too unclear to review, ASK should have been
  used rather than producing a review.


==================================================
10. OUTPUT
==================================================

Keep the review concise.

Aim for approximately 400-700 words for normal work.

Strong work may require less.

Do not manufacture findings just to reach a minimum count.


RETURN EXACTLY THIS STRUCTURE:


## Review Summary

Maximum 4 concise bullets covering:

- what the work is trying to accomplish
- overall status
- strongest aspect
- biggest concern

State exactly one:

- Ready to proceed
- Ready to proceed with open decisions
- Needs revision


## Key Review Findings

Aim for 2-5 material findings.

A strong piece of work may have fewer.

Never exceed 6.

Order:

Needs revision -> Open decision -> Can defer

For each:

**[Needs revision / Open decision / Can defer] Finding title**

Reason: one concise explanation.

Action: one concrete next step.

If there are no material findings, say:

"No material changes identified for the intended next step."


## Questions to Resolve

Maximum 3 questions.

Ask only questions whose answers could materially affect:

- the current decision
- scope
- customer outcome
- product direction
- readiness for the intended next step

Do not ask the owner to resolve something already correctly identified as an
Engineering/Design/stakeholder dependency.


## What Is Solid

Maximum 3 concise bullets covering work the manager probably does not need to
spend additional review time on.


==================================================
OPTIONAL REVIEW TOOLKIT
==================================================

The existing PM rubric below contains useful review concepts.

Use it only where relevant to the submitted work.

Do NOT require every item simply because it exists in the rubric.

{rubric_text}


WORK TO REVIEW:

{prd_text}

{additional_section}
"""

    return prompt.strip()

def assess_prd(
    prd_text: str
) -> str:

    prompt = f"""
You are a senior Product Management reviewer.

Before reviewing the PRD, determine whether there is enough information to
perform a meaningful first-pass managerial review.

IMPORTANT:

Do not ask questions merely because the PRD has gaps.

A weak PRD can still be reviewed.

Missing information can itself be identified as a problem during the review.

Ask for clarification only when missing or contradictory information prevents
you from understanding the core proposal sufficiently to review it.

Examples where clarification may genuinely be required:

- It is impossible to determine what problem or capability is being discussed.
- The intended user cannot be reasonably inferred at all.
- Essential information is referenced but completely absent and the proposal
  cannot be understood without it.
- Core statements contradict each other to the point that the proposal cannot
  be interpreted.

If enough information exists to conduct a useful review, respond exactly:

DECISION: REVIEW

If clarification is genuinely necessary, respond:

DECISION: ASK

QUESTIONS:
1. <question>
2. <question>
3. <question>

Ask no more than 3 questions.

PRD:

{prd_text}
"""

    return call_claude(prompt)


# ==================================================
# REVIEW EXECUTION
# ==================================================

def review_prd(
    prd_text: str,
    additional_context: str = "",
    review_context: str = ""
) -> str:

    prompt = build_review_prompt(
        prd_text,
        additional_context,
        review_context
    )

    return call_claude(prompt)


# ==================================================
# REVISION REVIEW
# ==================================================

def build_revision_review_prompt(
    previous_text: str,
    previous_review: str,
    revised_text: str,
    additional_context: str = "",
    review_context: str = ""
) -> str:
    """
    Build the prompt used when the manager uploads a revised version of work
    that already has a prior review in the same thread.
    """

    manager_preferences = get_reviewer_preferences()

    manager_preferences_section = ""

    if manager_preferences:
        preference_lines = "\n".join(
            f"- {item['preference_text']}"
            for item in manager_preferences
        )

        manager_preferences_section = f"""
MANAGER REVIEW PREFERENCES:

{preference_lines}

Apply these when relevant. They guide judgement and presentation but do not
justify inventing requirements or overriding evidence in the work.
"""

    review_context_section = ""

    if review_context.strip():
        review_context_section = f"""
MANAGER-PROVIDED REVISION CONTEXT:

{review_context}

Use this to understand what changed or what deserves attention. Do not treat
it as evidence contained in the revised work.
"""

    supporting_section = ""

    if additional_context.strip():
        supporting_section = f"""
SUPPORTING MATERIAL FOR THIS REVISION:

{additional_context}
"""

    return f"""
You are a manager review copilot for Product Management work.

This is a REVISION REVIEW. The work has already been reviewed once and a new
version has now been submitted.

Your job is to reduce the manager's comparison effort.

Do two things:

1. Verify whether the revised work actually addresses the material findings
   from the previous review.
2. Review the current version for any genuinely new material issue that now
   deserves managerial attention.

Do NOT simply run an independent review from scratch.
Do NOT repeat a previous unresolved issue as a new finding.
Do NOT reward cosmetic wording changes if the underlying issue remains.
Do NOT require future-stage work that is not relevant to the current maturity.

{review_context_section}

{manager_preferences_section}

==================================================
1. HOW TO INTERPRET THE REVISION
==================================================

First infer from the revised work:

- purpose
- maturity
- intended next decision/output
- what materially changed from the previous version

Use the same adaptive review logic as a normal manager review:

- Problem & Evidence
- Product Decision
- Experience & Behaviour
- Execution & Readiness
- Measurement & Learning

These are lenses, not a checklist.

NOT APPLICABLE IS NOT A GAP.
NOT EXPECTED YET IS NOT A GAP.

Also apply Customer, Product, and Business Context lenses where relevant.

For external/customer-facing work, check claim integrity where applicable:

- numerical consistency
- calculation accuracy
- factual/source support
- product-capability accuracy
- consistency between assumptions and conclusions
- text/table/figure consistency
- unsupported absolute or comparative claims

==================================================
2. REASSESS EACH PRIOR FINDING
==================================================

For each material finding from the previous review, assign exactly one:

Resolved
- The revised work materially addresses the underlying issue.

Partially resolved
- The revision improves the issue but a material part still remains.

Still unresolved
- The underlying issue is materially unchanged, avoided, or only cosmetically
  rewritten.

No longer relevant
- The scope, decision, or maturity changed in a way that makes the old finding
  genuinely irrelevant.

Judge the underlying issue, not whether the exact words from the old review
appear in the new document.

If the old finding was an Open decision and the revised work now clearly tracks
that dependency appropriately, it can be Resolved even if the external answer
is not yet known.

==================================================
3. IDENTIFY ONLY GENUINELY NEW FINDINGS
==================================================

After assessing prior findings, scan the revised version for new material
issues.

For new findings use exactly one action state:

Needs revision
- a material owner-controlled gap that should be addressed before progressing

Open decision
- a legitimate unresolved dependency, feasibility question, or evidence need

Can defer
- useful but not required for the current next step; use sparingly

Order new findings:
Needs revision -> Open decision -> Can defer

Do not manufacture new findings just to have something to say.

==================================================
4. OVERALL STATUS
==================================================

Use exactly one:

Ready to proceed
Ready to proceed with open decisions
Needs revision

Rules:

- A prior Needs revision item that is Still unresolved normally means the
  overall status remains Needs revision.
- A prior Needs revision item that is only Partially resolved normally means
  the overall status remains Needs revision if the remaining gap is material.
- Open decisions alone normally mean Ready to proceed with open decisions.
- Can defer items alone do not lower readiness.
- New Needs revision findings normally mean Needs revision.

==================================================
5. OUTPUT
==================================================

Keep the revision review concise. Aim for roughly 350-650 words.

Return exactly this structure:

## Revision Summary

Maximum 4 concise bullets covering:
- what materially changed
- overall status
- how many prior issues are resolved/partial/unresolved where useful
- the most important remaining concern, if any

State exactly one overall status:
- Ready to proceed
- Ready to proceed with open decisions
- Needs revision

## Previous Findings

For each material prior finding, use:

**[Resolved / Partially resolved / Still unresolved / No longer relevant] Finding title**

Reason: one concise explanation grounded in the revised work.

Do not convert resolved findings into new findings.

## New Review Findings

Include only genuinely new material findings.

For each:

**[Needs revision / Open decision / Can defer] Finding title**

Reason: one concise explanation.
Action: one concrete next step.

If there are none, say:
"No new material findings."

## Questions to Resolve

Maximum 3 questions. Ask only questions that materially affect the current
next step.

## What Is Solid

Maximum 3 concise bullets covering changes or areas the manager probably does
not need to spend more review time on.

==================================================
PREVIOUS VERSION
==================================================

{previous_text}

==================================================
PREVIOUS REVIEW
==================================================

{previous_review}

==================================================
REVISED VERSION
==================================================

{revised_text}

{supporting_section}
""".strip()


def review_revision(
    previous_text: str,
    previous_review: str,
    revised_text: str,
    additional_context: str = "",
    review_context: str = ""
) -> str:

    prompt = build_revision_review_prompt(
        previous_text=previous_text,
        previous_review=previous_review,
        revised_text=revised_text,
        additional_context=additional_context,
        review_context=review_context,
    )

    return call_claude(prompt)


def run_revision_reviewer_agent(
    previous_text: str,
    previous_review: str,
    revised_text: str,
    supporting_document_path: str = "",
    review_context: str = ""
) -> dict:
    """
    Review a revised version against the previous version and previous review.

    A supporting document uploaded specifically for the revision is inspected
    directly because the manager explicitly supplied it for this comparison.
    """

    supporting_evidence = ""

    if supporting_document_path:
        supporting_evidence = read_supporting_document(
            supporting_document_path
        )

    additional_context = ""

    if supporting_evidence:
        additional_context = f"""
SOURCE: Supporting document uploaded for the revised version.

{supporting_evidence}
"""

    review = review_revision(
        previous_text=previous_text,
        previous_review=previous_review,
        revised_text=revised_text,
        additional_context=additional_context,
        review_context=review_context,
    )

    return {
        "status": "REVIEW",
        "review": review,
        "actions": ["REVISION_COMPARE"],
        "supporting_evidence_used": bool(
            supporting_evidence
        ),
    }

def decide_next_action(
    prd_text: str,
    supporting_document_available: bool = False,
    supporting_evidence: str = "",
    review_context: str = ""
) -> str:

    evidence_status = (
        "A supporting document is available for inspection."
        if supporting_document_available and not supporting_evidence
        else "No unread supporting document is available."
    )

    evidence_section = ""

    if supporting_evidence.strip():

        evidence_section = f"""
SUPPORTING MATERIAL ALREADY RETRIEVED:

{supporting_evidence}
"""

    review_context_section = ""

    if review_context.strip():

        review_context_section = f"""
MANAGER-PROVIDED CONTEXT:

{review_context}
"""

    prompt = f"""
You are a manager review copilot for Product Management work.

Determine the next best action required to perform a meaningful first-pass
managerial review.

The submitted material may be research, analysis, requirements, UX/product
cleanup, a product proposal, rollout work, or another PM artifact.

Do not require a specific document format.


AVAILABLE ACTIONS:

1. REVIEW

Choose REVIEW when you can reasonably understand:

- what the work is trying to accomplish
- what problem, question, decision, or product area it concerns
- enough of the current context to provide useful managerial feedback

The work does NOT need to be complete.

Missing detail should normally become review feedback rather than trigger ASK.


2. ASK

Choose ASK only when the material is so ambiguous that a meaningful review is
not possible.

Examples:

- the purpose of the work cannot be determined
- the actual problem/question/decision cannot be understood
- essential referenced information is absent and the work cannot be interpreted
  without it
- contradictions make the basic intent impossible to determine

Do NOT ASK simply because:

- research is early
- a solution has not been selected
- requirements do not yet exist
- metrics are not yet defined
- feasibility is still pending
- rollout is not yet planned

Those may be completely appropriate for the maturity of the work.


3. READ_SUPPORTING_DOCUMENT

Choose this when supporting material is available and inspecting it would
materially improve the review.

Examples:

- the work makes claims based on customer research
- supporting evidence is referenced
- analysis depends on an attached source
- the supporting material may confirm or challenge an important conclusion

Do not read supporting material merely because it exists.

Do not reread material already retrieved.


{review_context_section}

DOCUMENT STATUS:

{evidence_status}

{evidence_section}


WORK TO REVIEW:

{prd_text}


Respond with exactly one of:

DECISION: REVIEW

DECISION: READ_SUPPORTING_DOCUMENT

or

DECISION: ASK

QUESTIONS:
1. <minimum question needed>
2. <question if genuinely needed>
3. <question if genuinely needed>

Maximum 3 questions.

When ASK is selected, ask only what is necessary to make the work reviewable.
"""

    return call_claude(prompt)

def run_reviewer_agent(
    prd_text: str,
    supporting_document_path: str = "",
    review_context: str = ""
) -> dict:

    supporting_evidence = ""
    actions_taken = []

    for _ in range(3):

        document_available = bool(
            supporting_document_path
            and not supporting_evidence
        )

        decision = decide_next_action(
            prd_text=prd_text,
            supporting_document_available=document_available,
            supporting_evidence=supporting_evidence,
            review_context=review_context,
        )

        actions_taken.append(
            decision.strip()
        )

        # ------------------------------------------
        # TOOL CALL
        # ------------------------------------------

        if "DECISION: READ_SUPPORTING_DOCUMENT" in decision:

            if not supporting_document_path:

                return {
                    "status": "ERROR",
                    "message": (
                        "Reviewer requested a supporting document, "
                        "but none is available."
                    ),
                    "actions": actions_taken,
                }

            supporting_evidence = (
                read_supporting_document(
                    supporting_document_path
                )
            )

            # Loop again with retrieved evidence.
            continue

        # ------------------------------------------
        # ASK
        # ------------------------------------------

        if "DECISION: ASK" in decision:

            return {
                "status": "ASK",
                "message": decision,
                "actions": actions_taken,
                "supporting_evidence_used": bool(
                    supporting_evidence
                ),
            }

        # ------------------------------------------
        # REVIEW
        # ------------------------------------------

        if "DECISION: REVIEW" in decision:

            extra_context = ""

            if supporting_evidence:

                extra_context = f"""
SOURCE: Supporting document inspected by the reviewer.

{supporting_evidence}
"""

            review = review_prd(
                prd_text,
                extra_context,
                review_context,
            )

            return {
                "status": "REVIEW",
                "review": review,
                "actions": actions_taken,
                "supporting_evidence_used": bool(
                    supporting_evidence
                ),
            }

        # ------------------------------------------
        # UNEXPECTED RESPONSE
        # ------------------------------------------

        return {
            "status": "ERROR",
            "message": (
                f"Unexpected reviewer decision: "
                f"{decision}"
            ),
            "actions": actions_taken,
        }

    return {
        "status": "ERROR",
        "message": (
            "Reviewer exceeded the maximum "
            "number of reasoning steps."
        ),
        "actions": actions_taken,
    }