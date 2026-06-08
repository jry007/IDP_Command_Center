import os
import requests
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
from dotenv import load_dotenv
from pathlib import Path
from config import NOTION_DB, CASH_FIELDS, STAGE_COLORS, PRIORITY_COLORS

load_dotenv(Path(__file__).parent / ".env")

st.set_page_config(
    page_title="IDP Command Center",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styles ────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #0f0f1a; }
[data-testid="stSidebar"] { background: #13131f; border-right: 1px solid #2a2a3e; }
.metric-card {
    background: linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);
    border: 1px solid #2a2a4a;
    border-radius: 12px;
    padding: 18px 20px;
    text-align: center;
}
.metric-card h2 { color: #a78bfa; font-size: 2rem; margin: 0 0 4px; }
.metric-card p  { color: #64748b; margin: 0; font-size: 0.85rem; letter-spacing:.05em; text-transform:uppercase; }
.panel-card {
    background: #1a1a2e;
    border: 1px solid #2a2a4a;
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 10px;
}
.stage-badge {
    display:inline-block; padding:3px 10px; border-radius:20px;
    font-size:.75rem; font-weight:600;
}
.priority-high   { background:#450a0a; color:#fca5a5; border-radius:6px; padding:2px 8px; font-size:.75rem; }
.priority-medium { background:#451a03; color:#fcd34d; border-radius:6px; padding:2px 8px; font-size:.75rem; }
.priority-low    { background:#0c1a3a; color:#93c5fd; border-radius:6px; padding:2px 8px; font-size:.75rem; }
.section-header  { color:#a78bfa; font-size:1.1rem; font-weight:700; margin-bottom:12px; border-bottom:1px solid #2a2a4a; padding-bottom:8px; }
</style>
""", unsafe_allow_html=True)

# ── Notion REST helpers ───────────────────────────────────────────────────────

def _notion_headers():
    return {
        "Authorization": f"Bearer {os.getenv('NOTION_TOKEN')}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

def notion_query(db_id, sorts=None, filters=None):
    """Query a Notion database via REST API (no SDK dependency)."""
    token = os.getenv("NOTION_TOKEN")
    if not token:
        return []
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    body = {}
    if sorts:
        body["sorts"] = sorts
    if filters:
        body["filter"] = filters
    results, cursor = [], None
    try:
        while True:
            if cursor:
                body["start_cursor"] = cursor
            resp = requests.post(url, headers=_notion_headers(), json=body, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            results.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            cursor = data["next_cursor"]
        return results
    except Exception as e:
        st.error(f"Notion error: {e}")
        return []

def notion_update(page_id, properties):
    """Update a Notion page via REST API."""
    requests.patch(
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=_notion_headers(),
        json={"properties": properties},
        timeout=15,
    )

def notion_create(db_id, properties):
    """Create a new page in a Notion database via REST API."""
    requests.post(
        "https://api.notion.com/v1/pages",
        headers=_notion_headers(),
        json={"parent": {"database_id": db_id}, "properties": properties},
        timeout=15,
    )

# ── Property extractor ────────────────────────────────────────────────────────

def get_prop(page, key, default=None):
    props = page.get("properties", {})
    if key not in props:
        return default
    p = props[key]
    t = p.get("type")
    if t == "title":
        items = p.get("title", [])
        return items[0]["plain_text"] if items else default
    if t == "rich_text":
        items = p.get("rich_text", [])
        return items[0]["plain_text"] if items else default
    if t == "number":
        return p.get("number", default)
    if t == "select":
        s = p.get("select")
        return s["name"] if s else default
    if t == "date":
        d = p.get("date")
        return d["start"] if d else default
    if t == "checkbox":
        return p.get("checkbox", False)
    return default

@st.cache_data(ttl=300)
def fetch_db(db_id, sorts=None, filters=None):
    return notion_query(db_id, sorts=sorts, filters=filters)

# ── Sidebar ───────────────────────────────────────────────────────────────────

notion_ok = bool(os.getenv("NOTION_TOKEN"))

with st.sidebar:
    st.markdown("## 🎯 IDP Command Center")
    if not notion_ok:
        st.warning("No NOTION_TOKEN in .env")
    st.markdown("---")
    page = st.radio("Navigation", [
        "📊 Dashboard",
        "🏨 HGI Night Audit",
        "💰 Cash Position",
        "📋 Deal Pipeline",
        "✅ Action Items",
        "📁 Portfolio Reports",
    ], label_visibility="collapsed")
    st.markdown("---")
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"Last loaded: {datetime.now().strftime('%b %d %H:%M')}")

# ── Page: Dashboard ───────────────────────────────────────────────────────────

if page == "📊 Dashboard":
    st.title("📊 IDP Command Center")

    # Top metrics row — pull latest records
    cash_rows    = fetch_db(NOTION_DB["cash_position"],   sorts=[{"property":"Date","direction":"descending"}])
    hgi_rows     = fetch_db(NOTION_DB["hgi_daily_metrics"], sorts=[{"property":"Date","direction":"descending"}])
    deals        = fetch_db(NOTION_DB["deal_pipeline"])
    action_items = fetch_db(NOTION_DB["action_items"],
                            filters={"property":"Status","select":{"does_not_equal":"Done"}})

    latest_cash   = cash_rows[0]   if cash_rows   else None
    latest_hgi    = hgi_rows[0]    if hgi_rows    else None
    total_cash    = get_prop(latest_cash, "Total Cash", 0) if latest_cash else 0
    occ           = get_prop(latest_hgi,  "Occupancy %", 0) if latest_hgi  else 0
    rev_par       = get_prop(latest_hgi,  "RevPAR",      0) if latest_hgi  else 0
    open_actions  = len(action_items)
    active_deals  = sum(1 for d in deals if get_prop(d, "Stage") not in ("Closed","Dead",None))

    c1, c2, c3, c4, c5 = st.columns(5)
    for col, val, label in [
        (c1, f"${total_cash:,.0f}",  "Total Cash"),
        (c2, f"{occ*100:.1f}%",      "HGI Occupancy"),
        (c3, f"${rev_par:,.2f}",     "HGI RevPAR"),
        (c4, active_deals,           "Active Deals"),
        (c5, open_actions,           "Open Actions"),
    ]:
        with col:
            st.markdown(f'<div class="metric-card"><h2>{val}</h2><p>{label}</p></div>',
                        unsafe_allow_html=True)

    st.markdown("---")

    # Row 2: Cash breakdown + Deal stage funnel
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown('<div class="section-header">💰 Cash by Entity (Latest)</div>', unsafe_allow_html=True)
        if latest_cash:
            cash_data = [(f, get_prop(latest_cash, f, 0) or 0) for f in CASH_FIELDS]
            cash_data = [(k, v) for k, v in cash_data if v > 0]
            if cash_data:
                df_cash = pd.DataFrame(cash_data, columns=["Entity","Balance"])
                fig = px.bar(df_cash, x="Balance", y="Entity", orientation="h",
                             color="Balance", color_continuous_scale="Purples")
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  font_color="#94a3b8", margin=dict(t=10,b=10),
                                  coloraxis_showscale=False, height=300)
                fig.update_xaxes(tickprefix="$", tickformat=",.0f")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No cash position data yet.")

    with col_b:
        st.markdown('<div class="section-header">📋 Deal Pipeline by Stage</div>', unsafe_allow_html=True)
        if deals:
            stages = [get_prop(d,"Stage","Unknown") for d in deals]
            df_s = pd.Series(stages).value_counts().reset_index()
            df_s.columns = ["Stage","Count"]
            colors = [STAGE_COLORS.get(s,"#6b7280") for s in df_s["Stage"]]
            fig = px.bar(df_s, x="Stage", y="Count", color="Stage",
                         color_discrete_map=STAGE_COLORS)
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#94a3b8", margin=dict(t=10,b=10),
                              showlegend=False, height=300)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No deals yet.")

    # Row 3: HGI 7-day trend + Open action items
    col_c, col_d = st.columns(2)

    with col_c:
        st.markdown('<div class="section-header">🏨 HGI — 7-Day Revenue Trend</div>', unsafe_allow_html=True)
        if len(hgi_rows) >= 2:
            hgi_data = []
            for r in hgi_rows[:14]:
                hgi_data.append({
                    "Date":          get_prop(r, "Date"),
                    "Room Revenue":  get_prop(r, "Room Revenue", 0) or 0,
                    "F&B Revenue":   get_prop(r, "F&B Revenue",  0) or 0,
                    "Total Revenue": get_prop(r, "Total Revenue",0) or 0,
                })
            df_hgi = pd.DataFrame(hgi_data).sort_values("Date")
            fig = px.line(df_hgi, x="Date", y=["Room Revenue","F&B Revenue"],
                          color_discrete_map={"Room Revenue":"#a78bfa","F&B Revenue":"#34d399"})
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#94a3b8", margin=dict(t=10,b=10), height=300,
                              legend=dict(orientation="h", y=-0.2))
            fig.update_yaxes(tickprefix="$", tickformat=",.0f")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Not enough HGI data for trend.")

    with col_d:
        st.markdown('<div class="section-header">✅ Open Action Items</div>', unsafe_allow_html=True)
        if action_items:
            for item in sorted(action_items,
                               key=lambda x: {"High":0,"Medium":1,"Low":2}.get(get_prop(x,"Priority"),3))[:8]:
                title    = get_prop(item, "Action Item", "Untitled")
                priority = get_prop(item, "Priority", "—")
                category = get_prop(item, "Category", "—")
                due      = get_prop(item, "Due Date", "")
                pcls     = {"High":"priority-high","Medium":"priority-medium","Low":"priority-low"}.get(priority,"priority-low")
                due_str  = f" · Due {due}" if due else ""
                st.markdown(f"""
                <div class="panel-card" style="padding:10px 14px;margin-bottom:6px;">
                  <strong style="color:#e2e8f0">{title}</strong>
                  &nbsp;<span class="{pcls}">{priority}</span>
                  <br><small style="color:#475569">{category}{due_str}</small>
                </div>""", unsafe_allow_html=True)
        else:
            st.success("No open action items!")

# ── Page: HGI Night Audit ─────────────────────────────────────────────────────

elif page == "🏨 HGI Night Audit":
    st.title("🏨 Hilton Garden Inn — Daily Metrics")

    rows = fetch_db(NOTION_DB["hgi_daily_metrics"],
                    sorts=[{"property":"Date","direction":"descending"}])

    if not rows:
        st.info("No HGI data. Run the HGI audit agent to populate.")
    else:
        latest = rows[0]
        date_str = get_prop(latest, "Date", "Unknown")
        st.subheader(f"Latest Entry: {date_str}")

        c1,c2,c3,c4,c5 = st.columns(5)
        metrics = [
            ("Occupancy %",   get_prop(latest,"Occupancy %",0), True,  False),
            ("ADR",           get_prop(latest,"ADR",0),         False, True),
            ("RevPAR",        get_prop(latest,"RevPAR",0),      False, True),
            ("Room Revenue",  get_prop(latest,"Room Revenue",0),False, True),
            ("Total Revenue", get_prop(latest,"Total Revenue",0),False,True),
        ]
        for col, (label, val, is_pct, is_dollar) in zip([c1,c2,c3,c4,c5], metrics):
            val = val or 0
            if is_pct:
                disp = f"{val*100:.1f}%"
            elif is_dollar:
                disp = f"${val:,.0f}"
            else:
                disp = str(val)
            with col:
                st.markdown(f'<div class="metric-card"><h2>{disp}</h2><p>{label}</p></div>',
                            unsafe_allow_html=True)

        st.markdown("---")

        # Historical table
        hgi_data = []
        for r in rows[:30]:
            occ = get_prop(r, "Occupancy %", 0) or 0
            hgi_data.append({
                "Date":          get_prop(r, "Date"),
                "Occupancy":     f"{occ*100:.1f}%",
                "ADR":           f"${get_prop(r,'ADR',0) or 0:,.2f}",
                "RevPAR":        f"${get_prop(r,'RevPAR',0) or 0:,.2f}",
                "Rooms Sold":    get_prop(r, "Rooms Sold", 0),
                "Room Rev":      f"${get_prop(r,'Room Revenue',0) or 0:,.0f}",
                "F&B Rev":       f"${get_prop(r,'F&B Revenue',0) or 0:,.0f}",
                "Total Rev":     f"${get_prop(r,'Total Revenue',0) or 0:,.0f}",
                "Notes":         get_prop(r, "Notes", ""),
            })
        df = pd.DataFrame(hgi_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Trend charts
        col_a, col_b = st.columns(2)
        raw = []
        for r in rows[:30]:
            occ = get_prop(r,"Occupancy %",0) or 0
            raw.append({"Date":get_prop(r,"Date"),"Occupancy":occ*100,
                        "ADR":get_prop(r,"ADR",0) or 0,"RevPAR":get_prop(r,"RevPAR",0) or 0,
                        "Room Revenue":get_prop(r,"Room Revenue",0) or 0})
        df_raw = pd.DataFrame(raw).sort_values("Date")

        with col_a:
            st.subheader("Occupancy % — 30 Days")
            fig = px.line(df_raw, x="Date", y="Occupancy", markers=True,
                          color_discrete_sequence=["#a78bfa"])
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#94a3b8",margin=dict(t=10,b=10))
            fig.update_yaxes(ticksuffix="%")
            st.plotly_chart(fig, use_container_width=True)

        with col_b:
            st.subheader("ADR vs RevPAR — 30 Days")
            fig = px.line(df_raw, x="Date", y=["ADR","RevPAR"], markers=True,
                          color_discrete_map={"ADR":"#34d399","RevPAR":"#f59e0b"})
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#94a3b8",margin=dict(t=10,b=10))
            fig.update_yaxes(tickprefix="$")
            st.plotly_chart(fig, use_container_width=True)

# ── Page: Cash Position ───────────────────────────────────────────────────────

elif page == "💰 Cash Position":
    st.title("💰 Cash Position")

    rows = fetch_db(NOTION_DB["cash_position"],
                    sorts=[{"property":"Date","direction":"descending"}])

    if not rows:
        st.info("No cash data. Run the Xero cash agent to populate.")
    else:
        latest = rows[0]
        total  = get_prop(latest, "Total Cash", 0) or 0
        date_str = get_prop(latest, "Date", "Unknown")

        st.subheader(f"As of: {date_str}")
        st.markdown(f'<div class="metric-card" style="max-width:300px"><h2>${total:,.0f}</h2><p>Total Cash All Entities</p></div>',
                    unsafe_allow_html=True)
        st.markdown("---")

        # Entity breakdown
        breakdown = []
        for field in CASH_FIELDS:
            val = get_prop(latest, field, 0) or 0
            breakdown.append({"Entity": field.replace("Xero ",""), "Balance": val})
        df_b = pd.DataFrame(breakdown)

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Balance by Entity")
            fig = px.bar(df_b.sort_values("Balance",ascending=True),
                         x="Balance", y="Entity", orientation="h",
                         color="Balance", color_continuous_scale="Purples")
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#94a3b8",margin=dict(t=10,b=10),
                              coloraxis_showscale=False)
            fig.update_xaxes(tickprefix="$",tickformat=",.0f")
            st.plotly_chart(fig, use_container_width=True)

        with col_b:
            st.subheader("Share of Total")
            df_pie = df_b[df_b["Balance"] > 0]
            fig = px.pie(df_pie, names="Entity", values="Balance",
                         color_discrete_sequence=px.colors.sequential.Purples_r, hole=0.4)
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",font_color="#94a3b8",
                              margin=dict(t=10,b=10))
            st.plotly_chart(fig, use_container_width=True)

        # Entity table
        st.subheader("Entity Detail")
        df_b["Balance"] = df_b["Balance"].apply(lambda x: f"${x:,.2f}")
        st.dataframe(df_b, use_container_width=True, hide_index=True)

        # Historical trend
        if len(rows) > 1:
            st.subheader("Total Cash — Historical")
            hist = [{"Date": get_prop(r,"Date"), "Total Cash": get_prop(r,"Total Cash",0) or 0}
                    for r in rows[:60]]
            df_hist = pd.DataFrame(hist).sort_values("Date")
            fig = px.area(df_hist, x="Date", y="Total Cash",
                          color_discrete_sequence=["#a78bfa"])
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#94a3b8",margin=dict(t=10,b=10))
            fig.update_yaxes(tickprefix="$",tickformat=",.0f")
            st.plotly_chart(fig, use_container_width=True)

# ── Page: Deal Pipeline ───────────────────────────────────────────────────────

elif page == "📋 Deal Pipeline":
    st.title("📋 Deal Pipeline")

    rows = fetch_db(NOTION_DB["deal_pipeline"],
                    sorts=[{"property":"Deal Name","direction":"ascending"}])

    if not rows:
        st.info("No deals in pipeline.")
    else:
        # Filters
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            stage_filter = st.selectbox("Stage", ["All","Prospecting","LOI","Due Diligence","Under Contract","Closed","Dead"])
        with col_f2:
            type_filter = st.selectbox("Asset Type", ["All","Multifamily","Hotel","Assisted Living"])
        with col_f3:
            status_filter = st.selectbox("Status", ["All","Shopping","Underwriting","LOI Submitted","Under Contract","Closed","Dead"])

        filtered = rows
        if stage_filter  != "All": filtered = [r for r in filtered if get_prop(r,"Stage")  == stage_filter]
        if type_filter   != "All": filtered = [r for r in filtered if get_prop(r,"Asset Type") == type_filter]
        if status_filter != "All": filtered = [r for r in filtered if get_prop(r,"Status") == status_filter]

        st.caption(f"{len(filtered)} deal(s) shown")

        for deal in filtered:
            name     = get_prop(deal, "Deal Name",    "Untitled")
            stage    = get_prop(deal, "Stage",        "—")
            atype    = get_prop(deal, "Asset Type",   "—")
            asking   = get_prop(deal, "Asking Price", 0) or 0
            offer    = get_prop(deal, "Offer Amount", 0) or 0
            cap      = get_prop(deal, "Cap Rate",     0) or 0
            units    = get_prop(deal, "Units/Keys",   0) or 0
            market   = get_prop(deal, "Market",       "—")
            nxt      = get_prop(deal, "Next Action",  "")
            notes    = get_prop(deal, "Notes",        "")
            close_dt = get_prop(deal, "Target Close Date", "")
            broker   = get_prop(deal, "Broker Contact", "")
            s_color  = STAGE_COLORS.get(stage, "#6b7280")

            with st.expander(f"{name}  —  {atype}  ·  {market}"):
                c1,c2,c3,c4 = st.columns(4)
                c1.markdown(f'<span class="stage-badge" style="background:{s_color}22;color:{s_color};border:1px solid {s_color}44">{stage}</span>', unsafe_allow_html=True)
                c2.metric("Asking Price", f"${asking:,.0f}" if asking else "—")
                c3.metric("Offer",        f"${offer:,.0f}"  if offer  else "—")
                c4.metric("Cap Rate",     f"{cap*100:.2f}%" if cap    else "—")

                c5,c6,c7,c8 = st.columns(4)
                c5.metric("Units/Keys",   int(units) if units else "—")
                c6.metric("Target Close", close_dt or "—")
                c7.metric("Broker",       broker or "—")
                c8.metric("Asset Type",   atype)

                if nxt:
                    st.markdown(f"**Next Action:** {nxt}")
                if notes:
                    st.caption(notes)

# ── Page: Action Items ────────────────────────────────────────────────────────

elif page == "✅ Action Items":
    st.title("✅ Open Action Items")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        cat_filter = st.selectbox("Category", ["All","Finance","Operations","Legal","Deals","Hotel"])
    with col_f2:
        pri_filter = st.selectbox("Priority",  ["All","High","Medium","Low"])

    filter_obj = {"and": [{"property":"Status","select":{"does_not_equal":"Done"}}]}
    rows = fetch_db(NOTION_DB["action_items"], filters=filter_obj)

    if cat_filter != "All": rows = [r for r in rows if get_prop(r,"Category") == cat_filter]
    if pri_filter != "All": rows = [r for r in rows if get_prop(r,"Priority")  == pri_filter]

    rows_sorted = sorted(rows, key=lambda x: {"High":0,"Medium":1,"Low":2}.get(get_prop(x,"Priority"),3))

    st.caption(f"{len(rows_sorted)} open item(s)")

    for item in rows_sorted:
        title    = get_prop(item, "Action Item", "Untitled")
        priority = get_prop(item, "Priority", "—")
        category = get_prop(item, "Category", "—")
        status   = get_prop(item, "Status",   "—")
        due      = get_prop(item, "Due Date",  "")
        notes    = get_prop(item, "Notes",     "")
        pcls     = {"High":"priority-high","Medium":"priority-medium","Low":"priority-low"}.get(priority,"priority-low")
        due_str  = f" · Due **{due}**" if due else ""

        with st.expander(f"{title}"):
            c1,c2,c3 = st.columns(3)
            c1.markdown(f'<span class="{pcls}">{priority}</span>', unsafe_allow_html=True)
            c2.write(f"**Category:** {category}")
            c3.write(f"**Status:** {status}")
            if due_str:
                st.write(due_str)
            if notes:
                st.caption(notes)
            if st.button("Mark Done", key=f"done_{item['id']}"):
                notion_update(item["id"], {"Status": {"select": {"name": "Done"}}})
                st.cache_data.clear()
                st.success("Marked done!")
                st.rerun()

# ── Page: Portfolio Reports ───────────────────────────────────────────────────

elif page == "📁 Portfolio Reports":
    st.title("📁 Weekly Portfolio Reports")

    rows = fetch_db(NOTION_DB["portfolio_reports"],
                    sorts=[{"property":"Received Date","direction":"descending"}])

    if not rows:
        st.info("No portfolio reports yet.")
    else:
        status_filter = st.selectbox("Filter by status",
                                     ["All","Received","Replied","Follow-Ups Open","Closed"])
        if status_filter != "All":
            rows = [r for r in rows if get_prop(r,"Status") == status_filter]

        st.caption(f"{len(rows)} report(s)")

        for rep in rows:
            title   = get_prop(rep, "Report Title", "Untitled")
            frm     = get_prop(rep, "From",         "")
            subj    = get_prop(rep, "Email Subject","")
            rcvd    = get_prop(rep, "Received Date","")
            status  = get_prop(rep, "Status",       "—")
            replied = get_prop(rep, "Reply Sent",   False)
            body    = get_prop(rep, "Report Body",  "")
            week    = get_prop(rep, "Week Ending",  "")

            status_color = {"Received":"#3b82f6","Replied":"#22c55e",
                            "Follow-Ups Open":"#f97316","Closed":"#6b7280"}.get(status,"#6b7280")
            with st.expander(f"{title}  ·  {rcvd}"):
                c1,c2,c3 = st.columns(3)
                c1.write(f"**From:** {frm}")
                c2.write(f"**Week Ending:** {week or '—'}")
                c3.markdown(f'<span style="color:{status_color};font-weight:600">{status}</span>',
                            unsafe_allow_html=True)
                if subj:
                    st.caption(f"Subject: {subj}")
                if body:
                    st.text_area("Report Body", body, height=150, key=rep["id"], disabled=True)
                if not replied:
                    if st.button("Mark Reply Sent", key=f"reply_{rep['id']}"):
                        notion_update(rep["id"], {
                            "Reply Sent": {"checkbox": True},
                            "Status":     {"select": {"name": "Replied"}},
                            "Reply Date": {"date":   {"start": str(date.today())}},
                        })
                        st.cache_data.clear()
                        st.rerun()
