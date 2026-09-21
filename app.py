import os
import re
import tempfile
from io import BytesIO
from pathlib import Path

import streamlit as st

from tools import extract_docx_text
from reviewer import (
    run_reviewer_agent,
    run_revision_reviewer_agent,
)

from storage import (
    init_db,
    save_review,
    get_review,
    get_review_threads,
    get_thread_reviews,
    save_feedback,
    add_reviewer_preference,
    get_reviewer_preferences,
    remove_reviewer_preference,
)


# ==================================================
# PAGE CONFIG (must precede all other st.* calls)
# ==================================================

st.set_page_config(
    page_title="PM Reviewer",
    page_icon="📋",
    layout="wide",
)


# ==================================================
# TEXT UTILITIES
# ==================================================

def escape_dollar_signs_for_markdown(text: str) -> str:
    if not text:
        return text
    return text.replace("$", r"\$")


def _derive_display_title(filename: str) -> str:
    """Clean a raw filename to a human-readable display title.

    Removes extension, replaces underscores/hyphens with spaces, strips
    trailing _PRD or _v<n> noise. The original filename is never modified.
    """
    name = Path(filename).stem
    name = name.replace("_", " ").replace("-", " ")
    name = re.sub(r" +", " ", name).strip()
    name = re.sub(r"\s+PRD\s*$", "", name, flags=re.IGNORECASE).strip()
    name = re.sub(r"\s+v\d+\s*$", "", name, flags=re.IGNORECASE).strip()
    return name if name else filename


# ==================================================
# FILE EXTRACTION
# ==================================================

def extract_prd_text(uploaded_file) -> str:
    """
    Extract text from uploaded PM work.

    Supports:
    - .txt
    - .md
    - .docx

    For .docx files, paragraphs and tables are extracted
    in the same order they appear in the document.
    """

    suffix = Path(uploaded_file.name).suffix.lower()
    data = uploaded_file.getvalue()

    if suffix in [".txt", ".md"]:
        return data.decode("utf-8", errors="replace")

    if suffix == ".docx":
        return extract_docx_text(BytesIO(data))

    raise ValueError("Unsupported file format.")


# ==================================================
# AGENT EXECUTION
# ==================================================

def run_agent(
    prd_text,
    support_name="",
    support_bytes=None,
    review_context="",
):
    """Run the first-pass manager review agent."""

    if not support_bytes:
        return run_reviewer_agent(
            prd_text,
            review_context=review_context,
        )

    suffix = Path(support_name).suffix.lower()
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=suffix
        ) as temp_file:
            temp_file.write(support_bytes)
            temp_path = temp_file.name

        return run_reviewer_agent(
            prd_text,
            temp_path,
            review_context=review_context,
        )

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def run_revision_agent(
    previous_text,
    previous_review,
    revised_text,
    support_name="",
    support_bytes=None,
    review_context="",
):
    """Run the revision comparison against the previous saved version."""

    if not support_bytes:
        return run_revision_reviewer_agent(
            previous_text=previous_text,
            previous_review=previous_review,
            revised_text=revised_text,
            review_context=review_context,
        )

    suffix = Path(support_name).suffix.lower()
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=suffix
        ) as temp_file:
            temp_file.write(support_bytes)
            temp_path = temp_file.name

        return run_revision_reviewer_agent(
            previous_text=previous_text,
            previous_review=previous_review,
            revised_text=revised_text,
            supporting_document_path=temp_path,
            review_context=review_context,
        )

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


# ==================================================
# SAVE COMPLETED REVIEW
# ==================================================

def save_completed_review(
    result,
    prd_filename,
    prd_text,
    review_context="",
    thread_id=None,
    version_number=1,
    review_kind="initial",
):
    """Save a completed REVIEW result and return its database ID."""

    if result["status"] != "REVIEW":
        return None

    review_id = save_review(
        prd_filename=prd_filename,
        prd_text=prd_text,
        review_status=result["status"],
        review_output=result["review"],
        supporting_evidence_used=result.get(
            "supporting_evidence_used", False
        ),
        thread_id=thread_id,
        version_number=version_number,
        review_kind=review_kind,
        review_context=review_context,
    )

    return review_id


# ==================================================
# SESSION HELPERS
# ==================================================

def start_new_review():
    """Reset the current thread and create fresh upload widgets."""

    st.session_state.agent_result = None
    st.session_state.prd_text = ""
    st.session_state.prd_filename = ""
    st.session_state.support_name = ""
    st.session_state.support_bytes = None
    st.session_state.current_review_id = None
    st.session_state.current_thread_id = None
    st.session_state.review_context = ""
    st.session_state.review_session += 1
    st.session_state.revision_session += 1


def load_saved_thread(thread_id: int):
    """Load the latest version of a saved review thread."""

    versions = get_thread_reviews(thread_id)

    if not versions:
        return

    latest = versions[-1]

    st.session_state.current_thread_id = thread_id
    st.session_state.current_review_id = latest["id"]
    st.session_state.prd_filename = latest["prd_filename"]
    st.session_state.prd_text = latest["prd_text"]
    st.session_state.review_context = latest.get("review_context") or ""
    st.session_state.agent_result = {
        "status": latest["review_status"],
        "review": latest["review_output"],
        "supporting_evidence_used": bool(latest["supporting_evidence_used"]),
    }


def extract_overall_status(review_output: str) -> str:
    """Extract the manager-facing readiness state for sidebar display."""

    text = review_output or ""

    # The overall state is required near the top of both first-pass and
    # revision outputs. Limit the search to that opening area so a later
    # sentence such as "would be ready to proceed after..." does not
    # accidentally become the sidebar status.
    opening = text[:1800]

    patterns = [
        "Ready to proceed with open decisions",
        "Needs revision",
        "Ready to proceed",
    ]

    for state in patterns:
        if re.search(re.escape(state), opening, flags=re.IGNORECASE):
            return state

    return ""


# ==================================================
# PRESENTATION CONSTANTS
# ==================================================

# Ordered longest-first so alternation in regex doesn't mismatch prefixes.
_FINDING_STATES = [
    "No longer relevant",
    "Partially resolved",
    "Still unresolved",
    "Needs revision",
    "Open decision",
    "Can defer",
    "Resolved",
]

_STATUS_CSS = {
    "Needs revision":     "needs-revision",
    "Open decision":      "open-decision",
    "Can defer":          "can-defer",
    "Resolved":           "resolved",
    "Partially resolved": "partial",
    "Still unresolved":   "unresolved",
    "No longer relevant": "irrelevant",
}

_OVERALL_STATUS_CSS = {
    "Needs revision":                       "status-needs-revision",
    "Ready to proceed":                     "status-ready",
    "Ready to proceed with open decisions": "status-open-decisions",
}

_SECTION_LABELS = {
    "review summary":       "Review Summary",
    "revision summary":     "Revision Summary",
    "key review findings":  "Key Review Findings",
    "new review findings":  "New Review Findings",
    "previous findings":    "Previous Findings",
    "questions to resolve": "Questions to Resolve",
    "what is solid":        "What Is Solid",
}

_FINDINGS_SECTIONS = frozenset({
    "key review findings",
    "new review findings",
    "previous findings",
})


# ==================================================
# REVIEW OUTPUT RENDERING
# ==================================================

def _escape_html(text: str) -> str:
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _md_body_to_html(text: str) -> str:
    """Convert simple markdown paragraphs to HTML for finding card bodies."""
    paragraphs = re.split(r'\n\n+', text.strip())
    parts = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        para = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', para)
        para = re.sub(r'\*(.+?)\*', r'<em>\1</em>', para)
        para = para.replace('\n', '<br>')
        parts.append(f'<p>{para}</p>')
    return ''.join(parts)


def _split_sections(text: str):
    """Split review markdown into [(title, body)] pairs at ## headers."""
    parts = re.split(r'^##\s+(.+)$', text, flags=re.MULTILINE)
    sections = []
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        sections.append((title, body))
    return sections


def _canonicalize_finding_status(raw: str) -> str:
    """Map a captured status string (any case) to its canonical form."""
    raw_lower = raw.strip().lower()
    for s in _FINDING_STATES:
        if s.lower() == raw_lower:
            return s
    return raw.strip()


def _split_findings(section_body: str):
    """
    Parse a findings section into (intro_text, [(status, title, body)]).

    Handles **[Status] Title**, **Status Title**, and **[Status]: Title** formats.
    re.DOTALL lets the title span a line-wrapped bold header.
    """
    states_pat = "|".join(re.escape(s) for s in _FINDING_STATES)
    matches = list(
        re.finditer(
            rf'^\*\*\[?({states_pat})\]?[:\s]+(.+?)\*\*',
            section_body,
            re.IGNORECASE | re.MULTILINE,
        )
    )

    if not matches:
        return section_body.strip(), []

    intro = section_body[:matches[0].start()].strip()
    findings = []

    for i, match in enumerate(matches):
        status = _canonicalize_finding_status(match.group(1))
        title = match.group(2).strip().replace('\n', ' ')
        body_start = match.end()
        body_end = (
            matches[i + 1].start()
            if i + 1 < len(matches)
            else len(section_body)
        )
        findings.append((status, title, section_body[body_start:body_end].strip()))

    return intro, findings


def _render_section_header(label: str):
    st.markdown(
        f'<div class="section-header">{_escape_html(label)}</div>',
        unsafe_allow_html=True,
    )


def _render_finding_card(status: str, title: str, body: str):
    css = _STATUS_CSS.get(status, "needs-revision")
    st.markdown(
        f'<div class="finding-card finding-card-{css}">'
        f'<div class="finding-card-header">'
        f'<span class="badge badge-{css}">{_escape_html(status)}</span>'
        f'<span class="finding-title">{_escape_html(title)}</span>'
        f'</div>'
        f'<div class="finding-card-body">{_md_body_to_html(body)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


_REVISION_COUNT_COLORS = {
    "Resolved":           "#166534",
    "Partially resolved": "#92400e",
    "Still unresolved":   "#991b1b",
    "No longer relevant": "#6b7280",
}


def _count_revision_statuses(sections):
    """Count previous-finding statuses and new finding count for a revision review."""
    prev_counts: dict[str, int] = {}
    new_count = 0

    for title, body in sections:
        key = title.lower()
        if key == "previous findings":
            _, findings = _split_findings(body)
            for status, _, _ in findings:
                prev_counts[status] = prev_counts.get(status, 0) + 1
        elif key == "new review findings":
            _, findings = _split_findings(body)
            new_count = len(findings)

    return prev_counts, new_count


def _render_revision_counts_bar(prev_counts: dict, new_count: int):
    """Render a compact inline summary of revision finding statuses."""
    parts = []

    for status in ["Resolved", "Partially resolved", "Still unresolved", "No longer relevant"]:
        n = prev_counts.get(status, 0)
        if n:
            color = _REVISION_COUNT_COLORS[status]
            parts.append(
                f'<span style="color:{color};font-weight:500;">{n} {status}</span>'
            )

    if new_count:
        label = "New finding" if new_count == 1 else "New findings"
        parts.append(
            f'<span style="color:#1e40af;font-weight:500;">{new_count} {label}</span>'
        )

    if not parts:
        return

    sep = ' <span style="color:#d1d5db;">&middot;</span> '
    st.markdown(
        f'<div class="revision-counts">{sep.join(parts)}</div>',
        unsafe_allow_html=True,
    )


def render_review_output(text: str):
    """Render review output with styled section headers and finding cards."""

    if not text:
        return

    sections = _split_sections(text)

    if not sections:
        st.markdown(escape_dollar_signs_for_markdown(text))
        return

    for section_title, section_body in sections:
        key = section_title.lower()
        label = _SECTION_LABELS.get(key, section_title)
        _render_section_header(label)

        if key in _FINDINGS_SECTIONS:
            intro, findings = _split_findings(section_body)
            if intro:
                st.markdown(escape_dollar_signs_for_markdown(intro))
            if findings:
                for status, title, body in findings:
                    _render_finding_card(status, title, body)
            elif not intro:
                st.markdown(escape_dollar_signs_for_markdown(section_body))
        else:
            st.markdown(escape_dollar_signs_for_markdown(section_body))


def render_review_thread_header(
    latest: dict,
    root: dict,
    thread_status: str,
    version_count: int,
):
    """Render a compact two-line header for a review thread."""

    display_title = _derive_display_title(root["prd_filename"])
    raw_name = root["prd_filename"]
    sep = ' <span style="color:#d1d5db;">&middot;</span> '

    meta_parts = [
        f'<span style="color:#6b7280;">v{latest["version_number"]}</span>',
    ]
    if thread_status:
        css = _OVERALL_STATUS_CSS.get(thread_status, "")
        if css:
            meta_parts.append(
                f'<span class="badge status-badge {css}">'
                f'{_escape_html(thread_status)}'
                f'</span>'
            )
    if version_count > 1:
        meta_parts.append(
            f'<span style="color:#9ca3af;">{version_count} versions</span>'
        )

    raw_line = (
        f'<div style="font-size:0.6875rem;color:#9ca3af;margin-bottom:0.1rem;">'
        f'{_escape_html(raw_name)}</div>'
    ) if display_title.lower() != Path(raw_name).stem.lower() else ""

    st.markdown(
        f'<div style="margin-bottom:0.875rem;">'
        f'<div style="font-size:1rem;font-weight:600;color:#111827;margin-bottom:0.1rem;">'
        f'{_escape_html(display_title)}'
        f'</div>'
        f'{raw_line}'
        f'<div style="font-size:0.8125rem;line-height:1.5;">'
        f'{sep.join(meta_parts)}'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ==================================================
# CSS
# ==================================================

def inject_css():
    st.markdown(
        """
<style>
/* ── Layout ─────────────────────────────────────── */
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 2.5rem !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
    max-width: 1100px !important;
    margin-left: 0 !important;
    margin-right: auto !important;
}

/* ── Primary actions: dark neutral, not red ─────── */
button[kind="primary"],
[data-testid="stBaseButton-primary"] {
    background-color: #1e293b !important;
    border-color: #1e293b !important;
    color: #fff !important;
}
button[kind="primary"]:hover,
[data-testid="stBaseButton-primary"]:hover {
    background-color: #0f172a !important;
    border-color: #0f172a !important;
}

/* ── Sidebar width + top alignment ──────────────── */
section[data-testid="stSidebar"] {
    min-width: 285px !important;
    max-width: 285px !important;
    width: 285px !important;
}
section[data-testid="stSidebar"] > div:first-child {
    padding-top: 0 !important;
    padding-bottom: 1rem !important;
    position: relative !important;
}

/* Keep the collapse control, but remove its vertical layout footprint. */
[data-testid="stSidebarHeader"] {
    position: absolute !important;
    top: 0.75rem !important;
    right: 0.75rem !important;
    left: auto !important;
    width: auto !important;
    height: auto !important;
    min-height: 0 !important;
    padding: 0 !important;
    z-index: 10 !important;
}

[data-testid="stSidebarUserContent"] {
    padding-top: 1.5rem !important;
}

/* ── Sidebar wordmark & labels ───────────────────── */
.sidebar-wordmark {
    font-size: 0.9375rem;
    font-weight: 700;
    color: #111827;
    margin-bottom: 1px;
}
.sidebar-tagline {
    font-size: 0.6875rem;
    color: #9ca3af;
}
.sidebar-section-label {
    font-size: 0.625rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #9ca3af;
    padding-top: 0.75rem;
    padding-bottom: 0.2rem;
    padding-left: 0.5rem;
}

/* ── Sidebar nav: list-item style for all non-primary buttons ── */
[data-testid="stSidebar"] .stButton > button:not([kind="primary"]) {
    background: transparent !important;
    border: 1px solid transparent !important;
    border-radius: 4px !important;
    color: #374151 !important;
    padding: 0.25rem 0.5rem !important;
    text-align: left !important;
    justify-content: flex-start !important;
    font-size: 0.8125rem !important;
    line-height: 1.35 !important;
    min-height: unset !important;
    white-space: pre-line !important;
    margin-bottom: 1px !important;
}
[data-testid="stSidebar"] .stButton > button:not([kind="primary"]):hover {
    background: #f8fafc !important;
    border-color: #e2e8f0 !important;
    color: #111827 !important;
}

/* Streamlit wraps button labels in an inner Markdown container.
   Force that container to use the full button width so labels do
   not appear centered according to their text length. */
[data-testid="stSidebar"] .stButton > button:not([kind="primary"]) > div,
[data-testid="stSidebar"] .stButton > button:not([kind="primary"]) [data-testid="stMarkdownContainer"] {
    width: 100% !important;
    text-align: left !important;
}

[data-testid="stSidebar"] .stButton > button:not([kind="primary"]) [data-testid="stMarkdownContainer"] p {
    width: 100% !important;
    margin: 0 !important;
    text-align: left !important;
    white-space: pre-line !important;
}

/* ── Active nav item (rendered as HTML, not button) ── */
.nav-item-active {
    background: #f1f5f9;
    box-shadow: inset 2px 0 0 #1e293b;
    border-radius: 0 4px 4px 0;
    padding: 0.25rem 0.5rem;
    margin: 1px 0;
    width: 100%;
    box-sizing: border-box;
    text-align: left;
}
.nav-title {
    font-size: 0.8125rem;
    font-weight: 500;
    color: #111827;
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.nav-meta {
    font-size: 0.6875rem;
    color: #9ca3af;
    display: block;
    margin-top: 1px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

/* ── Upload labels ───────────────────────────────── */
.upload-label-primary {
    font-size: 0.875rem;
    font-weight: 600;
    color: #111827;
    margin-bottom: 0.25rem;
}
.upload-label-secondary {
    font-size: 0.8125rem;
    color: #6b7280;
    margin-top: 0.75rem;
    margin-bottom: 0.25rem;
}

/* ── File uploader compact ───────────────────────── */
[data-testid="stFileUploaderDropzone"] {
    padding: 0.75rem 1rem !important;
    min-height: unset !important;
}
[data-testid="stFileUploaderDropzone"] small {
    font-size: 0.625rem !important;
    color: #d1d5db !important;
}

/* ── Divider lighter ─────────────────────────────── */
hr {
    border-color: #f3f4f6 !important;
    margin: 0.875rem 0 !important;
}

/* ── Streamlit toolbar: reduce visual prominence ─── */
[data-testid="stHeader"] {
    background: rgba(255,255,255,0.97) !important;
    box-shadow: none !important;
    border-bottom: 1px solid #f3f4f6 !important;
}

/* ── Review thread header (compact inline row) ───── */
.review-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0.625rem 0;
    border-bottom: 1px solid #e5e7eb;
    margin-bottom: 0.75rem;
    flex-wrap: wrap;
}
.rh-filename {
    font-size: 0.875rem;
    font-weight: 600;
    color: #111827;
}
.rh-sep { color: #d1d5db; }
.rh-version {
    font-size: 0.8125rem;
    color: #6b7280;
}
.rh-count {
    font-size: 0.75rem;
    color: #9ca3af;
    margin-left: auto;
}

/* ── Badges ─────────────────────────────────────── */
.badge {
    display: inline-block;
    font-size: 0.6875rem;
    font-weight: 600;
    padding: 2px 7px;
    border-radius: 4px;
    letter-spacing: 0.01em;
    white-space: nowrap;
    vertical-align: middle;
    line-height: 1.4;
}
.badge-needs-revision  { background:#fef2f2; color:#991b1b; border:1px solid #fecaca; }
.badge-open-decision   { background:#fffbeb; color:#92400e; border:1px solid #fcd34d; }
.badge-can-defer       { background:#eff6ff; color:#1e40af; border:1px solid #bfdbfe; }
.badge-resolved        { background:#f0fdf4; color:#166534; border:1px solid #bbf7d0; }
.badge-partial         { background:#fffbeb; color:#92400e; border:1px solid #fcd34d; }
.badge-unresolved      { background:#fef2f2; color:#991b1b; border:1px solid #fecaca; }
.badge-irrelevant      { background:#f9fafb; color:#6b7280; border:1px solid #e5e7eb; }

.status-badge { font-size: 0.6875rem; padding: 2px 7px; }
.status-needs-revision   { background:#fef2f2; color:#991b1b; border:1px solid #fecaca; }
.status-ready            { background:#f0fdf4; color:#166534; border:1px solid #bbf7d0; }
.status-open-decisions   { background:#fffbeb; color:#92400e; border:1px solid #fcd34d; }

/* ── Review output section headers ──────────────── */
.section-header {
    font-size: 0.625rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #9ca3af;
    margin-top: 1.25rem;
    margin-bottom: 0.625rem;
    padding-bottom: 0.375rem;
    border-bottom: 1px solid #f3f4f6;
}

/* ── Revision counts bar ─────────────────────────── */
.revision-counts {
    font-size: 0.8125rem;
    color: #374151;
    margin-bottom: 0.875rem;
    line-height: 1.5;
}

/* ── Finding cards ───────────────────────────────── */
.finding-card {
    border: 1px solid #e5e7eb;
    border-radius: 5px;
    padding: 0.625rem 0.875rem;
    margin-bottom: 0.5rem;
    background: #fff;
}
.finding-card-needs-revision { border-left: 3px solid #fca5a5; }
.finding-card-open-decision  { border-left: 3px solid #fcd34d; }
.finding-card-can-defer      { border-left: 3px solid #93c5fd; }
.finding-card-resolved       { border-left: 3px solid #86efac; }
.finding-card-partial        { border-left: 3px solid #fcd34d; }
.finding-card-unresolved     { border-left: 3px solid #fca5a5; }
.finding-card-irrelevant     { border-left: 3px solid #e5e7eb; }

.finding-card-header {
    display: flex;
    align-items: baseline;
    gap: 7px;
    margin-bottom: 0.375rem;
    flex-wrap: wrap;
}
.finding-title {
    font-weight: 600;
    font-size: 0.875rem;
    color: #111827;
}
.finding-card-body {
    font-size: 0.8125rem;
    color: #374151;
    line-height: 1.6;
}
.finding-card-body p          { margin: 0.25rem 0; }
.finding-card-body p:first-child { margin-top: 0; }

/* ===== FINAL SIDEBAR ALIGNMENT OVERRIDES ===== */

/* Align sidebar content vertically with the main workspace below
   Streamlit's native top header. */
[data-testid="stSidebarUserContent"] {
    padding-top: 3rem !important;
}

/* Every history button occupies the same full-width row. */
[data-testid="stSidebar"] .stButton {
    width: 100% !important;
}

[data-testid="stSidebar"] .stButton > button:not([kind="primary"]) {
    display: block !important;
    width: 100% !important;
    box-sizing: border-box !important;
    padding: 0.35rem 0.5rem !important;
    text-align: left !important;
}

/* Streamlit nests the button label in several containers.
   Force every layer to the full row width and left-align it. */
[data-testid="stSidebar"] .stButton > button:not([kind="primary"]) > div,
[data-testid="stSidebar"] .stButton > button:not([kind="primary"]) [data-testid="stMarkdownContainer"],
[data-testid="stSidebar"] .stButton > button:not([kind="primary"]) [data-testid="stMarkdownContainer"] p {
    display: block !important;
    width: 100% !important;
    max-width: none !important;
    margin: 0 !important;
    padding: 0 !important;
    text-align: left !important;
    justify-content: flex-start !important;
}

/* Same grid for selected review. */
.nav-item-active {
    width: 100% !important;
    box-sizing: border-box !important;
    padding: 0.35rem 0.5rem !important;
    text-align: left !important;
}

.nav-title,
.nav-meta {
    width: 100% !important;
    text-align: left !important;
}

/* Review History label uses the same starting edge. */
.sidebar-section-label {
    padding-left: 0.5rem !important;
}


/* ===== FINAL TOP-HEADER LAYOUT FIX ===== */

/*
Keep Streamlit's native header as a real top bar.
Both the sidebar workspace and the main workspace begin below it.
*/
:root {
    --pmr-header-height: 3.75rem;
    --pmr-top-gap: 1.25rem;
}

header[data-testid="stHeader"] {
    height: var(--pmr-header-height) !important;
}

/* Main workspace
   Streamlit's main content already carries additional internal spacing,
   so use a smaller top offset than the sidebar to align their first
   visible content rows. */
.block-container {
    padding-top: var(--pmr-header-height) !important;
}

/* Sidebar workspace */
[data-testid="stSidebarUserContent"] {
    padding-top: calc(
        var(--pmr-header-height) + var(--pmr-top-gap)
    ) !important;
}

/*
The sidebar collapse control stays inside the native header area;
it must not consume vertical space above PM Reviewer.
*/
[data-testid="stSidebarHeader"] {
    position: absolute !important;
    top: 0.75rem !important;
    right: 0.75rem !important;
    left: auto !important;
    width: auto !important;
    height: auto !important;
    min-height: 0 !important;
    padding: 0 !important;
    z-index: 10 !important;
}

</style>
""",
        unsafe_allow_html=True,
    )


# ==================================================
# FEEDBACK UI
# ==================================================

def render_feedback(review_id: int):
    """Render feedback controls for the latest version in a thread."""

    st.divider()
    _render_section_header("Feedback")

    saved_review = get_review(review_id)

    existing_rating = ""
    existing_comment = ""

    if saved_review:
        existing_rating = saved_review.get("feedback_rating") or ""
        existing_comment = saved_review.get("feedback_comment") or ""

    edit_key = f"edit_feedback_comment_{review_id}"

    if edit_key not in st.session_state:
        st.session_state[edit_key] = False

    if existing_rating:

        st.success("Feedback submitted.")
        st.write(f"**Rating:** {existing_rating}")

        if st.session_state[edit_key]:

            edit_text_key = f"edit_comment_text_{review_id}"

            if edit_text_key not in st.session_state:
                st.session_state[edit_text_key] = existing_comment

            edited_comment = st.text_area(
                "Comment",
                key=edit_text_key,
                height=80,
            )

            original_clean = existing_comment.strip()
            edited_clean = edited_comment.strip()
            has_changed = edited_clean != original_clean

            col1, col2 = st.columns([1, 1])

            with col1:
                if st.button(
                    "Save changes",
                    key=f"save_comment_edit_{review_id}",
                    use_container_width=True,
                    disabled=not has_changed,
                ):
                    save_feedback(review_id, existing_rating, edited_clean)
                    st.session_state[edit_key] = False
                    if edit_text_key in st.session_state:
                        del st.session_state[edit_text_key]
                    st.toast("Comment updated.")
                    st.rerun()

            with col2:
                if st.button(
                    "Cancel",
                    key=f"cancel_comment_edit_{review_id}",
                    use_container_width=True,
                ):
                    st.session_state[edit_key] = False
                    if edit_text_key in st.session_state:
                        del st.session_state[edit_text_key]
                    st.rerun()

        else:

            if existing_comment:
                st.write("**Comment:**")
                st.write(existing_comment)
                edit_label = "Edit comment"
            else:
                st.caption("No comment provided.")
                edit_label = "Add comment"

            if st.button(
                edit_label,
                key=f"edit_comment_{review_id}",
            ):
                st.session_state[edit_key] = True
                st.rerun()

        if existing_comment and not st.session_state[edit_key]:
            if st.button(
                "Use comment as reviewer rule",
                key=f"promote_feedback_{review_id}",
            ):
                added = add_reviewer_preference(existing_comment)
                if added:
                    st.toast("Reviewer rule added.")
                else:
                    st.toast("This reviewer rule is already active.")
                st.rerun()

    else:

        rating_key = f"feedback_rating_{review_id}"
        comment_key = f"feedback_comment_{review_id}"

        feedback_rating = st.radio(
            "Was this review useful?",
            ["Useful", "Needs improvement"],
            index=None,
            key=rating_key,
        )

        feedback_comment = st.text_area(
            "Optional comment",
            placeholder=(
                "What was useful, incorrect, "
                "too severe, or missing?"
            ),
            key=comment_key,
            height=80,
        )

        if st.button(
            "Submit feedback",
            key=f"submit_feedback_{review_id}",
            disabled=feedback_rating is None,
        ):
            save_feedback(review_id, feedback_rating, feedback_comment.strip())

            if rating_key in st.session_state:
                del st.session_state[rating_key]
            if comment_key in st.session_state:
                del st.session_state[comment_key]

            st.toast("Feedback submitted.")
            st.rerun()


# ==================================================
# REVISION UI
# ==================================================

def render_revision_uploader(latest_review: dict):
    """Allow a revised version to be reviewed inside the same thread."""

    with st.expander("Upload revised version", expanded=False):

        revision_key = (
            f"{latest_review['id']}_"
            f"{st.session_state.revision_session}"
        )

        revised_file = st.file_uploader(
            "Revised work",
            type=["txt", "md", "docx"],
            key=f"revision_file_{revision_key}",
        )

        revision_support = st.file_uploader(
            "Supporting material for this revision (optional)",
            type=["txt", "md", "docx"],
            key=f"revision_support_{revision_key}",
        )

        revision_context = st.text_area(
            "Revision context (optional)",
            placeholder="e.g. Calculations updated; compliance sourcing still pending.",
            height=70,
            key=f"revision_context_{revision_key}",
        )

        if st.button(
            "Review revised version",
            key=f"review_revision_{revision_key}",
            type="primary",
        ):

            if revised_file is None:
                st.warning("Please upload the revised work first.")
                return

            try:
                revised_text = extract_prd_text(revised_file)

                support_name = ""
                support_bytes = None

                if revision_support is not None:
                    support_name = revision_support.name
                    support_bytes = revision_support.getvalue()

                with st.spinner("Comparing the revised version..."):
                    result = run_revision_agent(
                        previous_text=latest_review["prd_text"],
                        previous_review=latest_review["review_output"],
                        revised_text=revised_text,
                        support_name=support_name,
                        support_bytes=support_bytes,
                        review_context=revision_context.strip(),
                    )

                next_version = int(latest_review["version_number"]) + 1

                review_id = save_completed_review(
                    result=result,
                    prd_filename=revised_file.name,
                    prd_text=revised_text,
                    review_context=revision_context.strip(),
                    thread_id=latest_review["thread_id"],
                    version_number=next_version,
                    review_kind="revision",
                )

                st.session_state.current_review_id = review_id
                st.session_state.prd_text = revised_text
                st.session_state.prd_filename = revised_file.name
                st.session_state.review_context = revision_context.strip()
                st.session_state.agent_result = result
                st.session_state.revision_session += 1

                st.rerun()

            except Exception as e:
                st.error(f"Revision review failed: {e}")


# ==================================================
# DATABASE
# ==================================================

init_db()


# ==================================================
# SESSION STATE
# ==================================================

if "agent_result" not in st.session_state:
    st.session_state.agent_result = None

if "prd_text" not in st.session_state:
    st.session_state.prd_text = ""

if "prd_filename" not in st.session_state:
    st.session_state.prd_filename = ""

if "support_name" not in st.session_state:
    st.session_state.support_name = ""

if "support_bytes" not in st.session_state:
    st.session_state.support_bytes = None

if "current_review_id" not in st.session_state:
    st.session_state.current_review_id = None

if "current_thread_id" not in st.session_state:
    st.session_state.current_thread_id = None

if "review_session" not in st.session_state:
    st.session_state.review_session = 0

if "revision_session" not in st.session_state:
    st.session_state.revision_session = 0

if "review_context" not in st.session_state:
    st.session_state.review_context = ""


# ==================================================
# CSS INJECTION
# ==================================================

inject_css()


# ==================================================
# SIDEBAR
# ==================================================

st.sidebar.markdown(
    '<div class="sidebar-wordmark">PM Reviewer</div>'
    '<div class="sidebar-tagline">AI review copilot</div>',
    unsafe_allow_html=True,
)

st.sidebar.markdown("")

if st.sidebar.button(
    "New review",
    use_container_width=True,
    type="primary",
):
    start_new_review()
    st.rerun()

st.sidebar.markdown(
    '<div class="sidebar-section-label">Review History</div>',
    unsafe_allow_html=True,
)

review_threads = get_review_threads()

if not review_threads:
    st.sidebar.caption("No saved reviews yet.")
else:
    for thread in review_threads:

        is_active = (
            thread["thread_id"] == st.session_state.current_thread_id
        )
        display_title = _derive_display_title(thread["thread_title"])
        status = extract_overall_status(thread["latest_review_output"])
        meta_text = f"v{thread['latest_version']}"
        if status:
            meta_text += f" · {status}"

        if is_active:
            st.sidebar.markdown(
                f'<div class="nav-item-active">'
                f'<span class="nav-title">{_escape_html(display_title)}</span>'
                f'<span class="nav-meta">{_escape_html(meta_text)}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            if st.sidebar.button(
                f"{display_title}\n{meta_text}",
                key=f"thread_{thread['thread_id']}",
                use_container_width=True,
            ):
                load_saved_thread(thread["thread_id"])
                st.rerun()

st.sidebar.divider()

with st.sidebar.expander("Reviewer preferences"):

    reviewer_preferences = get_reviewer_preferences()

    if not reviewer_preferences:
        st.caption("No reusable reviewer rules yet.")
    else:
        for preference in reviewer_preferences:
            st.write(preference["preference_text"])
            if st.button(
                "Remove",
                key=f"remove_preference_{preference['id']}",
                use_container_width=True,
            ):
                remove_reviewer_preference(preference["id"])
                st.rerun()


# ==================================================
# NEW REVIEW
# ==================================================

if (
    st.session_state.current_thread_id is None
    and st.session_state.agent_result is None
):

    st.markdown(
        '<h3 style="margin-top:0;margin-bottom:0.15rem;font-size:1.125rem;'
        'font-weight:600;color:#111827;">Review new work</h3>'
        '<p style="margin:0 0 0.2rem 0;font-size:0.8125rem;color:#6b7280;">'
        'Upload product work for a manager-level review.</p>'
        '<p style="margin:0 0 1.25rem 0;font-size:0.75rem;color:#9ca3af;">'
        'Returns prioritized findings and recommended next actions.'
        '</p>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="upload-label-primary">Work to review</div>',
        unsafe_allow_html=True,
    )
    prd_file = st.file_uploader(
        "Work to review",
        type=["txt", "md", "docx"],
        label_visibility="collapsed",
        key=f"prd_file_{st.session_state.review_session}",
    )

    st.markdown(
        '<div class="upload-label-secondary">'
        'Supporting material '
        '<span style="color:#9ca3af;font-weight:400;">(optional)</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    support_file = st.file_uploader(
        "Supporting material",
        type=["txt", "md", "docx"],
        label_visibility="collapsed",
        key=f"support_file_{st.session_state.review_session}",
    )

    review_context = st.text_area(
        "Review context (optional)",
        value=st.session_state.review_context,
        placeholder="e.g. Early research; engineering feasibility is still pending.",
        height=70,
        key=f"review_context_input_{st.session_state.review_session}",
    )

    st.session_state.review_context = review_context

    if st.button("Review work", type="primary"):

        if prd_file is None:
            st.warning("Please upload work to review first.")
        else:
            try:
                prd_text = extract_prd_text(prd_file)

                st.session_state.prd_text = prd_text
                st.session_state.prd_filename = prd_file.name

                if support_file is not None:
                    st.session_state.support_name = support_file.name
                    st.session_state.support_bytes = support_file.getvalue()
                else:
                    st.session_state.support_name = ""
                    st.session_state.support_bytes = None

                with st.spinner("Reviewing work..."):
                    result = run_agent(
                        prd_text,
                        st.session_state.support_name,
                        st.session_state.support_bytes,
                        st.session_state.review_context,
                    )

                st.session_state.agent_result = result

                if result["status"] == "REVIEW":

                    review_id = save_completed_review(
                        result=result,
                        prd_filename=st.session_state.prd_filename,
                        prd_text=st.session_state.prd_text,
                        review_context=st.session_state.review_context,
                    )

                    saved = get_review(review_id)
                    st.session_state.current_review_id = review_id
                    st.session_state.current_thread_id = saved["thread_id"]
                    st.rerun()

            except Exception as e:
                st.error(f"Review failed: {e}")


# ==================================================
# DISPLAY SAVED REVIEW THREAD
# ==================================================

if st.session_state.current_thread_id is not None:

    versions = get_thread_reviews(st.session_state.current_thread_id)

    if versions:

        latest = versions[-1]
        root = versions[0]

        thread_status = extract_overall_status(latest["review_output"])

        render_review_thread_header(
            latest=latest,
            root=root,
            thread_status=thread_status,
            version_count=len(versions),
        )

        # Revision is the primary next action for an existing review,
        # so keep it directly under the header.
        render_revision_uploader(latest)

        st.divider()

        if latest.get("review_context"):
            st.caption("Review context: " + latest["review_context"])

        if latest.get("supporting_evidence_used"):
            st.info(
                "Supporting material was inspected as part of this review."
            )

        render_review_output(latest["review_output"])

        # Keep older versions accessible but subordinate.
        if len(versions) > 1:

            st.divider()
            st.markdown("**Previous versions**")

            for old_version in reversed(versions[:-1]):

                with st.expander(
                    f"v{old_version['version_number']} · "
                    f"{_derive_display_title(old_version['prd_filename'])}",
                    expanded=False,
                ):
                    if old_version.get("review_context"):
                        st.caption(
                            "Review context: " + old_version["review_context"]
                        )

                    if old_version.get("supporting_evidence_used"):
                        st.info(
                            "Supporting material was inspected "
                            "as part of this review."
                        )

                    render_review_output(old_version["review_output"])

                    if old_version.get("feedback_rating"):
                        st.caption(
                            "Feedback: " + old_version["feedback_rating"]
                        )

        render_feedback(latest["id"])


# ==================================================
# UNSAVED AGENT RESULT (ASK / ERROR)
# ==================================================

elif st.session_state.agent_result:

    result = st.session_state.agent_result

    if result["status"] == "ASK":

        st.subheader("More information needed")

        st.markdown(
            escape_dollar_signs_for_markdown(result["message"])
        )

        answers = st.text_area(
            "Provide clarification",
            height=180,
            key=f"clarification_{st.session_state.review_session}",
        )

        if st.button(
            "Continue review",
            key=f"continue_review_{st.session_state.review_session}",
            type="primary",
        ):

            if not answers.strip():
                st.warning("Please provide the requested clarification.")
            else:

                combined_context = f"""
{st.session_state.prd_text}

ADDITIONAL CLARIFICATION PROVIDED BY THE PM:

{answers}
"""

                with st.spinner("Continuing review..."):
                    try:
                        new_result = run_agent(
                            combined_context,
                            st.session_state.support_name,
                            st.session_state.support_bytes,
                            st.session_state.review_context,
                        )

                        st.session_state.agent_result = new_result

                        if new_result["status"] == "REVIEW":

                            review_id = save_completed_review(
                                result=new_result,
                                prd_filename=st.session_state.prd_filename,
                                prd_text=combined_context,
                                review_context=st.session_state.review_context,
                            )

                            saved = get_review(review_id)
                            st.session_state.current_review_id = review_id
                            st.session_state.current_thread_id = (
                                saved["thread_id"]
                            )

                        st.rerun()

                    except Exception as e:
                        st.error(f"Review failed: {e}")

    elif result["status"] == "ERROR":
        st.error(result["message"])
