"""Session-state + widget key constants.

Per ``.claude/rules/dashboard.md`` bullet 2: pages import these; never use
string literals. Namespaced prefixes (``co_``, ``dd_``, ``ap_``, ``al_``)
mirror the page they belong to so the ``dd_name_input`` / ``ac_name_input``
collision noted at the former ``app.py:702`` cannot silently recur.
"""

from __future__ import annotations

# Sidebar --------------------------------------------------------------------
LI_CSV_UPLOAD = "li_csv_upload"

# Page 2 — Companies ---------------------------------------------------------
CO_SHOW_ADD = "show_add_company"
CO_ADD_BTN = "add_company_btn"
CO_LOOKUP = "co_lookup"
CO_LOOKUP_VERSION = "co_lookup_v"
CO_SEARCH = "co_search"
CO_NAME_INPUT = "ac_name_input"
CO_LOOKUP_BTN = "co_lookup_btn"
CO_WISHLIST_EDITOR = "wishlist_editor"
CO_INTERESTED_EDITOR = "interested_editor"
CO_NOT_INTERESTED_EDITOR = "not_interested_editor"
CO_UNCATEGORIZED_EDITOR = "uncategorized_editor"

# Page 3 — Jobs --------------------------------------------------------------
JOB_SHOW_ADD = "show_add_role"
JOB_ADD_BTN = "add_role_btn"
JOB_SEARCH = "job_search"
JOB_WL_EDITOR = "wl_jobs_editor"
JOB_INT_EDITOR = "int_jobs_editor"
JOB_NI_EDITOR = "ni_jobs_editor"
JOB_UNC_EDITOR = "unc_jobs_editor"

# Page 4 — DeepDive ----------------------------------------------------------
DD_SHOW_ADD = "show_add_company_dd"
DD_ADD_BTN = "add_company_dd_btn"
DD_LOOKUP = "dd_lookup"
DD_LOOKUP_VERSION = "dd_lookup_v"
DD_NAME_INPUT = "dd_name_input"  # distinct from CO_NAME_INPUT — collision check below
DD_LOOKUP_BTN = "dd_lookup_btn"
DD_SELECT = "deepdive_select"
DD_GEN_BTN = "deepdive_btn"
DD_WARM_BTN = "warm_intros_btn"
DD_WARM_EDITOR = "warm_intros_editor"
DD_GENERATING = "generating"
DD_GEN_PROC = "gen_proc"
DD_GEN_START = "gen_start"
DD_SHOW_WARM = "show_warm_intros"

# Page 5 — Application Tracker ----------------------------------------------
AP_SHOW_ADD_ACTIVITY = "show_add_activity"
AP_ADD_ACTIVITY_BTN = "add_activity_btn"
AP_SHOW_ADD_APPLIED = "show_add_applied"
AP_ADD_APPLIED_BTN = "add_applied_btn"
AP_SHOW_ADD_LOG = "show_add_activity_log"
AP_ADD_LOG_BTN = "add_activity_log_btn"
AP_COMPANY = "ap_company"
AP_ROLE = "ap_role"
AP_STATUS = "ap_status"
AP_CONTACT = "ap_contact"
AP_CONTACT_TITLE = "ap_contact_title"
AP_DATE = "ap_date"
AP_NOTES = "ap_notes"
AL_COMPANY = "al_company"
AL_NEW = "al_new"
AL_ROLE = "al_role"
AL_TYPE = "al_type"
AL_CONTACT = "al_contact"
AL_CONTACT_TITLE = "al_contact_title"
AL_EMAIL = "al_email"
AL_DATE = "al_date"
AL_FOLLOWUP = "al_followup"
AL_NOTES = "al_notes"
AP_APPLIED_EDITOR = "tracker_applied_editor"
AP_ACTIVE_EDITOR = "tracker_active_editor"
AP_REJECTED_EDITOR = "rejected_tracker_editor"


ALL_KEYS: tuple[str, ...] = tuple(
    v for k, v in dict(globals()).items() if k.isupper() and isinstance(v, str)
)


def assert_no_collisions() -> None:
    """Fail loud at import time if two constants map to the same string."""
    if len(ALL_KEYS) != len(set(ALL_KEYS)):
        dupes = sorted({k for k in ALL_KEYS if ALL_KEYS.count(k) > 1})
        raise AssertionError(f"session-state key collision: {dupes}")


assert_no_collisions()
