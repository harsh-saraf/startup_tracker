"""Companies — wishlist / interested / not-interested / uncategorized tables
with inline editor + "Add Company" form.

Session-state reads/writes: see ``startup_radar.web.state`` for
``CO_*`` constants. Widget keys for editors + search live there too.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from startup_radar.web import state
from startup_radar.web.cache import get_storage, load_data
from startup_radar.web.lookup import lookup_company

storage = get_storage()

TODAY = datetime.now().strftime("%Y-%m-%d")
STATUS_OPTIONS = ["", "Interested", "Not Interested", "Applied", "Wishlist"]

df_startups, _ = load_data()


def _get_connections_for_companies(company_names):
    result = {}
    for name in company_names:
        conns = storage.search_connections_by_company(name)
        if not conns.empty:
            parts = []
            for _, c in conns.iterrows():
                full_name = f"{c['first_name']} {c['last_name']}".strip()
                pos = c.get("position", "")
                parts.append(f"{full_name} ({pos})" if pos else full_name)
            result[name] = ", ".join(parts)
        else:
            result[name] = ""
    return result


def _add_connections_col(frame, company_col="Company Name"):
    frame = frame.copy()
    if storage.get_connections_count() == 0:
        frame["Connections"] = ""
        return frame
    conn_map = _get_connections_for_companies(frame[company_col].tolist())
    frame["Connections"] = frame[company_col].map(conn_map).fillna("")
    return frame


def _add_delete_col(frame):
    frame = frame.copy()
    frame["\U0001f5d1\ufe0f"] = False
    return frame


st.title("Companies")

if st.button("+ Add Company", key=state.CO_ADD_BTN):
    st.session_state[state.CO_SHOW_ADD] = not st.session_state.get(state.CO_SHOW_ADD, False)
    st.session_state.pop(state.CO_LOOKUP, None)
    st.session_state.pop(state.CO_LOOKUP_VERSION, None)

if st.session_state.get(state.CO_SHOW_ADD):
    ac_name = st.text_input("Company Name *", key=state.CO_NAME_INPUT)
    if st.button("Lookup", key=state.CO_LOOKUP_BTN):
        if ac_name.strip():
            with st.spinner(f"Looking up {ac_name.strip()}..."):
                info = lookup_company(ac_name.strip())
            if info:
                st.session_state[state.CO_LOOKUP] = info
                st.session_state[state.CO_LOOKUP_VERSION] = (
                    st.session_state.get(state.CO_LOOKUP_VERSION, 0) + 1
                )
                st.rerun()
            else:
                st.warning("No results found. Fill in details manually.")
        else:
            st.error("Enter a company name first.")

    lookup = st.session_state.get(state.CO_LOOKUP, {})
    ver = st.session_state.get(state.CO_LOOKUP_VERSION, 0)
    with st.form(f"add_company_form_{ver}"):
        ac_desc = st.text_input("Description", value=lookup.get("description", ""))
        ac_stage = st.text_input("Funding Stage", value=lookup.get("funding_stage", ""))
        ac_amount = st.text_input("Amount Raised", value=lookup.get("amount_raised", ""))
        ac_loc = st.text_input("Location", value=lookup.get("location", ""))
        ac_submit = st.form_submit_button("Add Company")
    if ac_submit:
        if not ac_name.strip():
            st.error("Company Name is required.")
        else:
            inserted = storage.insert_startups(
                [
                    {
                        "company_name": ac_name.strip(),
                        "description": ac_desc.strip(),
                        "funding_stage": ac_stage.strip(),
                        "amount_raised": ac_amount.strip(),
                        "location": ac_loc.strip(),
                        "source": "Manual",
                        "date_found": TODAY,
                        "status": "",
                    }
                ]
            )
            if inserted:
                st.session_state[state.CO_SHOW_ADD] = False
                st.session_state.pop(state.CO_LOOKUP, None)
                st.session_state.pop(state.CO_LOOKUP_VERSION, None)
                load_data.clear()
                st.rerun()
            else:
                st.warning(f"'{ac_name.strip()}' already exists.")

search = st.text_input("Search", placeholder="Company name or keyword...", key=state.CO_SEARCH)
filtered = df_startups.copy()
if search:
    mask = filtered["Company Name"].str.contains(search, case=False, na=False) | filtered[
        "Description"
    ].str.contains(search, case=False, na=False)
    filtered = filtered[mask]

status_lower = filtered["Status"].str.strip().str.lower()
wishlist = filtered[status_lower == "wishlist"]
interested_co = filtered[status_lower == "interested"]
not_interested = filtered[status_lower == "not interested"]
uncategorized = filtered[
    ~status_lower.isin(["applied", "wishlist", "interested", "not interested"])
]

_col_config = {
    "Website": st.column_config.LinkColumn(
        "Website", display_text=r"https?://(?:www\.)?([^/]+)", width="small"
    ),
    "Status": st.column_config.SelectboxColumn("Status", options=STATUS_OPTIONS, width="medium"),
    "Connections": st.column_config.TextColumn("Connections", width="medium"),
    "\U0001f5d1\ufe0f": st.column_config.CheckboxColumn("\U0001f5d1\ufe0f", width="small"),
}


def _persist_company_changes(original_df, edited_df):
    changed = False
    for idx in edited_df.index:
        if idx not in original_df.index:
            continue
        company = original_df.loc[idx, "Company Name"]
        if edited_df.loc[idx, "\U0001f5d1\ufe0f"]:
            storage.delete_startup(company)
            changed = True
            continue
        old = original_df.loc[idx, "Status"]
        new = edited_df.loc[idx, "Status"]
        if old != new:
            storage.update_startup_status(company, new)
            if new == "Applied":
                ts = storage.get_tracker_status(company)
                if not ts:
                    storage.upsert_tracker_status(company, "Applied", "", "")
                    storage.insert_activity(
                        {
                            "company_name": company,
                            "role_title": "",
                            "activity_type": "Applied",
                            "contact_name": "",
                            "contact_title": "",
                            "contact_email": "",
                            "date": TODAY,
                            "follow_up_date": "",
                            "notes": "",
                        }
                    )
            changed = True
    if changed:
        load_data.clear()
    return changed


_needs_rerun = False

st.subheader(f"Wishlist ({len(wishlist)})")
if wishlist.empty:
    st.caption("No wishlisted companies yet.")
else:
    edited_wl = st.data_editor(
        _add_delete_col(_add_connections_col(wishlist)),
        column_config=_col_config,
        hide_index=True,
        use_container_width=True,
        disabled=[],
        key=state.CO_WISHLIST_EDITOR,
    )
    if _persist_company_changes(wishlist, edited_wl):
        _needs_rerun = True

st.divider()

st.subheader(f"Interested ({len(interested_co)})")
if interested_co.empty:
    st.caption("No companies marked as interested yet.")
else:
    edited_int = st.data_editor(
        _add_delete_col(_add_connections_col(interested_co)),
        column_config=_col_config,
        hide_index=True,
        use_container_width=True,
        disabled=[],
        key=state.CO_INTERESTED_EDITOR,
    )
    if _persist_company_changes(interested_co, edited_int):
        _needs_rerun = True

st.divider()

with st.expander(f"Not Interested ({len(not_interested)})"):
    if not_interested.empty:
        st.caption("No companies marked as not interested.")
    else:
        edited_ni = st.data_editor(
            _add_delete_col(not_interested),
            column_config=_col_config,
            hide_index=True,
            use_container_width=True,
            disabled=[],
            key=state.CO_NOT_INTERESTED_EDITOR,
        )
        if _persist_company_changes(not_interested, edited_ni):
            _needs_rerun = True

st.divider()

st.subheader(f"Uncategorized ({len(uncategorized)})")
if uncategorized.empty:
    st.caption("All companies have been categorized.")
else:
    edited_unc = st.data_editor(
        _add_delete_col(uncategorized),
        column_config=_col_config,
        hide_index=True,
        use_container_width=True,
        disabled=[],
        key=state.CO_UNCATEGORIZED_EDITOR,
    )
    if _persist_company_changes(uncategorized, edited_unc):
        _needs_rerun = True

if _needs_rerun:
    st.rerun()
