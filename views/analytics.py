"""Analytics page — year-filtered charts with Plotly, TalentCorp theme."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

import streamlit as st

from utils.helpers import normalize_status, normalize_value

# Brand palette
_C_BRAND    = "#0E1B48"
_C_BRAND2   = "#27425D"
_C_ACCENT   = "#87A7D0"
_C_PINK     = "#C18DB4"
_C_BLUSH    = "#E2CAD8"
_C_GREEN    = "#22c55e"
_C_AMBER    = "#f59e0b"
_C_RED      = "#ef4444"
_C_BLUE     = "#3b82f6"
_C_GREY     = "#9ca3af"

STATUS_COLORS = {
    "Pending":     _C_AMBER,
    "In Progress": _C_BLUE,
    "Done":        _C_GREEN,
    "Overdue":     _C_RED,
    "Cancelled":   _C_GREY,
}

_ORG_KEYWORDS = (
    "team", "corp", "sdn", "bhd", "ltd", "inc", "department", "division",
    "unit", "group", "ministry", "agency", "centre", "center", "office",
    "bureau", "talentcorp", "mynext", "region",
)


def _is_person(name: str) -> bool:
    if not name or name in ("Not stated", "None", ""):
        return False
    return not any(kw in name.lower() for kw in _ORG_KEYWORDS)


def _chart_card(title: str, caption: str = "") -> None:
    """Render a section header with subtle caption for a chart block."""
    cap_html = f"<div style='font-size:0.82rem;color:#6e7f96;margin-top:0.1rem'>{caption}</div>" if caption else ""
    st.markdown(
        f"<div style='margin:0.5rem 0 0.4rem'>"
        f"<div style='font-size:1rem;font-weight:800;color:#0E1B48'>{title}</div>"
        f"{cap_html}</div>",
        unsafe_allow_html=True,
    )


def _card_wrap(content_fn, *args, **kwargs):
    """Render content inside a styled card container."""
    st.markdown(
        "<div style='background:#ffffff;border:1px solid #d8dceb;border-radius:18px;"
        "padding:1rem 1.1rem;box-shadow:0 8px 20px rgba(14,27,72,0.06)'>",
        unsafe_allow_html=True,
    )
    content_fn(*args, **kwargs)
    st.markdown("</div>", unsafe_allow_html=True)


def render() -> None:
    try:
        import plotly.graph_objects as go
        import plotly.express as px
    except ImportError:
        st.error("plotly is required. Run: pip install plotly")
        return

    meetings_all = st.session_state.get("meetings", [])

    st.markdown("## Analytics")

    if not meetings_all:
        st.info("No meetings yet. Capture some meetings to see analytics here.")
        return

    # ── Year filter ────────────────────────────────────────────────
    all_years = sorted({
        datetime.strptime(normalize_value(m.get("date"), ""), "%Y-%m-%d").year
        for m in meetings_all
        if normalize_value(m.get("date"), "")
        and len(normalize_value(m.get("date"), "")) == 10
    }, reverse=True)

    col_year, col_spacer = st.columns([1, 3])
    with col_year:
        year_options = ["All years"] + [str(y) for y in all_years]
        selected_year = st.selectbox("Filter by year", year_options, key="analytics_year")

    # Filter meetings
    if selected_year == "All years":
        meetings = meetings_all
    else:
        meetings = [
            m for m in meetings_all
            if normalize_value(m.get("date"), "").startswith(selected_year)
        ]

    if not meetings:
        st.info(f"No meetings found for {selected_year}.")
        return

    all_actions = [a for m in meetings for a in (m.get("actions") or [])]

    # ── KPI row ───────────────────────────────────────────────────
    total_mtgs   = len(meetings)
    total_acts   = len(all_actions)
    done_acts    = sum(1 for a in all_actions if normalize_status(a) == "Done")
    overdue_acts = sum(1 for a in all_actions if normalize_status(a) == "Overdue")
    rate         = int((done_acts / total_acts) * 100) if total_acts else 0
    year_label   = selected_year if selected_year != "All years" else "All time"

    c1, c2, c3, c4 = st.columns(4)
    for col, title, value, color, sub in [
        (c1, "Meetings",        str(total_mtgs),   _C_BRAND,  year_label),
        (c2, "Action items",    str(total_acts),   "#0f766e", "Extracted"),
        (c3, "Overdue",         str(overdue_acts), _C_RED,    "Need attention"),
        (c4, "Completion",      f"{rate}%",         "#7c3aed", "Done vs total"),
    ]:
        with col:
            st.markdown(
                f"<div class='kpi-card'>"
                f"<div class='kpi-label'>{title}</div>"
                f"<div class='kpi-value' style='color:{color}'>{value}</div>"
                f"<div class='kpi-subtitle'>{sub}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    # ── Row 1: Meetings per month  +  Status donut ────────────────
    col_a, col_b = st.columns([3, 2])

    with col_a:
        _chart_card("Meetings per month", f"How many meetings were held each month — {year_label}")
        month_counts: dict[str, int] = defaultdict(int)
        for m in meetings:
            d = normalize_value(m.get("date"), "")
            try:
                key = datetime.strptime(d, "%Y-%m-%d").strftime("%b %Y")
                month_counts[key] += 1
            except Exception:
                pass

        if month_counts:
            sorted_keys = sorted(month_counts, key=lambda x: datetime.strptime(x, "%b %Y"))
            fig = go.Figure(go.Bar(
                x=sorted_keys,
                y=[month_counts[k] for k in sorted_keys],
                marker_color=_C_BRAND2,
                marker_line_width=0,
                hovertemplate="%{x}: <b>%{y} meeting(s)</b><extra></extra>",
            ))
            fig.update_layout(**_chart_layout(height=260))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No dated meetings.")

    with col_b:
        _chart_card("Action item status", "Current breakdown")
        status_counts = Counter(normalize_status(a) for a in all_actions)
        order = [s for s in ["Pending", "In Progress", "Done", "Overdue", "Cancelled"] if s in status_counts]
        if order:
            fig2 = go.Figure(go.Pie(
                labels=order,
                values=[status_counts[s] for s in order],
                marker_colors=[STATUS_COLORS.get(s, _C_GREY) for s in order],
                hole=0.55,
                textinfo="percent+label",
                textfont_size=11,
                hovertemplate="<b>%{label}</b>: %{value}<extra></extra>",
            ))
            fig2.update_layout(**_chart_layout(height=260, show_legend=False))
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    # ── Row 2: Completion by dept  +  Top assignees ───────────────
    col_c, col_d = st.columns(2)

    with col_c:
        _chart_card("Completion by department", "% of actions marked Done — top 10")
        dept_stats: dict[str, dict] = defaultdict(lambda: {"done": 0, "total": 0})
        for m in meetings:
            m_dept = normalize_value(m.get("deptName") or m.get("department"), "").strip()
            for a in (m.get("actions") or []):
                dept = normalize_value(a.get("department") or a.get("company"), "").strip()
                if not dept or dept in ("None", "Not stated"):
                    dept = m_dept
                if not dept or dept in ("None", "Not stated", ""):
                    dept = "Unassigned"
                dept_stats[dept]["total"] += 1
                if normalize_status(a) == "Done":
                    dept_stats[dept]["done"] += 1

        if dept_stats:
            dept_rates = {
                d: int((v["done"] / v["total"]) * 100) if v["total"] else 0
                for d, v in dept_stats.items()
            }
            top = sorted(dept_rates.items(), key=lambda x: x[1])[-10:]
            depts  = [x[0] for x in top]
            values = [x[1] for x in top]
            colors_bar = [_C_GREEN if v >= 75 else _C_ACCENT if v >= 40 else _C_PINK for v in values]
            fig3 = go.Figure(go.Bar(
                x=values, y=depts,
                orientation="h",
                marker_color=colors_bar,
                marker_line_width=0,
                text=[f"{v}%" for v in values],
                textposition="outside",
                hovertemplate="<b>%{y}</b>: %{x}%<extra></extra>",
            ))
            fig3.update_layout(**_chart_layout(height=300))
            fig3.update_xaxes(range=[0, 110], showgrid=False)
            st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No department data.")

    with col_d:
        _chart_card("Pending load per person", "Who has the most open tasks")
        person_pending: dict[str, int] = defaultdict(int)
        for a in all_actions:
            if normalize_status(a) in ("Done", "Cancelled"):
                continue
            owner = normalize_value(a.get("owner"), "Not stated")
            if not _is_person(owner):
                continue
            person_pending[owner] += 1

        if person_pending:
            top_p = sorted(person_pending.items(), key=lambda x: x[1])[-10:]
            names  = [x[0] for x in top_p]
            counts = [x[1] for x in top_p]
            bar_colors = [_C_RED if c >= 5 else _C_AMBER if c >= 3 else _C_ACCENT for c in counts]
            fig4 = go.Figure(go.Bar(
                x=counts, y=names,
                orientation="h",
                marker_color=bar_colors,
                marker_line_width=0,
                text=counts,
                textposition="outside",
                hovertemplate="<b>%{y}</b>: %{x} pending<extra></extra>",
            ))
            fig4.update_layout(**_chart_layout(height=300))
            fig4.update_xaxes(showgrid=False)
            st.plotly_chart(fig4, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No named assignees with pending actions.")

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    # ── Row 3: Category breakdown ─────────────────────────────────
    col_e, col_f = st.columns(2)

    with col_e:
        _chart_card("Meetings by category")
        cat_counts = Counter(
            normalize_value(m.get("category"), "Uncategorised") for m in meetings
        )
        if cat_counts:
            labels = list(cat_counts.keys())
            values = list(cat_counts.values())
            fig5 = go.Figure(go.Bar(
                x=labels, y=values,
                marker_color=_C_BRAND,
                marker_line_width=0,
                text=values,
                textposition="outside",
                hovertemplate="<b>%{x}</b>: %{y}<extra></extra>",
            ))
            fig5.update_layout(**_chart_layout(height=240))
            st.plotly_chart(fig5, use_container_width=True, config={"displayModeBar": False})

    with col_f:
        _chart_card("Follow-up status")
        fu_yes = sum(1 for m in meetings if m.get("followUp"))
        fu_no  = total_mtgs - fu_yes
        fig6 = go.Figure(go.Pie(
            labels=["Follow-up needed", "Closed"],
            values=[fu_yes, fu_no],
            marker_colors=[_C_AMBER, _C_GREEN],
            hole=0.55,
            textinfo="percent+label",
            textfont_size=12,
            hovertemplate="<b>%{label}</b>: %{value}<extra></extra>",
        ))
        fig6.update_layout(**_chart_layout(height=240, show_legend=False))
        st.plotly_chart(fig6, use_container_width=True, config={"displayModeBar": False})


def _chart_layout(height: int = 280, show_legend: bool = True) -> dict:
    """Shared clean Plotly layout config."""
    return dict(
        height=height,
        margin=dict(l=0, r=10, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Aptos, Segoe UI, Arial, sans-serif", size=11, color="#27425D"),
        showlegend=show_legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        xaxis=dict(showgrid=False, zeroline=False, tickfont=dict(size=10)),
        yaxis=dict(showgrid=True, gridcolor="#f0f0f5", zeroline=False, tickfont=dict(size=10)),
        hoverlabel=dict(bgcolor="white", bordercolor="#d8dceb", font_size=12),
    )
