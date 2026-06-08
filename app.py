import streamlit as st
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
from pathlib import Path
import uuid

DATA_DIR = Path(__file__).parent / "data"
GOALS_FILE = DATA_DIR / "goals.json"
TASKS_FILE = DATA_DIR / "tasks.json"

st.set_page_config(
    page_title="IDP Command Center",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Data helpers ──────────────────────────────────────────────────────────────

def load_json(path):
    if path.exists():
        return json.loads(path.read_text())
    return []

def save_json(path, data):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2))

def load_goals():
    return load_json(GOALS_FILE)

def save_goals(goals):
    save_json(GOALS_FILE, goals)

def load_tasks():
    return load_json(TASKS_FILE)

def save_tasks(tasks):
    save_json(TASKS_FILE, tasks)

# ── Styles ────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
  .metric-card {
    background: linear-gradient(135deg, #1e1e2e 0%, #2a2a3e 100%);
    border: 1px solid #3a3a5c;
    border-radius: 12px;
    padding: 20px;
    text-align: center;
    margin-bottom: 10px;
  }
  .metric-card h2 { color: #a78bfa; font-size: 2.2rem; margin: 0; }
  .metric-card p  { color: #94a3b8; margin: 4px 0 0; font-size: 0.9rem; }
  .goal-card {
    background: #1e1e2e;
    border-left: 4px solid #7c3aed;
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 10px;
  }
  .task-card {
    background: #1e1e2e;
    border-left: 4px solid #0ea5e9;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 8px;
  }
  .badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
  }
  .badge-high   { background:#7f1d1d; color:#fca5a5; }
  .badge-medium { background:#78350f; color:#fcd34d; }
  .badge-low    { background:#14532d; color:#86efac; }
  .badge-done   { background:#1e3a5f; color:#7dd3fc; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar nav ───────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🎯 IDP Command Center")
    st.markdown("---")
    page = st.radio(
        "Navigate",
        ["📊 Dashboard", "🎯 Goals & Milestones", "🤖 AI Task Manager", "➕ Add / Edit"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.markdown("**Last synced**")
    st.markdown(f"`{datetime.now().strftime('%Y-%m-%d %H:%M')}`")
    st.markdown("Run `git pull` on another machine to sync.")

goals = load_goals()
tasks = load_tasks()

# ── Page: Dashboard ───────────────────────────────────────────────────────────

if page == "📊 Dashboard":
    st.title("📊 Dashboard")

    total_goals = len(goals)
    done_goals   = sum(1 for g in goals if g["status"] == "Completed")
    total_tasks  = len(tasks)
    done_tasks   = sum(1 for t in tasks if t["status"] == "Completed")
    avg_progress = (sum(g.get("progress", 0) for g in goals) / total_goals) if total_goals else 0

    c1, c2, c3, c4 = st.columns(4)
    for col, val, label in [
        (c1, total_goals,  "Total Goals"),
        (c2, done_goals,   "Goals Completed"),
        (c3, total_tasks,  "Total Tasks"),
        (c4, f"{avg_progress:.0f}%", "Avg Goal Progress"),
    ]:
        with col:
            st.markdown(f"""
            <div class="metric-card">
              <h2>{val}</h2>
              <p>{label}</p>
            </div>""", unsafe_allow_html=True)

    st.markdown("---")
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Goal Status Breakdown")
        if goals:
            status_counts = pd.Series([g["status"] for g in goals]).value_counts().reset_index()
            status_counts.columns = ["Status", "Count"]
            fig = px.pie(status_counts, names="Status", values="Count",
                         color_discrete_sequence=px.colors.sequential.Purples_r,
                         hole=0.4)
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#94a3b8", margin=dict(t=20, b=20))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No goals yet.")

    with col_b:
        st.subheader("Goal Progress")
        if goals:
            df = pd.DataFrame([{"Goal": g["title"][:30], "Progress": g.get("progress", 0)} for g in goals])
            fig = px.bar(df, x="Progress", y="Goal", orientation="h",
                         color="Progress", color_continuous_scale="Purples",
                         range_x=[0, 100])
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#94a3b8", margin=dict(t=20, b=20),
                              coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No goals yet.")

    st.subheader("Upcoming Tasks")
    upcoming = sorted(
        [t for t in tasks if t["status"] != "Completed"],
        key=lambda x: x.get("due_date", "9999"),
    )[:5]
    if upcoming:
        for t in upcoming:
            pri_cls = {"High": "badge-high", "Medium": "badge-medium", "Low": "badge-low"}.get(t["priority"], "badge-low")
            st.markdown(f"""
            <div class="task-card">
              <strong>{t['title']}</strong>
              &nbsp;<span class="badge {pri_cls}">{t['priority']}</span>
              &nbsp;<span class="badge badge-done">{t['type']}</span>
              <br><small style="color:#64748b">Due {t.get('due_date','—')} · {t['status']}</small>
            </div>""", unsafe_allow_html=True)
    else:
        st.success("All tasks complete!")

# ── Page: Goals & Milestones ──────────────────────────────────────────────────

elif page == "🎯 Goals & Milestones":
    st.title("🎯 Goals & Milestones")

    filter_status = st.selectbox("Filter by status", ["All", "Not Started", "In Progress", "Completed", "On Hold"])
    filtered = goals if filter_status == "All" else [g for g in goals if g["status"] == filter_status]

    for i, g in enumerate(filtered):
        with st.expander(f"{'✅' if g['status']=='Completed' else '🔵'} {g['title']}  —  {g['status']}"):
            c1, c2, c3 = st.columns(3)
            c1.metric("Category", g.get("category", "—"))
            c2.metric("Priority", g.get("priority", "—"))
            c3.metric("Due", g.get("due_date", "—"))

            progress = g.get("progress", 0)
            st.progress(progress / 100, text=f"Progress: {progress}%")

            new_prog = st.slider("Update progress", 0, 100, progress, key=f"prog_{g['id']}")
            new_status = st.selectbox("Status", ["Not Started", "In Progress", "Completed", "On Hold"],
                                      index=["Not Started", "In Progress", "Completed", "On Hold"].index(g["status"]),
                                      key=f"stat_{g['id']}")

            st.markdown("**Milestones**")
            for j, m in enumerate(g.get("milestones", [])):
                done = st.checkbox(m["title"], value=m["done"], key=f"ms_{g['id']}_{j}")
                goals[[x["id"] for x in goals].index(g["id"])]["milestones"][j]["done"] = done

            if st.button("Save changes", key=f"save_{g['id']}"):
                idx = [x["id"] for x in goals].index(g["id"])
                goals[idx]["progress"] = new_prog
                goals[idx]["status"] = new_status
                save_goals(goals)
                st.success("Saved!")
                st.rerun()

            notes = st.text_area("Notes", g.get("notes", ""), key=f"notes_{g['id']}")
            if st.button("Save notes", key=f"savenotes_{g['id']}"):
                idx = [x["id"] for x in goals].index(g["id"])
                goals[idx]["notes"] = notes
                save_goals(goals)
                st.success("Notes saved!")

# ── Page: AI Task Manager ─────────────────────────────────────────────────────

elif page == "🤖 AI Task Manager":
    st.title("🤖 AI Task Manager")

    col_filter, col_sort = st.columns(2)
    with col_filter:
        filter_type = st.selectbox("Filter by type", ["All", "AI Agent", "Manual", "Review", "Other"])
    with col_sort:
        sort_by = st.selectbox("Sort by", ["Due Date", "Priority", "Status"])

    filtered_tasks = tasks if filter_type == "All" else [t for t in tasks if t["type"] == filter_type]

    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    if sort_by == "Due Date":
        filtered_tasks = sorted(filtered_tasks, key=lambda x: x.get("due_date", "9999"))
    elif sort_by == "Priority":
        filtered_tasks = sorted(filtered_tasks, key=lambda x: priority_order.get(x["priority"], 3))
    elif sort_by == "Status":
        filtered_tasks = sorted(filtered_tasks, key=lambda x: x["status"])

    for t in filtered_tasks:
        pri_cls = {"High": "badge-high", "Medium": "badge-medium", "Low": "badge-low"}.get(t["priority"], "badge-low")
        with st.expander(f"{'✅' if t['status']=='Completed' else '⏳'} {t['title']}"):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Type", t["type"])
            c2.metric("Agent", t.get("agent", "—"))
            c3.metric("Priority", t["priority"])
            c4.metric("Due", t.get("due_date", "—"))

            new_status = st.selectbox(
                "Status",
                ["Pending", "In Progress", "Completed", "Blocked"],
                index=["Pending", "In Progress", "Completed", "Blocked"].index(t["status"]),
                key=f"tstatus_{t['id']}"
            )
            notes = st.text_area("Notes", t.get("notes", ""), key=f"tnotes_{t['id']}")

            if st.button("Save", key=f"tsave_{t['id']}"):
                idx = [x["id"] for x in tasks].index(t["id"])
                tasks[idx]["status"] = new_status
                tasks[idx]["notes"] = notes
                save_tasks(tasks)
                st.success("Saved!")
                st.rerun()

            if st.button("🗑 Delete task", key=f"tdel_{t['id']}"):
                tasks[:] = [x for x in tasks if x["id"] != t["id"]]
                save_tasks(tasks)
                st.warning("Deleted.")
                st.rerun()

    st.markdown("---")
    st.subheader("Task Status Overview")
    if tasks:
        df = pd.DataFrame(tasks)
        fig = px.histogram(df, x="status", color="priority",
                           color_discrete_map={"High": "#ef4444", "Medium": "#f59e0b", "Low": "#22c55e"},
                           barmode="group")
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font_color="#94a3b8", margin=dict(t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)

# ── Page: Add / Edit ──────────────────────────────────────────────────────────

elif page == "➕ Add / Edit":
    st.title("➕ Add New Goal or Task")

    tab1, tab2 = st.tabs(["🎯 New Goal", "🤖 New Task"])

    with tab1:
        with st.form("new_goal"):
            title    = st.text_input("Goal title *")
            category = st.selectbox("Category", ["Technical", "Leadership", "Communication", "Personal", "Business", "Other"])
            priority = st.selectbox("Priority", ["High", "Medium", "Low"])
            status   = st.selectbox("Status", ["Not Started", "In Progress", "Completed", "On Hold"])
            due_date = st.date_input("Due date", min_value=date.today())
            progress = st.slider("Initial progress", 0, 100, 0)
            notes    = st.text_area("Notes")
            milestones_raw = st.text_area("Milestones (one per line)")
            submitted = st.form_submit_button("Add Goal")

            if submitted and title:
                milestones = [{"title": m.strip(), "done": False}
                              for m in milestones_raw.split("\n") if m.strip()]
                new_goal = {
                    "id": str(uuid.uuid4())[:8],
                    "title": title,
                    "category": category,
                    "status": status,
                    "priority": priority,
                    "due_date": str(due_date),
                    "progress": progress,
                    "notes": notes,
                    "milestones": milestones,
                }
                goals.append(new_goal)
                save_goals(goals)
                st.success(f"Goal '{title}' added!")

    with tab2:
        goal_map = {g["title"]: g["id"] for g in goals}
        with st.form("new_task"):
            title    = st.text_input("Task title *")
            task_type = st.selectbox("Type", ["AI Agent", "Manual", "Review", "Other"])
            agent    = st.selectbox("Agent / Tool", ["Claude", "GPT-4", "Gemini", "Custom Script", "Manual", "Other"])
            priority = st.selectbox("Priority", ["High", "Medium", "Low"])
            status   = st.selectbox("Status", ["Pending", "In Progress", "Completed", "Blocked"])
            due_date = st.date_input("Due date", min_value=date.today())
            goal_link = st.selectbox("Link to goal (optional)", ["None"] + list(goal_map.keys()))
            notes    = st.text_area("Notes")
            submitted = st.form_submit_button("Add Task")

            if submitted and title:
                new_task = {
                    "id": str(uuid.uuid4())[:8],
                    "title": title,
                    "goal_id": goal_map.get(goal_link, ""),
                    "type": task_type,
                    "status": status,
                    "priority": priority,
                    "created": str(date.today()),
                    "due_date": str(due_date),
                    "agent": agent,
                    "notes": notes,
                }
                tasks.append(new_task)
                save_tasks(tasks)
                st.success(f"Task '{title}' added!")
