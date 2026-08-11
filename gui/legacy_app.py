"""AutoSeller AI — 2026 Modern Interface"""
import html
import json
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from app.pipeline import (
    setup, list_products, get_product_detail,
    delete_product, get_stats, import_product, upload_product,
    analyze_market, get_market_history,
    add_order, list_orders, delete_order,
    get_settlement_dashboard, get_profit_calculator_preview,
    get_inventory_dashboard, update_inventory,
    bulk_init_inventory, get_recent_stock_movements,
    create_purchase_order, list_purchase_orders,
    receive_purchase_order, update_po_status,
    get_stock_movements,
    test_telegram_connection, send_daily_report,
    trigger_inventory_alerts, notify_pipeline_done,
    get_notification_logs, get_notification_stats,
    get_scheduler_status, toggle_scheduled_job,
    run_job_now, update_job_cron, get_job_run_logs,
    get_dashboard_overview,
    run_health_check, get_circuit_breaker_status,
    reset_circuit_breaker, get_health_logs, get_rate_limiter_status,
    test_service_connection,
    list_seo_target_products, run_seo_analysis, list_seo_revisions,
    approve_seo_revision, reject_seo_revision, apply_seo_revision,
    get_seo_before_after, export_seo_revisions_csv,
    sync_platform_catalog,
)

setup()


# ── 스케줄러 싱글톤 (모듈 레벨 캐싱 — with tab 블록 밖) ──────────────────
@st.cache_resource(show_spinner=False)
def _get_scheduler():
    from app.scheduler.manager import get_scheduler
    return get_scheduler()

_sched_instance = _get_scheduler()

# ── 페이지 설정 ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="AutoSeller AI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 디자인 시스템 ──────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@300;400;500;600;700;800&display=swap');

*, html, body, [class*="css"] {
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none !important; }
.block-container { padding-top: 1.5rem !important; max-width: 1280px; }

/* ── 탭 (pill style) ── */
.stTabs [data-baseweb="tab-list"] {
    background: #F1F5F9;
    border-radius: 12px;
    padding: 4px;
    gap: 2px;
    border-bottom: none !important;
    overflow-x: auto !important;
    overflow-y: hidden !important;
    flex-wrap: nowrap !important;
    scrollbar-width: none !important;
}
.stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {
    display: none !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    color: #64748B;
    border: none !important;
    padding: 8px 14px !important;
    background: transparent !important;
    transition: all 0.15s !important;
    white-space: nowrap !important;
    flex-shrink: 0 !important;
}
.stTabs [aria-selected="true"] {
    background: #FFFFFF !important;
    color: #0F172A !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06) !important;
}
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] { display: none !important; }

/* ── 버튼 ── */
.stButton > button {
    border-radius: 10px !important;
    font-weight: 600 !important;
    transition: all 0.15s ease !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #7C3AED, #6D28D9) !important;
    border: none !important;
    color: white !important;
    box-shadow: 0 4px 14px rgba(124,58,237,0.35) !important;
}
.stButton > button[kind="primary"]:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(124,58,237,0.45) !important;
}
.stButton > button[kind="secondary"] {
    border-color: #E2E8F0 !important;
    color: #475569 !important;
}

/* ── 입력 ── */
.stTextInput > div > div > input,
.stNumberInput > div > div > input { border-radius: 8px !important; }
.stSelectbox > div > div { border-radius: 8px !important; }
.stSlider > div { padding: 4px 0 !important; }

/* ── 메트릭 카드 ── */
.m-card {
    background: #fff;
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    padding: 18px 16px;
    text-align: center;
    transition: all 0.2s ease;
}
.m-card:hover { box-shadow: 0 8px 25px rgba(0,0,0,0.08); transform: translateY(-2px); }
.m-icon  { font-size: 22px; margin-bottom: 8px; }
.m-value { font-size: 30px; font-weight: 800; color: #0F172A; line-height: 1.1; }
.m-label { font-size: 11px; color: #94A3B8; font-weight: 600; margin-top: 5px;
           letter-spacing: 0.05em; text-transform: uppercase; }

/* ── 배지 ── */
.badge { display:inline-block; padding:3px 10px; border-radius:20px; font-size:11px; font-weight:700; }
.bd-ready   { background:#DCFCE7; color:#15803D; }
.bd-draft   { background:#F1F5F9; color:#475569; }
.bd-listed  { background:#DBEAFE; color:#1D4ED8; }
.bd-success { background:#DCFCE7; color:#15803D; }
.bd-failed  { background:#FEE2E2; color:#B91C1C; }
.bd-pending { background:#FEF3C7; color:#B45309; }

/* ── 실행 로그 ── */
.log-wrap {
    background: #0F172A;
    border-radius: 12px;
    padding: 16px 18px;
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
    font-size: 13px;
    line-height: 1.75;
    min-height: 180px;
    max-height: 460px;
    overflow-y: auto;
}
.lo { color: #4ADE80; }   /* ok */
.le { color: #F87171; }   /* error */
.li { color: #60A5FA; }   /* info */
.lw { color: #FBBF24; }   /* warn */
.ld { color: #475569; }   /* dim */

/* ── 상품 행 ── */
.prow {
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 8px;
    background: white;
    transition: box-shadow 0.15s;
}
.prow:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.07); }

/* ── 결과 배너 ── */
.result-ok {
    background: linear-gradient(135deg, #ECFDF5, #D1FAE5);
    border: 1px solid #6EE7B7;
    border-radius: 12px;
    padding: 16px 20px;
    margin-top: 14px;
}
.result-fail {
    background: #FFF7ED;
    border: 1px solid #FED7AA;
    border-radius: 12px;
    padding: 16px 20px;
    margin-top: 14px;
}

/* ── 빈 상태 ── */
.empty-box { text-align:center; padding:56px 20px; color:#94A3B8; }
.empty-box .ei { font-size:48px; margin-bottom:14px; }
.empty-box h3 { color:#64748B; font-size:18px; font-weight:700; margin:0; }
.empty-box p  { font-size:14px; margin-top:6px; }

hr { border-color: #E2E8F0 !important; margin: 16px 0 !important; }
</style>
""", unsafe_allow_html=True)


# ── 유틸 ──────────────────────────────────────────────────────────────

def badge(status: str) -> str:
    mapping = {
        "draft": ("bd-draft", "처리중"),
        "ready": ("bd-ready", "준비됨"),
        "listed": ("bd-listed", "판매중"),
        "success": ("bd-success", "성공"),
        "failed": ("bd-failed", "실패"),
        "pending": ("bd-pending", "대기"),
        "DRAFT": ("bd-draft", "초안"),
        "REVIEW_PENDING": ("bd-pending", "검수대기"),
        "APPROVED": ("bd-ready", "승인됨"),
        "REJECTED": ("bd-failed", "반려됨"),
        "APPLIED": ("bd-success", "반영완료"),
        "APPLY_FAILED": ("bd-failed", "반영실패"),
    }
    cls, label = mapping.get(status, ("bd-draft", status))
    return f'<span class="badge {cls}">{label}</span>'


def log_html(logs: list[str]) -> str:
    if not logs:
        return '<div class="log-wrap"><span class="ld">파이프라인 실행 대기 중...</span></div>'
    lines = []
    for raw in logs:
        safe = html.escape(raw)
        if any(x in raw for x in ["✅", "성공", "완료", "등록", "♻️"]):
            cls = "lo"
        elif any(x in raw for x in ["❌", "실패", "오류", "예외"]):
            cls = "le"
        elif any(x in raw for x in ["🔍", "📤", "🤖", "📥", "📊", "🎉"]):
            cls = "li"
        elif any(x in raw for x in ["⚠️", "주의", "확인"]):
            cls = "lw"
        else:
            cls = "ld"
        lines.append(f'<div class="{cls}">{safe}</div>')
    return f'<div class="log-wrap">{"".join(lines)}</div>'


def metric_card(icon: str, value, label: str) -> str:
    return (
        f'<div class="m-card">'
        f'<div class="m-icon">{icon}</div>'
        f'<div class="m-value">{value}</div>'
        f'<div class="m-label">{label}</div>'
        f'</div>'
    )


def src_name(s: str) -> str:
    return {"domeggook": "도매꾹", "onchannel": "온채널"}.get(s, s)


def plat_name(p: str) -> str:
    return {"smartstore": "스마트스토어", "coupang": "쿠팡"}.get(p, p)


# ── 헤더 ──────────────────────────────────────────────────────────────

stats = get_stats()
p, u = stats["products"], stats["uploads"]

st.markdown(f"""
<div style="
    background: linear-gradient(135deg,#1E1B4B 0%,#3730A3 55%,#4F46E5 100%);
    padding:22px 28px; border-radius:16px; margin-bottom:22px;
    display:flex; align-items:center; gap:20px;
    box-shadow:0 8px 32px rgba(99,102,241,.28);
">
  <div style="
    width:50px;height:50px; background:rgba(255,255,255,.15);
    border-radius:14px; display:flex; align-items:center; justify-content:center;
    font-size:24px; flex-shrink:0; backdrop-filter:blur(6px);
  ">⚡</div>
  <div style="flex:1;min-width:0">
    <div style="color:#fff;font-size:20px;font-weight:800;letter-spacing:-.3px">AutoSeller AI</div>
    <div style="color:rgba(255,255,255,.6);font-size:12px;margin-top:3px">
      도매꾹 · 온채널 → 쿠팡 · 스마트스토어 자동 판매 플랫폼
    </div>
  </div>
  <div style="display:flex;gap:28px;flex-shrink:0">
    {"".join(
      f'<div style="text-align:center">'
      f'<div style="color:#fff;font-size:22px;font-weight:800;line-height:1">{v}</div>'
      f'<div style="color:rgba(255,255,255,.5);font-size:10px;margin-top:4px;letter-spacing:.05em;text-transform:uppercase">{k}</div>'
      f'</div>'
      for k, v in [
        ("전체", p["total"]), ("준비", p["ready"]), ("판매중", p["listed"]),
        ("스마트", u["smartstore"]), ("쿠팡", u["coupang"]),
      ]
    )}
  </div>
</div>
""", unsafe_allow_html=True)


# ── 탭 네비게이션 ─────────────────────────────────────────────────────
tab_dash, tab_auto, tab_search, tab_products, tab_status, tab_seo, tab_market, tab_settle, tab_inv, tab_notify, tab_sched, tab_cfg = st.tabs([
    "📊 대시보드",
    "⚡ 파이프라인",
    "🔍 상품수집",
    "📦 상품관리",
    "📤 업로드",
    "🔍 SEO 최적화",
    "🧠 시장분석",
    "💰 정산·세금",
    "🏭 재고·발주",
    "📱 알림",
    "⏰ 스케줄러",
    "⚙️ 설정",
])


# ════════════════════════════════════════════════════════════════════════
# TAB 1 · 대시보드 (Dashboard)
# ════════════════════════════════════════════════════════════════════════
with tab_dash:
    import pandas as pd
    import plotly.graph_objects as go

    # ── 데이터 로드 ────────────────────────────────────────────────────
    @st.cache_data(ttl=60, show_spinner=False)
    def _load_overview():
        return get_dashboard_overview()

    d_ref_btn = st.button("🔄 새로고침", key="dash_main_ref", help="대시보드 데이터 갱신 (60초 캐시)")
    if d_ref_btn:
        st.cache_data.clear()
        st.rerun()

    with st.spinner("데이터 로딩 중..."):
        ov = _load_overview()

    p_stats = ov["products"]
    sm      = ov["settlement"]
    by_plat = ov["by_platform"]
    monthly = ov["monthly_trend"]
    inv     = ov["inventory"]
    notifs  = ov["recent_notifications"]
    sched   = ov["scheduler"]
    orders  = ov["recent_orders"]

    # ── KPI 카드 행 ────────────────────────────────────────────────────
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    _np_color = "#047857" if sm["net_profit"] >= 0 else "#DC2626"

    kpi_data = [
        (k1, "📦", p_stats["products"]["total"],       "전체 상품",    ""),
        (k2, "🟢", p_stats["products"]["listed"],      "판매 중",      "color:#047857;"),
        (k3, "💵", f'{sm["gross_revenue"]:,.0f}원',    "이번달 매출",   ""),
        (k4, "💚", f'{sm["net_profit"]:,.0f}원',       "이번달 순이익", f"color:{_np_color};"),
        (k5, "🔴", inv["critical"],                    "재고 위험",    "color:#DC2626;" if inv["critical"] > 0 else ""),
        (k6, "⏰", sched["enabled_jobs"],              "활성 스케줄",   "color:#4F46E5;"),
    ]
    for col, icon, val, lbl, clr in kpi_data:
        with col:
            st.markdown(
                f'<div class="m-card">'
                f'<div class="m-icon">{icon}</div>'
                f'<div class="m-value" style="{clr}">{val}</div>'
                f'<div class="m-label">{lbl}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Row A: 수익 트렌드 + 플랫폼 비중 ─────────────────────────────
    ra_l, ra_r = st.columns([2.2, 1], gap="large")

    with ra_l:
        st.markdown("##### 📈 월별 수익 트렌드")
        months_lbl = [m["label"] for m in monthly]
        revenues   = [m["gross_revenue"] for m in monthly]
        profits    = [m["net_profit"]    for m in monthly]

        fig_rev = go.Figure()
        fig_rev.add_trace(go.Bar(
            x=months_lbl, y=revenues,
            name="총매출",
            marker_color="#818CF8",
            opacity=0.75,
        ))
        fig_rev.add_trace(go.Scatter(
            x=months_lbl, y=profits,
            name="순이익",
            mode="lines+markers",
            line=dict(color="#10B981", width=2.5),
            marker=dict(size=5, color="#10B981"),
        ))
        fig_rev.update_layout(
            height=240,
            margin=dict(l=0, r=0, t=8, b=0),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", y=1.18, x=0, font=dict(size=12)),
            xaxis=dict(showgrid=False, tickfont=dict(size=11)),
            yaxis=dict(gridcolor="#F1F5F9", tickfont=dict(size=10),
                       tickformat=",.0f"),
            hovermode="x unified",
        )
        st.plotly_chart(fig_rev, use_container_width=True, config={"displayModeBar": False})

    with ra_r:
        st.markdown("##### 🏪 플랫폼 비중")
        cp = by_plat.get("coupang", {})
        ss = by_plat.get("smartstore", {})
        cp_rev = cp.get("gross_revenue", 0)
        ss_rev = ss.get("gross_revenue", 0)

        if cp_rev + ss_rev > 0:
            fig_pie = go.Figure(data=[go.Pie(
                labels=["쿠팡", "스마트스토어"],
                values=[cp_rev, ss_rev],
                hole=0.58,
                marker=dict(colors=["#F59E0B", "#10B981"]),
                textinfo="label+percent",
                textfont=dict(size=12),
                hovertemplate="%{label}<br>%{value:,.0f}원<extra></extra>",
            )])
            fig_pie.update_layout(
                height=220,
                margin=dict(l=0, r=0, t=0, b=0),
                showlegend=False,
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_pie, use_container_width=True, config={"displayModeBar": False})
        else:
            st.markdown(
                '<div class="empty-box" style="padding:30px 10px">'
                '<div class="ei" style="font-size:32px">📊</div>'
                '<p style="font-size:12px">주문 데이터 없음</p></div>',
                unsafe_allow_html=True,
            )

        # 플랫폼별 미니 수치
        for plat, clr_dot, pdata in [
            ("쿠팡",       "#F59E0B", cp),
            ("스마트스토어", "#10B981", ss),
        ]:
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;'
                f'align-items:center;padding:4px 0;border-bottom:1px solid #F1F5F9">'
                f'<span style="font-size:12px;color:#475569">'
                f'<span style="color:{clr_dot};font-weight:800">●</span> {plat}</span>'
                f'<span style="font-size:12px;font-weight:700;color:#0F172A">'
                f'{pdata.get("order_count",0)}건 · '
                f'{pdata.get("net_profit",0):,.0f}원</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Row B: 재고 알림 / 최근 알림 / 스케줄러 ─────────────────────
    rb1, rb2, rb3 = st.columns(3, gap="large")

    with rb1:
        st.markdown("##### 🏭 재고 위험 현황")
        with st.container(border=True):
            if inv["critical"] == 0 and inv["warning"] == 0:
                st.markdown(
                    '<div style="text-align:center;padding:18px 0;color:#10B981">'
                    '<div style="font-size:28px">✅</div>'
                    '<div style="font-size:13px;font-weight:700;margin-top:6px">재고 양호</div>'
                    '<div style="font-size:11px;color:#94A3B8;margin-top:2px">'
                    f'총 {inv["total"]}개 상품 추적 중</div></div>',
                    unsafe_allow_html=True,
                )
            else:
                if inv["critical"] > 0:
                    st.markdown(
                        f'<div style="background:#FEF2F2;border-left:3px solid #EF4444;'
                        f'padding:8px 12px;border-radius:0 8px 8px 0;margin-bottom:8px">'
                        f'<span style="font-weight:700;color:#B91C1C">🔴 위험 {inv["critical"]}개</span>'
                        f'<span style="font-size:11px;color:#94A3B8;margin-left:6px">즉시 발주 필요</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                if inv["warning"] > 0:
                    st.markdown(
                        f'<div style="background:#FFFBEB;border-left:3px solid #F59E0B;'
                        f'padding:8px 12px;border-radius:0 8px 8px 0;margin-bottom:8px">'
                        f'<span style="font-weight:700;color:#B45309">🟡 경고 {inv["warning"]}개</span>'
                        f'<span style="font-size:11px;color:#94A3B8;margin-left:6px">발주 권장</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                for alert in inv["top_alerts"][:3]:
                    urg = alert["urgency"]
                    dot = "🔴" if urg == "critical" else "🟡"
                    st.markdown(
                        f'<div style="padding:4px 0;border-bottom:1px solid #F8FAFC;'
                        f'font-size:12px;color:#374151">'
                        f'{dot} <b>{alert["product_name"][:22]}</b> '
                        f'— 가용 {alert["available_qty"]}개</div>',
                        unsafe_allow_html=True,
                    )
            st.markdown(
                f'<div style="font-size:11px;color:#94A3B8;margin-top:8px">'
                f'재고 원가 {inv["total_value"]:,.0f}원 · {inv["total"]}개 상품</div>',
                unsafe_allow_html=True,
            )

    with rb2:
        st.markdown("##### 📱 최근 알림")
        with st.container(border=True):
            if not notifs:
                st.markdown(
                    '<div style="text-align:center;padding:18px 0;color:#94A3B8">'
                    '<div style="font-size:28px">📭</div>'
                    '<div style="font-size:12px;margin-top:6px">알림 없음</div></div>',
                    unsafe_allow_html=True,
                )
            else:
                _nlv_dot = {
                    "critical": ("🚨", "#B91C1C"),
                    "warning":  ("⚠️", "#B45309"),
                    "info":     ("ℹ️", "#1D4ED8"),
                    "success":  ("✅", "#047857"),
                }
                for n in notifs:
                    dot_e, dot_c = _nlv_dot.get(n["level"], ("·", "#94A3B8"))
                    ok_icon = "✅" if n["status"] == "ok" else "❌"
                    st.markdown(
                        f'<div style="padding:5px 0;border-bottom:1px solid #F8FAFC">'
                        f'<div style="display:flex;align-items:center;gap:6px">'
                        f'<span>{dot_e}</span>'
                        f'<span style="font-size:12px;font-weight:600;color:{dot_c};flex:1">'
                        f'{html.escape(n["title"][:28])}</span>'
                        f'<span style="font-size:10px">{ok_icon}</span>'
                        f'</div>'
                        f'<div style="font-size:10px;color:#94A3B8;margin-left:22px">'
                        f'{n["sent_at"][-8:] if n["sent_at"] else ""}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

    with rb3:
        st.markdown("##### ⏰ 스케줄러 현황")
        with st.container(border=True):
            running_dot = (
                '<span style="display:inline-block;width:8px;height:8px;'
                'border-radius:50%;background:#4ADE80;margin-right:4px;'
                'vertical-align:middle"></span>'
                if sched["running"] else
                '<span style="display:inline-block;width:8px;height:8px;'
                'border-radius:50%;background:#94A3B8;margin-right:4px;'
                'vertical-align:middle"></span>'
            )
            st.markdown(
                f'{running_dot}'
                f'<span style="font-size:12px;font-weight:700;color:#374151">'
                f'{"실행 중" if sched["running"] else "중지"}</span> '
                f'<span style="font-size:11px;color:#94A3B8">'
                f'활성 {sched["enabled_jobs"]}/{sched["total_jobs"]}개</span>',
                unsafe_allow_html=True,
            )
            st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

            enabled_jobs = [j for j in sched["jobs"] if j["enabled"]]
            if not enabled_jobs:
                st.markdown(
                    '<div style="font-size:12px;color:#94A3B8;text-align:center;padding:12px 0">'
                    '활성 작업 없음<br><small>스케줄러 탭에서 활성화하세요</small></div>',
                    unsafe_allow_html=True,
                )
            else:
                for jb in enabled_jobs[:4]:
                    last_st = jb.get("last_status", "")
                    st_icon = "✅" if last_st == "ok" else "❌" if last_st == "failed" else "⏳"
                    next_run = jb.get("next_run_at", "")[-5:] if jb.get("next_run_at") else "--:--"
                    st.markdown(
                        f'<div style="padding:4px 0;border-bottom:1px solid #F8FAFC;'
                        f'display:flex;align-items:center;gap:6px">'
                        f'<span style="font-size:11px">{st_icon}</span>'
                        f'<span style="font-size:12px;color:#374151;flex:1">{jb["name"]}</span>'
                        f'<span style="font-size:10px;color:#94A3B8">{next_run}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Row C: 업로드 현황 미니 카드 + Quick Actions ──────────────────
    rc_l, rc_r = st.columns([1.2, 1], gap="large")

    with rc_l:
        st.markdown("##### 📤 업로드 현황")
        uc1, uc2, uc3, uc4 = st.columns(4)
        for col, icon, val, lbl, clr in [
            (uc1, "📦", p_stats["products"]["total"], "전체",    ""),
            (uc2, "✅", p_stats["uploads"]["smartstore"], "스마트", "color:#047857;"),
            (uc3, "🟡", p_stats["uploads"]["coupang"],    "쿠팡",   "color:#B45309;"),
            (uc4, "❌", ov["upload_fail"],                "실패",   "color:#DC2626;" if ov["upload_fail"] > 0 else ""),
        ]:
            with col:
                st.markdown(
                    f'<div style="text-align:center;padding:10px 4px;'
                    f'background:#F8FAFC;border-radius:10px">'
                    f'<div style="font-size:18px">{icon}</div>'
                    f'<div style="font-size:20px;font-weight:800;{clr}">{val}</div>'
                    f'<div style="font-size:10px;color:#94A3B8">{lbl}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    with rc_r:
        st.markdown("##### ⚡ 빠른 실행")
        with st.container(border=True):
            if st.button("⚡ 파이프라인 즉시 실행", use_container_width=True,
                         key="dash_run_pipe", type="primary"):
                res_p = run_job_now("pipeline_auto")
                if res_p["status"] == "ok":
                    st.success("✅ 파이프라인 시작됨 (백그라운드)")
                else:
                    st.error(res_p.get("error", ""))

            if st.button("🏭 재고 위험 체크 + 알림", use_container_width=True,
                         key="dash_inv_chk"):
                with st.spinner("재고 스캔 중..."):
                    res_i = trigger_inventory_alerts()
                c, w = res_i["critical"], res_i["warning"]
                if c == 0 and w == 0:
                    st.info("재고 위험 없음")
                else:
                    st.warning(f"위험 {c}개 / 경고 {w}개 — 알림 {res_i['sent']}건 발송")

            if st.button("📊 일일 리포트 발송", use_container_width=True,
                         key="dash_report"):
                with st.spinner("리포트 발송 중..."):
                    res_r = send_daily_report()
                if res_r["status"] == "ok":
                    st.success("✅ 텔레그램 리포트 발송 완료")
                else:
                    st.error("발송 실패")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Row D: 최근 주문 테이블 ────────────────────────────────────────
    st.markdown("##### 📋 최근 주문")
    if not orders:
        st.info("주문 데이터 없음 — 정산 탭에서 주문을 등록하세요.", icon="ℹ️")
    else:
        hdr = st.columns([0.5, 2, 1, 1, 1.2, 1.2, 0.8])
        for col, txt in zip(hdr, ["#", "상품·플랫폼", "수량", "판매가", "총매출", "순이익", "상태"]):
            col.markdown(
                f'<div style="font-size:11px;font-weight:700;color:#94A3B8;'
                f'text-transform:uppercase;padding:3px 0">{txt}</div>',
                unsafe_allow_html=True,
            )
        for o in orders[:8]:
            plat_c = "#B45309" if o["platform"] == "coupang" else "#047857"
            plat_l = "쿠팡" if o["platform"] == "coupang" else "스마트"
            np_c   = "#047857" if o["net_profit"] >= 0 else "#DC2626"
            st_map = {"completed": "완료", "ordered": "접수", "shipped": "배송중",
                      "returned": "반품", "cancelled": "취소"}
            c0, c1, c2, c3, c4, c5, c6 = st.columns([0.5, 2, 1, 1, 1.2, 1.2, 0.8])
            c0.markdown(
                f'<div style="font-size:12px;color:#94A3B8;padding-top:3px">#{o["id"]}</div>',
                unsafe_allow_html=True,
            )
            c1.markdown(
                f'<div style="font-size:12px;font-weight:600;color:#0F172A">'
                f'상품 #{o["product_id"]}</div>'
                f'<div style="font-size:10px;color:{plat_c};font-weight:700">{plat_l} · {o["ordered_at"][:10]}</div>',
                unsafe_allow_html=True,
            )
            c2.markdown(f'<div style="font-size:12px;padding-top:3px">{o["quantity"]}개</div>', unsafe_allow_html=True)
            c3.markdown(f'<div style="font-size:12px;padding-top:3px">{o["unit_sale_price"]:,.0f}</div>', unsafe_allow_html=True)
            c4.markdown(f'<div style="font-size:12px;font-weight:600;padding-top:3px">{o["gross_revenue"]:,.0f}</div>', unsafe_allow_html=True)
            c5.markdown(f'<div style="font-size:12px;font-weight:800;color:{np_c};padding-top:3px">{o["net_profit"]:,.0f}</div>', unsafe_allow_html=True)
            c6.markdown(
                f'<div style="font-size:10px;padding-top:3px">'
                f'{st_map.get(o["status"], o["status"])}</div>',
                unsafe_allow_html=True,
            )


# ════════════════════════════════════════════════════════════════════════
# TAB 2 · 자동 파이프라인 ─ 한큐 자동화
# ════════════════════════════════════════════════════════════════════════
with tab_auto:
    col_cfg, col_run = st.columns([1, 1.6], gap="large")

    # ── 설정 패널 ──────────────────────────────────────────────────────
    with col_cfg:
        st.markdown("#### ⚙️ 실행 설정")
        with st.container(border=True):

            st.markdown("**공급처 선택**")
            c1, c2 = st.columns(2)
            use_onc = c1.checkbox("온채널", value=True)
            use_dom = c2.checkbox("도매꾹", value=False,
                                   help="도매꾹 API 키 등록 후 사용 가능")

            st.divider()

            kw = st.text_input(
                "🔑 검색 키워드 또는 온채널 URL",
                placeholder="예: 텀블러  또는  onch3.co.kr/dbcenter_renewal/detail.php?num=12340149",
                label_visibility="visible",
                help="키워드 검색 또는 온채널 상품 URL을 직접 붙여넣으면 정확한 상품 1개를 수집합니다",
            )

            st.divider()

            c1, c2 = st.columns(2)
            mult = c1.number_input(
                "판매가 배수", value=3.5, min_value=1.1, step=0.1,
                format="%.1f", help="공급가 × 배수 = 판매가",
            )
            min_mgn = c2.number_input(
                "최소 마진 (%)", value=15, min_value=1, max_value=80,
                help="이 마진 이하 상품은 제외",
            )
            collect_n = st.slider("수집 수", 5, 50, 20)

            st.divider()

            st.markdown("**업로드 대상**")
            c1, c2 = st.columns(2)
            up_ss = c1.checkbox("스마트스토어", value=True)
            up_cp = c2.checkbox("쿠팡", value=True)

            ai_on = st.checkbox("🤖 AI 상품명 · 설명 자동 생성", value=True,
                                 help="Claude Haiku로 상품명 최적화 및 상세 HTML 생성")

            st.divider()

            sources = []
            if use_onc: sources.append("onchannel")
            if use_dom: sources.append("domeggook")
            plats = []
            if up_ss: plats.append("smartstore")
            if up_cp: plats.append("coupang")

            disabled = not kw.strip() or not sources or not plats
            hint = ""
            if not kw.strip():  hint = "키워드를 입력하세요"
            elif not sources:   hint = "공급처를 선택하세요"
            elif not plats:     hint = "업로드 대상을 선택하세요"

            if hint:
                st.caption(f"⚠️ {hint}")

            run_btn = st.button(
                "⚡  자동 실행 시작",
                type="primary",
                use_container_width=True,
                disabled=disabled,
            )

    # ── 실행 패널 ──────────────────────────────────────────────────────
    with col_run:
        st.markdown("#### 📋 실행 현황")

        log_ph    = st.empty()
        prog_ph   = st.empty()
        result_ph = st.empty()

        log_ph.markdown(log_html([]), unsafe_allow_html=True)

        if run_btn:
            logs: list[str] = []

            def add(msg: str) -> None:
                logs.append(msg)
                log_ph.markdown(log_html(logs), unsafe_allow_html=True)

            prog = prog_ph.progress(0, text="파이프라인 시작 중...")

            # ── Step 1 · 수집 ─────────────────────────────────────────
            import re as _re_kw
            _onc_num = _re_kw.search(r'num=(\d+)', kw)  # 온채널 URL 직접 입력 감지
            _kw_display = f"num={_onc_num.group(1)}" if _onc_num else kw
            add(f"🔍 '{_kw_display}' 검색 시작 ({', '.join(src_name(s) for s in sources)})")
            all_prods = []

            for src in sources:
                add(f"  📡 {src_name(src)} 요청 중...")
                try:
                    if src == "onchannel" and _onc_num:
                        # URL 직접 입력 → 정확한 상품 1개 수집
                        from app.suppliers.onchannel import get_product as _gp_onc
                        _p = _gp_onc(_onc_num.group(1))
                        got = [_p] if _p else []
                        add(f"  ✅ {src_name(src)}: URL 직접 수집 ({len(got)}개)")
                    elif src == "onchannel":
                        from app.suppliers.onchannel import search as _s
                        got = _s(keyword=kw, limit=collect_n)
                        add(f"  ✅ {src_name(src)}: {len(got)}개 수집")
                    else:
                        from app.suppliers.domeggook import search as _s
                        got = _s(keyword=kw, limit=collect_n)
                        add(f"  ✅ {src_name(src)}: {len(got)}개 수집")
                    all_prods.extend(got)
                except Exception as exc:
                    add(f"  ❌ {src_name(src)} 오류: {str(exc)[:60]}")

            prog.progress(20, text=f"수집 완료 · {len(all_prods)}개")

            if not all_prods:
                add("❌ 수집 결과 없음 — 키워드 변경 또는 공급처 설정 확인")
                prog_ph.empty()
            else:
                # ── Step 2 · 마진 필터 ────────────────────────────────
                add(f"\n📊 마진 필터 ({min_mgn}% 이상) 적용 중...")
                fee_max = max(({"smartstore": 0.035, "coupang": 0.107}.get(pl, 0.107) for pl in plats), default=0.107)
                ship = 3000
                filtered: list[tuple] = []

                for prod in all_prods:
                    if prod.supply_price <= 0:
                        continue
                    sell = prod.supply_price * mult
                    margin = (sell - prod.supply_price - ship - sell * fee_max) / sell
                    if margin >= (min_mgn / 100):
                        filtered.append((prod, int(sell)))

                add(f"✅ 마진 통과 {len(filtered)}/{len(all_prods)}개 "
                    f"(탈락 {len(all_prods)-len(filtered)}개)")
                prog.progress(30, text=f"필터 완료 · {len(filtered)}개")

                if not filtered:
                    add(f"⚠️ 통과 상품 없음 — 배수({mult}x) 또는 최소 마진({min_mgn}%) 조정 필요")
                    prog_ph.empty()
                else:
                    # ── Step 3 · AI 최적화 + DB 등록 ──────────────────
                    ai_tag = "🤖 AI 최적화 + " if ai_on else ""
                    add(f"\n{ai_tag}📥 DB 등록 중 ({len(filtered)}개)...")
                    imported: list[int] = []

                    for i, (prod, sell_price) in enumerate(filtered):
                        try:
                            res = import_product(prod.source, prod.source_id,
                                                  sell_price, ai_on)
                            st_icon = {"imported": "✅", "updated": "♻️"}.get(res["status"], "❌")
                            if res["status"] in ("imported", "updated"):
                                imported.append(res["id"])
                                add(f"  {st_icon} [{i+1}/{len(filtered)}] {res['name'][:42]}")
                            else:
                                add(f"  ❌ [{i+1}/{len(filtered)}] {res.get('error','')[:50]}")
                        except Exception as exc:
                            add(f"  ❌ [{i+1}/{len(filtered)}] 예외: {str(exc)[:50]}")
                        prog.progress(30 + int(40 * (i + 1) / len(filtered)),
                                      text=f"등록 중 {i+1}/{len(filtered)}")

                    add(f"✅ DB 등록 완료: {len(imported)}개")
                    prog.progress(72, text="업로드 준비...")

                    # ── Step 4 · 플랫폼 업로드 ────────────────────────
                    ok_cnt = fail_cnt = 0

                    if imported and plats:
                        add(f"\n📤 플랫폼 업로드 ({', '.join(plat_name(pl) for pl in plats)})...")
                        for j, pid in enumerate(imported):
                            try:
                                for r in upload_product(pid, plats):
                                    if r["status"] == "success":
                                        ok_cnt += 1
                                        add(f"  ✅ [{j+1}] {plat_name(r['platform'])} 업로드 성공")
                                    else:
                                        fail_cnt += 1
                                        add(f"  ❌ [{j+1}] {plat_name(r['platform'])}: "
                                            f"{r.get('error','')[:150]}")
                            except Exception as exc:
                                fail_cnt += 1
                                add(f"  ❌ [{j+1}] 업로드 예외: {str(exc)[:150]}")
                            prog.progress(72 + int(26 * (j + 1) / len(imported)),
                                          text=f"업로드 {j+1}/{len(imported)}")

                    # ── 완료 ──────────────────────────────────────────
                    prog.progress(100, text="완료!")
                    add(f"\n🎉 완료  수집 {len(all_prods)} → 통과 {len(filtered)}"
                        f" → 등록 {len(imported)} → 업로드 성공 {ok_cnt}건 / 실패 {fail_cnt}건")
                    time.sleep(0.4)
                    prog_ph.empty()

                    color = "#ECFDF5" if fail_cnt == 0 else "#FFF7ED"
                    border = "#6EE7B7" if fail_cnt == 0 else "#FED7AA"
                    text_c = "#065F46" if fail_cnt == 0 else "#92400E"
                    sub_c = "#047857" if fail_cnt == 0 else "#B45309"
                    icon = "🎉" if fail_cnt == 0 else "⚠️"
                    title = "파이프라인 완료!" if fail_cnt == 0 else "완료 (일부 실패)"

                    result_ph.markdown(f"""
<div class="result-ok" style="background:{color};border-color:{border}">
  <div style="display:flex;align-items:center;gap:14px">
    <div style="font-size:34px">{icon}</div>
    <div>
      <div style="font-size:16px;font-weight:700;color:{text_c}">{title}</div>
      <div style="font-size:13px;color:{sub_c};margin-top:5px">
        수집 <b>{len(all_prods)}</b>개 → 마진 통과 <b>{len(filtered)}</b>개
        → DB 등록 <b>{len(imported)}</b>개 → 업로드 성공 <b>{ok_cnt}</b>건
        {f'/ 실패 <b>{fail_cnt}</b>건' if fail_cnt else ''}
      </div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

                    time.sleep(1.5)
                    st.rerun()


# ════════════════════════════════════════════════════════════════════════
# TAB 2 · 상품 수집 (수동)
# ════════════════════════════════════════════════════════════════════════
with tab_search:
    col_l, col_r = st.columns([1, 1.8], gap="large")

    with col_l:
        st.markdown("#### 🔍 공급처 검색")
        with st.container(border=True):
            src_sel = st.selectbox(
                "공급처",
                ["onchannel", "domeggook"],
                format_func=src_name,
            )
            kw2 = st.text_input("키워드", placeholder="예: 텀블러")
            lim2 = st.slider("최대 수집 수", 5, 50, 20, key="lim2")

            if st.button("🔍 검색", type="primary", use_container_width=True):
                if not kw2.strip():
                    st.warning("키워드를 입력하세요.")
                else:
                    with st.spinner("수집 중..."):
                        try:
                            if src_sel == "onchannel":
                                from app.suppliers.onchannel import search as _s2
                            else:
                                from app.suppliers.domeggook import search as _s2
                            res2 = _s2(keyword=kw2, limit=lim2)
                            st.session_state["sr"] = res2
                            st.session_state["sr_src"] = src_sel
                            if not res2:
                                if src_sel == "domeggook":
                                    st.warning(
                                        "도매꾹 결과 없음\n\n"
                                        "파트너 센터에서 API 키 등록 후 `.env`의 `DOMEGGOOK_API_KEY` 업데이트 필요"
                                    )
                                else:
                                    st.info("결과 없음 — 다른 키워드를 시도하세요.")
                        except Exception as exc:
                            st.error(f"검색 오류: {exc}")

    with col_r:
        sr = st.session_state.get("sr", [])
        sr_src = st.session_state.get("sr_src", "")

        if sr:
            st.markdown(f"**{len(sr)}개 검색됨** ({src_name(sr_src)})")
            for item in sr:
                with st.container(border=True):
                    ia, ib = st.columns([3, 1])
                    with ia:
                        if item.images:
                            st.image(item.images[0], width=72)
                        st.markdown(f"**{item.name[:58]}**")
                        price_txt = f"{item.supply_price:,.0f}원" if item.supply_price > 0 else "가격 미조회"
                        st.caption(f"공급가 {price_txt}  ·  {item.category[:28]}")
                    with ib:
                        if st.button("상세보기", key=f"d_{item.source_id}"):
                            with st.spinner("수집 중..."):
                                try:
                                    if sr_src == "onchannel":
                                        from app.suppliers.onchannel import get_product as _gp
                                    else:
                                        from app.suppliers.domeggook import get_product as _gp
                                    detail = _gp(item.source_id)
                                    if detail:
                                        st.session_state["sel"] = detail
                                    else:
                                        st.error("상세 수집 실패")
                                except Exception as exc:
                                    st.error(str(exc))

        elif "sr" in st.session_state:
            st.markdown('<div class="empty-box"><div class="ei">🔍</div>'
                        '<h3>검색 결과 없음</h3>'
                        '<p>키워드를 바꿔 다시 시도하세요</p></div>',
                        unsafe_allow_html=True)

    # 선택 상품 상세 + 등록
    if "sel" in st.session_state:
        st.divider()
        prod = st.session_state["sel"]
        st.markdown("### 선택된 상품")

        ca, cb = st.columns([1, 2], gap="large")
        with ca:
            if prod.images:
                st.image(prod.images[0], use_container_width=True)
            for img in prod.images[1:3]:
                st.image(img, width=100)

        with cb:
            st.markdown(f"## {prod.name}")
            st.caption(
                f"📂 {prod.category or '카테고리 미확인'}  ·  "
                f"🌍 {prod.origin}  ·  🏷️ {prod.brand or '브랜드 미상'}"
            )
            if prod.options:
                for opt in prod.options:
                    st.caption(f"옵션 · {opt['name']}: {', '.join(opt['values'][:6])}")

            if prod.supply_price <= 0:
                st.warning("공급가 미조회 — 로그인 필요 또는 비공개 상품 (아래에 직접 입력)")
                supply_for_calc = float(st.number_input(
                    "공급가 직접 입력 (원)", value=0, step=500, min_value=0,
                    key="manual_supply"
                ))
            else:
                supply_for_calc = prod.supply_price
                st.metric("공급가", f"{supply_for_calc:,.0f}원")

            sell_price = st.number_input(
                "판매가 (원)",
                value=max(int(supply_for_calc * 3.5), 1000) if supply_for_calc > 0 else 1000,
                step=100,
                min_value=max(int(supply_for_calc), 0),
                key="sp_input",
            )

            if supply_for_calc > 0 and sell_price > 0:
                ship = 3000
                m_c = (sell_price - supply_for_calc - ship - sell_price * 0.107) / sell_price
                m_n = (sell_price - supply_for_calc - ship - sell_price * 0.035) / sell_price
                mc1, mc2 = st.columns(2)
                mc1.metric("쿠팡 예상 마진", f"{m_c:.1%}",
                           delta="✅ 양호" if m_c >= 0.15 else "❌ 마진 부족")
                mc2.metric("스마트스토어 마진", f"{m_n:.1%}",
                           delta="✅ 양호" if m_n >= 0.15 else "❌ 마진 부족")

            ai_sel = st.checkbox("🤖 AI 상품명/설명 자동 생성", value=True, key="ai_sel")

            btn_disabled = supply_for_calc <= 0 or sell_price <= 0
            if st.button("📥 시스템에 등록", type="primary",
                         use_container_width=True, disabled=btn_disabled):
                if prod.supply_price <= 0:
                    prod.supply_price = supply_for_calc
                with st.spinner("AI 최적화 및 등록 중... (최대 30초)"):
                    res3 = import_product(prod.source, prod.source_id, sell_price, ai_sel)
                if res3["status"] in ("imported", "updated"):
                    st.success(f"✅ 등록 완료 — {res3['name']}")
                    del st.session_state["sel"]
                    time.sleep(0.8)
                    st.rerun()
                else:
                    st.error(f"❌ 등록 실패: {res3.get('error', '')}")

            if st.button("← 뒤로", key="back_btn"):
                del st.session_state["sel"]
                st.rerun()


# ════════════════════════════════════════════════════════════════════════
# TAB 3 · 상품 관리
# ════════════════════════════════════════════════════════════════════════
with tab_products:
    hc1, hc2, hc3 = st.columns([2, 1, 1])
    with hc1:
        st_filter = st.selectbox(
            "상태 필터",
            ["전체", "draft", "ready", "listed"],
            format_func=lambda x: {
                "전체": "전체 상품",
                "draft": "처리중",
                "ready": "등록 완료 (업로드 대기)",
                "listed": "판매 중",
            }.get(x, x),
            label_visibility="collapsed",
        )
    with hc2:
        if st.button("🔄 새로고침", use_container_width=True):
            st.rerun()
    with hc3:
        pass

    data3 = list_products(status="" if st_filter == "전체" else st_filter, limit=100)
    items3 = data3["items"]

    if not items3:
        st.markdown('<div class="empty-box"><div class="ei">📦</div>'
                    '<h3>상품 없음</h3>'
                    '<p>자동 파이프라인 또는 수동 수집으로 상품을 등록하세요</p></div>',
                    unsafe_allow_html=True)
    else:
        st.caption(f"총 {data3['total']}개 상품")

        selected: list[int] = []
        for item in items3:
            with st.container(border=True):
                r1, r2, r3, r4 = st.columns([0.25, 2.8, 1.6, 1.4])
                with r1:
                    if st.checkbox("선택", key=f"chk_{item['id']}", label_visibility="collapsed"):
                        selected.append(item["id"])
                with r2:
                    img_tag = ""
                    if item.get("images"):
                        img_tag = (
                            f'<img src="{html.escape(item["images"][0])}" '
                            f'style="width:44px;height:44px;object-fit:cover;'
                            f'border-radius:8px;float:left;margin-right:10px;'
                            f'border:1px solid #E2E8F0">'
                        )
                    st.markdown(
                        f'{img_tag}'
                        f'{badge(item["status"])} '
                        f'<strong style="font-size:14px">{html.escape(item["name"][:52])}</strong><br>'
                        f'<small style="color:#94A3B8">'
                        f'{src_name(item["source"])} · {html.escape(item["category"][:26])}'
                        f'</small>',
                        unsafe_allow_html=True,
                    )
                with r3:
                    st.markdown(
                        f'<div style="font-size:13px;color:#64748B;margin-top:4px">공급가</div>'
                        f'<div style="font-weight:700;color:#0F172A">{item["supply_price"]:,.0f}원</div>'
                        f'<div style="font-size:13px;color:#64748B;margin-top:2px">판매가</div>'
                        f'<div style="font-weight:600;color:#4F46E5">{item["sell_price"]:,.0f}원</div>',
                        unsafe_allow_html=True,
                    )
                with r4:
                    if st.button("📤 업로드", key=f"up_{item['id']}", use_container_width=True,
                                 type="primary"):
                        with st.spinner("업로드 중..."):
                            results = upload_product(item["id"], ["smartstore", "coupang"])
                        for r in results:
                            if r["status"] == "success":
                                st.success(f"✅ {plat_name(r['platform'])} 완료")
                            else:
                                st.error(f"❌ {plat_name(r['platform'])}: {r.get('error','')[:60]}")
                        time.sleep(0.8)
                        st.rerun()
                    if st.button("🗑 삭제", key=f"del_{item['id']}", use_container_width=True):
                        delete_product(item["id"])
                        st.rerun()

        if selected:
            st.divider()
            bc1, bc2, bc3 = st.columns([1.5, 1.5, 1])
            with bc1:
                bulk_plats = st.multiselect(
                    "업로드 플랫폼",
                    ["smartstore", "coupang"],
                    default=["smartstore", "coupang"],
                    format_func=plat_name,
                    label_visibility="collapsed",
                )
            with bc2:
                st.markdown(f"<div style='padding:8px 0;color:#64748B;font-size:14px'>"
                            f"선택된 상품 <strong>{len(selected)}</strong>개</div>",
                            unsafe_allow_html=True)
            with bc3:
                if st.button(f"일괄 업로드 ({len(selected)}개)",
                             type="primary", use_container_width=True, disabled=not bulk_plats):
                    total_ok = total_fail = 0
                    with st.spinner(f"{len(selected)}개 업로드 중..."):
                        for pid in selected:
                            for r in upload_product(pid, bulk_plats):
                                if r["status"] == "success":
                                    total_ok += 1
                                else:
                                    total_fail += 1
                    st.success(f"완료 — 성공 {total_ok}건 / 실패 {total_fail}건")
                    time.sleep(0.8)
                    st.rerun()


# ════════════════════════════════════════════════════════════════════════
# TAB 4 · 업로드 현황
# ════════════════════════════════════════════════════════════════════════
with tab_status:
    sc1, sc2 = st.columns([3, 1])
    with sc1:
        st.markdown("#### 📊 플랫폼별 업로드 현황")
    with sc2:
        if st.button("🔄 새로고침", key="ref_s", use_container_width=True):
            st.rerun()

    # 요약 카드
    mc1, mc2, mc3, mc4 = st.columns(4)
    with mc1:
        st.markdown(metric_card("📦", p["total"], "전체 상품"), unsafe_allow_html=True)
    with mc2:
        st.markdown(metric_card("✅", u["smartstore"], "스마트스토어"), unsafe_allow_html=True)
    with mc3:
        st.markdown(metric_card("🟡", u["coupang"], "쿠팡"), unsafe_allow_html=True)
    with mc4:
        st.markdown(metric_card("❌", u["failed"], "업로드 실패"), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    data4 = list_products(limit=200)
    if not data4["items"]:
        st.markdown('<div class="empty-box"><div class="ei">📊</div>'
                    '<h3>업로드 내역 없음</h3></div>',
                    unsafe_allow_html=True)
    else:
        for item in data4["items"]:
            detail = get_product_detail(item["id"])
            if not detail:
                continue
            listings = detail.get("listings", [])
            ss = next((l for l in listings if l["platform"] == "smartstore"), None)
            cp = next((l for l in listings if l["platform"] == "coupang"), None)

            def _badge(listing):
                if not listing:
                    return badge("pending")
                return badge(listing["status"])

            with st.container(border=True):
                d1, d2, d3, d4 = st.columns([3, 1.5, 1.5, 0.8])
                with d1:
                    st.markdown(
                        f'<strong style="font-size:14px">{html.escape(item["name"][:48])}</strong><br>'
                        f'<small style="color:#94A3B8">ID {item["id"]} · {src_name(item["source"])}</small>',
                        unsafe_allow_html=True,
                    )
                with d2:
                    st.markdown(
                        f'스마트스토어 {_badge(ss)}',
                        unsafe_allow_html=True,
                    )
                    if ss and ss.get("platform_id"):
                        st.caption(f"No. {ss['platform_id'][:18]}")
                    if ss and ss.get("error"):
                        st.caption(f"⚠️ {ss['error'][:55]}")
                with d3:
                    st.markdown(f'쿠팡 {_badge(cp)}', unsafe_allow_html=True)
                    if cp and cp.get("platform_id"):
                        st.caption(f"No. {cp['platform_id'][:18]}")
                    if cp and cp.get("error"):
                        st.caption(f"⚠️ {cp['error'][:55]}")
                with d4:
                    if st.button("재시도", key=f"retry_{item['id']}"):
                        with st.spinner("재시도 중..."):
                            for r in upload_product(item["id"], ["smartstore", "coupang"]):
                                if r["status"] == "success":
                                    st.success(f"✅ {plat_name(r['platform'])}")
                                else:
                                    st.error(f"❌ {r.get('error','')[:50]}")
                        time.sleep(0.8)
                        st.rerun()


# ════════════════════════════════════════════════════════════════════════
# TAB · SEO 최적화 (기존 등록 상품 검색 최적화)
# ════════════════════════════════════════════════════════════════════════
with tab_seo:
    st.markdown("""
<div style="
  background:linear-gradient(135deg,#0C4A6E 0%,#0369A1 55%,#0EA5E9 100%);
  padding:20px 24px;border-radius:14px;margin-bottom:20px;
  box-shadow:0 6px 24px rgba(14,165,233,.3);
">
  <div style="color:#fff;font-size:18px;font-weight:800">🔍 SEO 최적화 엔진</div>
  <div style="color:rgba(255,255,255,.7);font-size:12px;margin-top:4px">
    기존 등록 상품 AI 분석 · 상품명/키워드/설명 재작성 제안 · 검수 후 반영 · 성과 비교
  </div>
</div>
""", unsafe_allow_html=True)

    seo_sub_run, seo_sub_review, seo_sub_apply, seo_sub_perf = st.tabs([
        "🚀 분석 실행", "✅ 검수", "📤 적용", "📈 성과 비교",
    ])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab A · 분석 실행
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with seo_sub_run:
        seo_platform = st.selectbox("플랫폼", ["smartstore", "coupang"],
                                    format_func=plat_name, key="seo_run_platform")

        seo_sync_col1, seo_sync_col2 = st.columns([3, 1])
        with seo_sync_col1:
            st.caption(
                "이 앱을 거치지 않고 판매자센터에서 직접 등록한 상품이 있다면 "
                "먼저 동기화해야 아래 목록에 나타납니다."
            )
        with seo_sync_col2:
            if st.button("🔄 카탈로그 동기화", key="seo_sync_btn", use_container_width=True):
                with st.spinner(f"{plat_name(seo_platform)} 상품 목록 가져오는 중..."):
                    seo_sync_res = sync_platform_catalog(seo_platform)
                if seo_sync_res.get("ok"):
                    st.success(
                        f"✅ {seo_sync_res['total_found']}개 발견 · "
                        f"신규 {seo_sync_res['created']} · 연결 {seo_sync_res['linked']} · "
                        f"스킵 {seo_sync_res['skipped']}"
                    )
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error(f"❌ 동기화 실패: {seo_sync_res.get('error', '')}")

        seo_targets = list_seo_target_products(seo_platform)

        if not seo_targets:
            st.info(f"{plat_name(seo_platform)}에 등록 완료된 상품이 없습니다. "
                   f"위 '카탈로그 동기화'를 실행하거나 **업로드** 탭에서 상품을 등록하세요.", icon="ℹ️")
        else:
            seo_selected = st.multiselect(
                "분석할 상품 선택",
                options=[t["id"] for t in seo_targets],
                format_func=lambda pid: next(
                    (f"{t['name'][:40]} (ID {pid})" for t in seo_targets if t["id"] == pid), str(pid)
                ),
                key="seo_run_targets",
            )
            seo_competitor_url = st.text_input(
                "경쟁사 상품 URL (선택 — 입력 시 키워드/강약점 비교 분석 추가)",
                key="seo_run_competitor",
            )
            if st.button("🚀 AI SEO 분석 실행", type="primary",
                        disabled=not seo_selected, key="seo_run_btn"):
                with st.spinner(f"{len(seo_selected)}개 상품 분석 중... (Claude 호출)"):
                    seo_results = run_seo_analysis(seo_selected, seo_platform, seo_competitor_url)
                ok_count = sum(1 for r in seo_results if r.get("ok"))
                st.success(f"✅ {ok_count}/{len(seo_results)}건 분석 완료 — 검수 탭에서 확인하세요")
                for r in seo_results:
                    if not r.get("ok"):
                        st.error(f"❌ {r.get('error', '알 수 없는 오류')}")
                time.sleep(0.5)
                st.rerun()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab B · 검수 (승인/반려)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with seo_sub_review:
        seo_reviewer = st.text_input("검수자", value="관리자", key="seo_reviewer_name")
        seo_pending = [r for r in list_seo_revisions() if r["status"] in ("DRAFT", "REVIEW_PENDING")]

        if not seo_pending:
            st.markdown('<div class="empty-box"><div class="ei">✅</div>'
                       '<h3>검수 대기중인 SEO 제안이 없습니다</h3></div>',
                       unsafe_allow_html=True)
        else:
            for rev in seo_pending:
                with st.container(border=True):
                    rc1, rc2 = st.columns([3, 1])
                    with rc1:
                        st.markdown(
                            f'<strong style="font-size:14px">상품 ID {rev["product_id"]}'
                            f' · {plat_name(rev["platform"])}</strong> {badge(rev["status"])}',
                            unsafe_allow_html=True,
                        )
                        st.caption(f"SEO 점수 {rev['score_before']:.1f} → {rev['score_after']:.1f}점")
                    with rc2:
                        st.metric("키워드", f"{len(rev['suggested_keywords'])}개")

                    st.markdown("**원본 상품명**")
                    st.text(rev["original_name"])
                    st.markdown("**추천 상품명 후보**")
                    for i, name in enumerate(rev["suggested_names"][:5], 1):
                        st.text(f"{i}. {name}")
                    with st.expander("추천 키워드 전체 / 상세설명 미리보기"):
                        st.write(", ".join(rev["suggested_keywords"]))
                        st.markdown(rev["suggested_detail_html"], unsafe_allow_html=True)
                    if rev["duplicate_of_product_id"]:
                        st.warning(f"⚠️ 유사 상품 ID {rev['duplicate_of_product_id']}과 이름이 거의 동일합니다",
                                  icon="⚠️")

                    ac1, ac2 = st.columns([1, 3])
                    with ac1:
                        if st.button("✅ 승인", key=f"seo_approve_{rev['id']}",
                                    type="primary", use_container_width=True):
                            approve_seo_revision(rev["id"], seo_reviewer)
                            st.rerun()
                    with ac2:
                        seo_reject_reason = st.text_input(
                            "반려 사유", key=f"seo_reject_reason_{rev['id']}",
                            label_visibility="collapsed", placeholder="반려 사유 (선택 입력 후 반려 버튼)",
                        )
                    if st.button("❌ 반려", key=f"seo_reject_{rev['id']}"):
                        reject_seo_revision(rev["id"], seo_reject_reason or "검수자 반려", seo_reviewer)
                        st.rerun()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab C · 적용
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with seo_sub_apply:
        seo_approved = list_seo_revisions(status="APPROVED")
        if not seo_approved:
            st.markdown('<div class="empty-box"><div class="ei">📤</div>'
                       '<h3>반영 대기중인 승인 건이 없습니다</h3></div>',
                       unsafe_allow_html=True)
        else:
            st.download_button(
                "📥 승인 건 전체 Excel(CSV) 내보내기",
                data=export_seo_revisions_csv(status="APPROVED"),
                file_name="seo_approved_revisions.csv",
                mime="text/csv",
                key="seo_export_approved",
            )
            st.markdown("<br>", unsafe_allow_html=True)

            for rev in seo_approved:
                with st.container(border=True):
                    st.markdown(
                        f'<strong style="font-size:14px">상품 ID {rev["product_id"]}'
                        f' · {plat_name(rev["platform"])}</strong> {badge(rev["status"])}',
                        unsafe_allow_html=True,
                    )
                    seo_apply_names = rev["suggested_names"]
                    st.caption(f"반영될 상품명: {seo_apply_names[0] if seo_apply_names else rev['original_name']}")

                    seo_apply_confirmed = True
                    if rev.get("experimental"):
                        st.warning(
                            "⚠️ 실험적 기능 — 쿠팡 상품수정 API는 실제 계정으로 검증되지 않았습니다. "
                            "반영 시 카테고리/이미지 등에 따라 재승인 심사가 걸릴 수 있으니, "
                            "반영 후 Wing 관리자 화면에서 반드시 결과를 확인하세요.",
                            icon="⚠️",
                        )
                        seo_apply_confirmed = st.checkbox(
                            "위 내용을 확인했으며 쿠팡 반영을 진행합니다",
                            key=f"seo_confirm_{rev['id']}",
                        )

                    if rev["can_auto_apply"]:
                        if st.button("🚀 지금 반영", key=f"seo_apply_{rev['id']}", type="primary",
                                    disabled=not seo_apply_confirmed):
                            with st.spinner("플랫폼에 반영 중..."):
                                seo_apply_res = apply_seo_revision(rev["id"])
                            if seo_apply_res.get("ok"):
                                st.success("✅ 반영 완료")
                            else:
                                st.error(f"❌ 반영 실패: {seo_apply_res.get('error','')}")
                            time.sleep(0.5)
                            st.rerun()
                    else:
                        st.info(
                            "이 플랫폼은 자동 반영을 지원하지 않습니다. "
                            "위 Excel(CSV)을 내려받아 관리자 화면에서 직접 반영하세요.",
                            icon="ℹ️",
                        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab D · 성과 비교 (반영 전/후)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with seo_sub_perf:
        import plotly.graph_objects as go

        pf1, pf2, pf3 = st.columns([2, 2, 1])
        with pf1:
            seo_perf_pid = st.number_input("상품 ID", min_value=1, step=1, key="seo_perf_pid")
        with pf2:
            seo_perf_platform = st.selectbox("플랫폼", ["smartstore", "coupang"],
                                             format_func=plat_name, key="seo_perf_platform")
        with pf3:
            st.markdown("<br>", unsafe_allow_html=True)
            seo_perf_go = st.button("조회", key="seo_perf_btn", use_container_width=True)

        if seo_perf_go:
            seo_perf = get_seo_before_after(int(seo_perf_pid), seo_perf_platform)
            if not seo_perf.get("ok"):
                st.info(seo_perf.get("error", "적용된 SEO 변경 이력이 없습니다"), icon="ℹ️")
            else:
                seo_before, seo_after = seo_perf["before"], seo_perf["after"]
                st.caption(f"반영일: {seo_perf['applied_at']} · "
                          f"반영 전 {seo_before['days']}일 vs 반영 후 {seo_after['days']}일 비교")

                pm1, pm2, pm3, pm4 = st.columns(4)
                pm1.metric("평균 CTR", f"{seo_after['avg_ctr']*100:.2f}%",
                          f"{(seo_after['avg_ctr']-seo_before['avg_ctr'])*100:+.2f}%p")
                pm2.metric("평균 CVR", f"{seo_after['avg_cvr']*100:.2f}%",
                          f"{(seo_after['avg_cvr']-seo_before['avg_cvr'])*100:+.2f}%p")
                pm3.metric("주문수", seo_after["total_orders"],
                          seo_after["total_orders"] - seo_before["total_orders"])
                pm4.metric("매출", f"{seo_after['total_revenue']:,.0f}원",
                          f"{seo_after['total_revenue']-seo_before['total_revenue']:+,.0f}원")

                fig_seo = go.Figure()
                fig_seo.add_trace(go.Bar(
                    x=["CTR", "CVR"], y=[seo_before["avg_ctr"]*100, seo_before["avg_cvr"]*100],
                    name="반영 전", marker_color="#94A3B8",
                ))
                fig_seo.add_trace(go.Bar(
                    x=["CTR", "CVR"], y=[seo_after["avg_ctr"]*100, seo_after["avg_cvr"]*100],
                    name="반영 후", marker_color="#0EA5E9",
                ))
                fig_seo.update_layout(
                    height=260, barmode="group",
                    margin=dict(l=0, r=0, t=8, b=0),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    legend=dict(orientation="h", y=1.15, x=0, font=dict(size=12)),
                    yaxis=dict(gridcolor="#F1F5F9", ticksuffix="%"),
                )
                st.plotly_chart(fig_seo, use_container_width=True, config={"displayModeBar": False})


# ════════════════════════════════════════════════════════════════════════
# TAB 5 · 시장 분석 (Market Intelligence Engine)
# ════════════════════════════════════════════════════════════════════════
with tab_market:
    import pandas as pd

    # ── 헤더 ──────────────────────────────────────────────────────────
    st.markdown("""
<div style="
  background:linear-gradient(135deg,#0F172A 0%,#1E3A5F 60%,#1D4ED8 100%);
  padding:20px 24px;border-radius:14px;margin-bottom:20px;
  box-shadow:0 6px 24px rgba(29,78,216,.3);
">
  <div style="color:#fff;font-size:18px;font-weight:800">🧠 Market Intelligence Engine</div>
  <div style="color:rgba(255,255,255,.6);font-size:12px;margin-top:4px">
    네이버 데이터랩 트렌드 · 쿠팡 베스트셀러 · Claude Opportunity Score
  </div>
</div>
""", unsafe_allow_html=True)

    # ── 검색 입력 ──────────────────────────────────────────────────────
    col_inp, col_btn, col_refresh = st.columns([3, 1, 1])
    with col_inp:
        mkt_kw = st.text_input(
            "분석 키워드",
            placeholder="예: 무선 이어폰, 캠핑 의자, 텀블러",
            label_visibility="collapsed",
            key="mkt_kw",
        )
    with col_btn:
        mkt_run = st.button("🧠 분석 시작", type="primary", use_container_width=True)
    with col_refresh:
        mkt_force = st.button("🔄 강제 갱신", use_container_width=True,
                               help="24시간 캐시를 무시하고 새로 수집·분석")

    # ── 분석 실행 ──────────────────────────────────────────────────────
    if (mkt_run or mkt_force) and mkt_kw.strip():
        with st.spinner(f"'{mkt_kw}' 시장 데이터 수집 및 AI 분석 중... (최대 30초)"):
            try:
                mkt_result = analyze_market(mkt_kw.strip(), force_refresh=bool(mkt_force))
                st.session_state["mkt_result"] = mkt_result
            except Exception as exc:
                st.error(f"분석 오류: {exc}")
    elif (mkt_run or mkt_force) and not mkt_kw.strip():
        st.warning("키워드를 입력하세요.")

    # ── 결과 표시 ──────────────────────────────────────────────────────
    mkt = st.session_state.get("mkt_result")
    if mkt:
        score = int(mkt.get("opportunity_score", 0))
        bd = mkt.get("score_breakdown", {})
        trend_pts = mkt.get("trend_data", [])
        shop = mkt.get("shopping_stats", {})
        best = mkt.get("coupang_best", [])
        tags = mkt.get("tags", [])
        risks = mkt.get("risk_factors", [])

        # 점수 색상
        if score >= 76:
            sc_color, sc_icon, sc_label = "#1D4ED8", "💎", "우수"
        elif score >= 61:
            sc_color, sc_icon, sc_label = "#047857", "✅", "양호"
        elif score >= 41:
            sc_color, sc_icon, sc_label = "#B45309", "🟡", "보통"
        else:
            sc_color, sc_icon, sc_label = "#B91C1C", "⚠️", "주의"

        cached_tag = (
            '<span style="font-size:11px;background:#F1F5F9;color:#64748B;'
            'padding:2px 8px;border-radius:8px;margin-left:8px">캐시됨</span>'
            if mkt.get("cached") else ""
        )

        st.markdown(f"""
<div style="display:flex;align-items:center;gap:6px;margin-bottom:16px">
  <span style="font-size:18px;font-weight:800;color:#0F172A">
    '{html.escape(mkt['keyword'])}' 분석 결과
  </span>
  {cached_tag}
</div>
""", unsafe_allow_html=True)

        # ── Row 1: 점수 카드 + 트렌드 차트 ───────────────────────────
        rc1, rc2 = st.columns([1, 2.2], gap="large")

        with rc1:
            st.markdown(f"""
<div style="
  text-align:center;padding:28px 16px;
  background:linear-gradient(135deg,{sc_color}18,{sc_color}08);
  border:2px solid {sc_color}40;border-radius:16px;
">
  <div style="font-size:56px;font-weight:900;color:{sc_color};line-height:1">{score}</div>
  <div style="font-size:13px;color:{sc_color};font-weight:700;margin-top:6px">{sc_icon} 기회점수 {sc_label}</div>
  <hr style="border-color:{sc_color}20;margin:12px 0">
  <div style="font-size:12px;color:#475569;text-align:left;padding:0 4px">
    {"".join(
      f'<div style="display:flex;justify-content:space-between;margin-bottom:6px">'
      f'<span>{lbl}</span>'
      f'<span style="font-weight:700;color:{sc_color}">{val}/{mx}</span></div>'
      f'<div style="background:#E2E8F0;border-radius:4px;height:5px;margin-bottom:10px">'
      f'<div style="width:{int(val/mx*100)}%;background:{sc_color};height:5px;border-radius:4px"></div>'
      f'</div>'
      for lbl, key, mx in [
        ("📈 트렌드", "trend", 30),
        ("🎯 경쟁여지", "competition", 25),
        ("💰 마진가능성", "margin", 25),
        ("📦 수요규모", "demand", 20),
      ]
      for val in [bd.get(key, 0)]
    )}
  </div>
</div>
""", unsafe_allow_html=True)

            # 태그
            if tags:
                st.markdown(
                    " ".join(
                        f'<span style="display:inline-block;margin:2px;padding:3px 10px;'
                        f'background:#DBEAFE;color:#1D4ED8;border-radius:12px;'
                        f'font-size:12px;font-weight:600">#{t}</span>'
                        for t in tags
                    ),
                    unsafe_allow_html=True,
                )
            if risks:
                for r in risks:
                    st.caption(f"⚠️ {r}")

        with rc2:
            if trend_pts:
                df_trend = pd.DataFrame(trend_pts).set_index("period")
                df_trend.columns = ["검색량 지수"]
                st.markdown("**📈 네이버 검색 트렌드 (최근 12개월)**")
                st.line_chart(df_trend, use_container_width=True, height=220)
            else:
                st.markdown("**📈 네이버 검색 트렌드**")
                st.info(
                    "데이터랩 데이터 없음 — 네이버 개발자센터에서 해당 앱에\n"
                    "**'데이터랩 트렌드'** 권한을 추가하면 트렌드 차트가 표시됩니다.",
                    icon="ℹ️",
                )

            # 쇼핑 통계
            if shop.get("total_items"):
                sm1, sm2, sm3 = st.columns(3)
                sm1.markdown(
                    metric_card("🛍️", f"{shop['total_items']:,}", "쇼핑 상품 수"),
                    unsafe_allow_html=True,
                )
                sm2.markdown(
                    metric_card("💰", f"{shop['avg_price']:,}원", "평균 판매가"),
                    unsafe_allow_html=True,
                )
                sm3.markdown(
                    metric_card("📊", f"{shop['min_price']:,}~{shop['max_price']:,}", "가격 범위"),
                    unsafe_allow_html=True,
                )
                if shop.get("top_brands"):
                    st.caption("주요 브랜드: " + " · ".join(shop["top_brands"][:5]))

        st.divider()

        # ── Row 2: 쿠팡 베스트셀러 ────────────────────────────────────
        st.markdown("**🏆 쿠팡 베스트셀러**")
        if best:
            header_cols = st.columns([0.5, 3.5, 1.2, 1, 1.5, 1.3])
            for col, hdr in zip(header_cols,
                                ["순위", "상품명", "판매가", "별점", "리뷰수", "배송"]):
                col.markdown(
                    f'<div style="font-size:11px;font-weight:700;color:#94A3B8;'
                    f'text-transform:uppercase;letter-spacing:.05em">{hdr}</div>',
                    unsafe_allow_html=True,
                )
            for item in best:
                bc0, bc1, bc2, bc3, bc4, bc5 = st.columns([0.5, 3.5, 1.2, 1, 1.5, 1.3])
                bc0.markdown(
                    f'<div style="font-weight:800;color:{"#F59E0B" if item["rank"] <= 3 else "#94A3B8"};'
                    f'font-size:16px;padding-top:4px">{item["rank"]}</div>',
                    unsafe_allow_html=True,
                )
                bc1.markdown(
                    f'<div style="font-size:13px;font-weight:600;color:#0F172A;padding-top:4px">'
                    f'{html.escape(item["name"][:45])}</div>',
                    unsafe_allow_html=True,
                )
                bc2.markdown(
                    f'<div style="font-size:13px;font-weight:700;color:#4F46E5;padding-top:4px">'
                    f'{item["price"]:,}원</div>',
                    unsafe_allow_html=True,
                )
                bc3.markdown(
                    f'<div style="font-size:13px;color:#0F172A;padding-top:4px">'
                    f'{"★" * int(item["rating"])}{"☆" * (5 - int(item["rating"]))}'
                    f' {item["rating"]}</div>',
                    unsafe_allow_html=True,
                )
                bc4.markdown(
                    f'<div style="font-size:13px;color:#475569;padding-top:4px">'
                    f'{item["review_count"]:,}개</div>',
                    unsafe_allow_html=True,
                )
                badge_html = ""
                if item.get("badge") == "로켓배송":
                    badge_html = (
                        '<span style="background:#FEF3C7;color:#B45309;'
                        'padding:2px 7px;border-radius:8px;font-size:11px;font-weight:700">🚀 로켓</span>'
                    )
                bc5.markdown(badge_html or '<span style="color:#94A3B8;font-size:12px">일반</span>',
                             unsafe_allow_html=True)
        else:
            st.info(
                "쿠팡 베스트셀러 데이터를 가져오지 못했습니다. "
                "쿠팡이 일시적으로 차단했거나 네트워크 문제일 수 있습니다.",
                icon="ℹ️",
            )

        st.divider()

        # ── Row 3: AI 전략 추천 ────────────────────────────────────────
        st.markdown("**🤖 Claude AI 판매 전략 추천**")
        rec = mkt.get("recommendation", "")
        if rec:
            st.markdown(
                f'<div style="background:#F8FAFF;border-left:4px solid #4F46E5;'
                f'padding:14px 18px;border-radius:0 10px 10px 0;'
                f'color:#1E293B;font-size:14px;line-height:1.8">{html.escape(rec)}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("추천 없음")

        st.markdown(
            f'<div style="color:#94A3B8;font-size:11px;margin-top:8px">'
            f'분석 시각: {mkt["analyzed_at"][:16].replace("T", " ")} UTC'
            f'{"  ·  캐시 사용" if mkt.get("cached") else ""}</div>',
            unsafe_allow_html=True,
        )

    else:
        # 빈 상태 + 최근 분석 히스토리
        st.markdown(
            '<div class="empty-box"><div class="ei">🧠</div>'
            '<h3>키워드를 입력하고 분석을 시작하세요</h3>'
            '<p>네이버 트렌드 · 쿠팡 베스트 · AI 기회점수를 한눈에 확인</p>'
            '</div>',
            unsafe_allow_html=True,
        )
        history = get_market_history(limit=10)
        if history:
            st.markdown("##### 🕑 최근 분석 키워드")
            for h in history:
                hc1, hc2, hc3 = st.columns([2, 1, 2])
                with hc1:
                    if st.button(f"🔍 {h['keyword']}", key=f"hist_{h['keyword']}",
                                 use_container_width=True):
                        st.session_state["mkt_kw"] = h["keyword"]
                        with st.spinner("불러오는 중..."):
                            st.session_state["mkt_result"] = analyze_market(h["keyword"])
                        st.rerun()
                with hc2:
                    score_h = int(h["opportunity_score"])
                    color_h = "#1D4ED8" if score_h >= 76 else "#047857" if score_h >= 61 else "#B45309" if score_h >= 41 else "#B91C1C"
                    st.markdown(
                        f'<div style="font-size:22px;font-weight:800;color:{color_h};'
                        f'padding-top:4px">{score_h}점</div>',
                        unsafe_allow_html=True,
                    )
                with hc3:
                    tags_h = h.get("tags", [])
                    st.markdown(
                        " ".join(
                            f'<span style="background:#F1F5F9;color:#475569;'
                            f'padding:2px 7px;border-radius:8px;font-size:11px">#{t}</span>'
                            for t in tags_h[:3]
                        ) or "<span style='color:#94A3B8;font-size:12px'>태그 없음</span>",
                        unsafe_allow_html=True,
                    )


# ════════════════════════════════════════════════════════════════════════
# TAB 6 · 정산 & 세금 (Settlement Engine)
# ════════════════════════════════════════════════════════════════════════
with tab_settle:
    import pandas as pd
    from app.settlement.calculator import PLATFORM_FEE_RATES, SETTLEMENT_CYCLES, next_settlement_date
    from app.settlement.tax_engine import format_krw

    # ── 헤더 ──────────────────────────────────────────────────────────
    st.markdown("""
<div style="
  background:linear-gradient(135deg,#064E3B 0%,#065F46 55%,#047857 100%);
  padding:20px 24px;border-radius:14px;margin-bottom:20px;
  box-shadow:0 6px 24px rgba(4,120,87,.3);
">
  <div style="color:#fff;font-size:18px;font-weight:800">💰 Settlement Engine</div>
  <div style="color:rgba(255,255,255,.6);font-size:12px;margin-top:4px">
    실시간 순이익 정산 · 부가세 · 종합소득세 추정 대시보드
  </div>
</div>
""", unsafe_allow_html=True)

    # ── 기간 선택 ──────────────────────────────────────────────────────
    now_dt = __import__("datetime").datetime.now()
    sc1, sc2, sc3 = st.columns([1, 1, 2])
    with sc1:
        sel_year = st.selectbox("연도", list(range(now_dt.year, now_dt.year - 4, -1)),
                                 index=0, key="settle_year", label_visibility="collapsed")
    with sc2:
        sel_month = st.selectbox("월", list(range(1, 13)),
                                  index=now_dt.month - 1, key="settle_month",
                                  format_func=lambda m: f"{m}월",
                                  label_visibility="collapsed")
    with sc3:
        if st.button("🔄 새로고침", key="settle_ref", use_container_width=True):
            st.rerun()

    # ── 대시보드 데이터 로드 ────────────────────────────────────────────
    dash = get_settlement_dashboard(year=sel_year, month=sel_month)
    sm = dash["summary"]
    by_plat = dash["by_platform"]
    monthly = dash["monthly"]
    tax = dash["tax_estimate"]

    # ── KPI 카드 행 ────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    kpi_items = [
        (k1, "🛒", sm["order_count"], "이번 달 주문"),
        (k2, "💵", format_krw(sm["gross_revenue"]), "이번 달 총매출"),
        (k3, "💚", format_krw(sm["net_profit"]), "이번 달 순이익"),
        (k4, "📊", f"{sm['margin_rate']:.1%}", "순이익률"),
        (k5, "🏛️", format_krw(sm["vat_payable"]), "이번 달 부가세"),
    ]
    for col, icon, val, lbl in kpi_items:
        with col:
            profit_color = ""
            if lbl == "이번 달 순이익":
                profit_color = "color:#047857;" if sm["net_profit"] >= 0 else "color:#DC2626;"
            st.markdown(
                f'<div class="m-card">'
                f'<div class="m-icon">{icon}</div>'
                f'<div class="m-value" style="{profit_color}">{val}</div>'
                f'<div class="m-label">{lbl}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 내부 subtab ─────────────────────────────────────────────────────
    sub_dash, sub_input, sub_orders, sub_tax = st.tabs([
        "📈 수익 분석", "➕ 주문 입력", "📋 주문 내역", "🏛️ 세금 계산기",
    ])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab A · 수익 분석
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with sub_dash:
        # ── 플랫폼별 카드 ────────────────────────────────────────────
        st.markdown("#### 플랫폼별 이번 달 정산 현황")
        pc1, pc2 = st.columns(2)

        for col, plat, icon, color in [
            (pc1, "coupang", "🟡", "#B45309"),
            (pc2, "smartstore", "🟢", "#047857"),
        ]:
            pd_data = by_plat.get(plat, {})
            plat_label = {"coupang": "쿠팡", "smartstore": "스마트스토어"}[plat]
            next_date = next_settlement_date(plat)
            with col:
                st.markdown(f"""
<div style="border:1px solid #E2E8F0;border-radius:14px;padding:18px 20px;background:#fff">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
    <span style="font-size:16px;font-weight:800;color:#0F172A">{icon} {plat_label}</span>
    <span style="font-size:11px;background:#F1F5F9;color:#64748B;padding:3px 10px;border-radius:8px">
      다음 정산 {next_date}
    </span>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
    <div><div style="font-size:11px;color:#94A3B8;font-weight:600">주문 수</div>
      <div style="font-size:20px;font-weight:800;color:#0F172A">{pd_data.get("order_count",0)}건</div></div>
    <div><div style="font-size:11px;color:#94A3B8;font-weight:600">총매출</div>
      <div style="font-size:18px;font-weight:700;color:#0F172A">{format_krw(pd_data.get("gross_revenue",0))}</div></div>
    <div><div style="font-size:11px;color:#94A3B8;font-weight:600">순이익</div>
      <div style="font-size:18px;font-weight:800;color:{color}">{format_krw(pd_data.get("net_profit",0))}</div></div>
    <div><div style="font-size:11px;color:#94A3B8;font-weight:600">플랫폼 수수료</div>
      <div style="font-size:16px;font-weight:600;color:#DC2626">-{format_krw(pd_data.get("platform_fee",0))}</div></div>
  </div>
  <div style="margin-top:10px;font-size:11px;color:#94A3B8">{SETTLEMENT_CYCLES.get(plat,"")}</div>
</div>
""", unsafe_allow_html=True)

        st.divider()

        # ── 월별 수익 차트 ────────────────────────────────────────────
        st.markdown(f"#### {sel_year}년 월별 수익 추이")
        df_month = pd.DataFrame(monthly)
        if df_month["gross_revenue"].sum() > 0:
            df_chart = df_month.set_index("label")[["gross_revenue", "net_profit"]].rename(
                columns={"gross_revenue": "총매출", "net_profit": "순이익"}
            )
            st.bar_chart(df_chart, use_container_width=True, height=260)
        else:
            st.info("주문 데이터가 없습니다. '주문 입력' 탭에서 주문을 등록하세요.", icon="ℹ️")

        # ── 월별 상세 테이블 ──────────────────────────────────────────
        with st.expander("월별 상세 수치"):
            rows_m = []
            for mo in monthly:
                rows_m.append({
                    "월": mo["label"],
                    "주문 수": mo["order_count"],
                    "총매출": f"{mo['gross_revenue']:,.0f}원",
                    "순이익": f"{mo['net_profit']:,.0f}원",
                    "순이익률": f"{mo['net_profit']/mo['gross_revenue']*100:.1f}%" if mo['gross_revenue'] > 0 else "-",
                })
            st.dataframe(pd.DataFrame(rows_m), use_container_width=True, hide_index=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab B · 주문 입력
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with sub_input:
        left_in, right_in = st.columns([1, 1.2], gap="large")

        with left_in:
            st.markdown("#### ➕ 주문 등록")
            with st.container(border=True):
                # 상품 선택
                prods_all = list_products(limit=200)["items"]
                if not prods_all:
                    st.warning("등록된 상품이 없습니다. 먼저 상품을 수집·등록하세요.")
                    st.stop()

                prod_options = {f"[{p['id']}] {p['name'][:40]} (공급가 {p['supply_price']:,.0f}원)": p for p in prods_all}
                selected_prod_key = st.selectbox("상품 선택", list(prod_options.keys()), key="ord_prod")
                sel_prod = prod_options[selected_prod_key]

                plat_sel = st.selectbox("플랫폼", ["coupang", "smartstore"],
                                         format_func=lambda x: {"coupang": "쿠팡", "smartstore": "스마트스토어"}[x],
                                         key="ord_plat")

                oi1, oi2 = st.columns(2)
                ord_qty = oi1.number_input("수량", value=1, min_value=1, max_value=9999, key="ord_qty")
                ord_sale = oi2.number_input(
                    "판매가 (원)", value=int(sel_prod["sell_price"]),
                    min_value=1, step=100, key="ord_sale"
                )

                st.markdown("**배송비**")
                oi3, oi4 = st.columns(2)
                ord_ship_paid = oi3.number_input("지출 배송비", value=3000, min_value=0, step=500, key="ord_sp",
                                                   help="택배사에 실제 지불한 배송비")
                ord_ship_chg = oi4.number_input("청구 배송비", value=0, min_value=0, step=500, key="ord_sc",
                                                  help="구매자에게 청구한 배송비 (무료배송=0)")

                st.markdown("**추가 비용**")
                oi5, oi6 = st.columns(2)
                ord_ad = oi5.number_input("광고비 (원)", value=0, min_value=0, step=100, key="ord_ad")
                ord_ret = oi6.number_input("반품 처리비 (원)", value=0, min_value=0, step=500, key="ord_ret")

                ord_plat_id = st.text_input("플랫폼 주문번호 (선택)", placeholder="주문번호 직접 입력", key="ord_pid")

                import datetime as _dt
                ord_date = st.date_input("주문일", value=_dt.date.today(), key="ord_date")
                ord_status = st.selectbox("주문 상태", ["completed", "ordered", "shipped", "returned", "cancelled"],
                                           format_func=lambda x: {
                                               "completed": "완료", "ordered": "주문접수",
                                               "shipped": "배송중", "returned": "반품",
                                               "cancelled": "취소"
                                           }[x], key="ord_status")
                ord_memo = st.text_input("메모 (선택)", key="ord_memo")

                if st.button("💾 주문 등록", type="primary", use_container_width=True):
                    res = add_order(
                        product_id=sel_prod["id"],
                        platform=plat_sel,
                        unit_sale_price=float(ord_sale),
                        quantity=int(ord_qty),
                        shipping_fee_paid=float(ord_ship_paid),
                        shipping_fee_charged=float(ord_ship_chg),
                        ad_cost=float(ord_ad),
                        return_cost=float(ord_ret),
                        platform_order_id=ord_plat_id,
                        status=ord_status,
                        ordered_at=_dt.datetime.combine(ord_date, _dt.time()),
                        memo=ord_memo,
                    )
                    if res["status"] == "ok":
                        st.success(f"✅ 등록 완료 — 순이익 {format_krw(res['net_profit'])}")
                        time.sleep(0.6)
                        st.rerun()
                    else:
                        st.error(f"❌ {res.get('error','')}")

        with right_in:
            st.markdown("#### 📐 실시간 순이익 미리보기")
            with st.container(border=True):
                preview = get_profit_calculator_preview(
                    platform=st.session_state.get("ord_plat", "coupang"),
                    unit_sale_price=float(st.session_state.get("ord_sale", sel_prod["sell_price"])),
                    unit_supply_price=float(sel_prod["supply_price"]),
                    quantity=int(st.session_state.get("ord_qty", 1)),
                    shipping_fee_paid=float(st.session_state.get("ord_sp", 3000)),
                    shipping_fee_charged=float(st.session_state.get("ord_sc", 0)),
                    ad_cost=float(st.session_state.get("ord_ad", 0)),
                    return_cost=float(st.session_state.get("ord_ret", 0)),
                )

                net = preview["net_profit"]
                net_color = "#047857" if net >= 0 else "#DC2626"
                net_icon = "✅" if net >= 0 else "❌"

                st.markdown(f"""
<div style="text-align:center;padding:20px 0;border-bottom:1px solid #E2E8F0;margin-bottom:16px">
  <div style="font-size:13px;color:#94A3B8;font-weight:600">예상 순이익 (VAT 차감 후)</div>
  <div style="font-size:42px;font-weight:900;color:{net_color};line-height:1.1;margin-top:6px">
    {format_krw(net)}
  </div>
  <div style="font-size:15px;color:{net_color};font-weight:700;margin-top:4px">
    {net_icon} 순이익률 {preview['margin_rate']:.1%}
  </div>
</div>
""", unsafe_allow_html=True)

                breakdown_items = [
                    ("💵 총매출", preview["gross_revenue"], "#0F172A", "+"),
                    ("📦 공급 원가", preview["supply_cost"], "#DC2626", "-"),
                    (f"🏪 플랫폼 수수료 ({preview['platform_fee_rate']:.1%})", preview["platform_fee"], "#DC2626", "-"),
                    ("🚚 순 배송비", preview["net_shipping_cost"], "#DC2626", "-"),
                    ("📢 광고비", preview["ad_cost"], "#DC2626", "-"),
                    ("↩️ 반품비", preview["return_cost"], "#DC2626", "-"),
                    ("📊 영업이익", preview["gross_profit"], "#047857" if preview["gross_profit"] >= 0 else "#DC2626", "="),
                    ("🏛️ 납부 부가세", preview["vat_payable"], "#DC2626", "-"),
                ]
                for label, amount, color, sign in breakdown_items:
                    is_total = sign == "="
                    st.markdown(
                        f'<div style="display:flex;justify-content:space-between;'
                        f'padding:{"8px 0;border-top:2px solid #E2E8F0;margin-top:4px" if is_total else "4px 0"}">'
                        f'<span style="font-size:{"14px" if is_total else "13px"};'
                        f'color:#{"0F172A" if is_total else "475569"};'
                        f'font-weight:{"700" if is_total else "400"}">{label}</span>'
                        f'<span style="font-size:{"14px" if is_total else "13px"};'
                        f'color:{color};font-weight:{"800" if is_total else "600"}">'
                        f'{sign if sign != "+" else ""}{amount:,.0f}원</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab C · 주문 내역
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with sub_orders:
        oh1, oh2, oh3 = st.columns([1, 1, 1])
        with oh1:
            flt_plat = st.selectbox("플랫폼", ["전체", "coupang", "smartstore"],
                                     format_func=lambda x: {"전체": "전체", "coupang": "쿠팡", "smartstore": "스마트스토어"}[x],
                                     key="ord_flt_plat", label_visibility="collapsed")
        with oh2:
            flt_status = st.selectbox("상태", ["전체", "completed", "ordered", "shipped", "returned", "cancelled"],
                                       format_func=lambda x: {
                                           "전체": "전체 상태", "completed": "완료", "ordered": "주문접수",
                                           "shipped": "배송중", "returned": "반품", "cancelled": "취소"
                                       }[x],
                                       key="ord_flt_st", label_visibility="collapsed")
        with oh3:
            if st.button("🔄 새로고침", key="ord_ref", use_container_width=True):
                st.rerun()

        orders_data = list_orders(
            platform="" if flt_plat == "전체" else flt_plat,
            status="" if flt_status == "전체" else flt_status,
            year=sel_year,
            month=sel_month,
        )
        items_ord = orders_data["items"]

        if not items_ord:
            st.markdown(
                '<div class="empty-box"><div class="ei">📋</div>'
                '<h3>주문 내역 없음</h3>'
                '<p>주문 입력 탭에서 주문을 등록하세요</p></div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption(f"총 {orders_data['total']}건 (현재 {len(items_ord)}건 표시)")

            # 헤더
            hdr = st.columns([0.4, 2.2, 0.8, 1, 1.2, 1.2, 1.2, 0.8])
            for col, txt in zip(hdr, ["", "상품·플랫폼", "수량", "판매가", "총매출", "순이익", "부가세", "상태"]):
                col.markdown(
                    f'<div style="font-size:11px;font-weight:700;color:#94A3B8;'
                    f'text-transform:uppercase;letter-spacing:.04em;padding:4px 0">{txt}</div>',
                    unsafe_allow_html=True,
                )

            for o in items_ord:
                plat_lbl = {"coupang": "쿠팡", "smartstore": "스마트"}.get(o["platform"], o["platform"])
                plat_color = "#B45309" if o["platform"] == "coupang" else "#047857"
                np_color = "#047857" if o["net_profit"] >= 0 else "#DC2626"
                status_map = {"completed": ("bd-success", "완료"), "ordered": ("bd-pending", "접수"),
                              "shipped": ("bd-listed", "배송중"), "returned": ("bd-failed", "반품"),
                              "cancelled": ("bd-draft", "취소")}
                st_cls, st_lbl = status_map.get(o["status"], ("bd-draft", o["status"]))

                c0, c1, c2, c3, c4, c5, c6, c7 = st.columns([0.4, 2.2, 0.8, 1, 1.2, 1.2, 1.2, 0.8])
                with c0:
                    if st.button("🗑", key=f"del_ord_{o['id']}", help="삭제"):
                        delete_order(o["id"])
                        st.rerun()
                c1.markdown(
                    f'<div style="font-size:13px;font-weight:600;color:#0F172A">상품 #{o["product_id"]}</div>'
                    f'<div style="font-size:11px;color:{plat_color};font-weight:700">{plat_lbl}</div>'
                    f'<div style="font-size:10px;color:#94A3B8">{o["ordered_at"][:10]}</div>',
                    unsafe_allow_html=True,
                )
                c2.markdown(f'<div style="padding-top:4px;font-weight:600">{o["quantity"]}개</div>', unsafe_allow_html=True)
                c3.markdown(f'<div style="padding-top:4px;font-size:13px">{o["unit_sale_price"]:,.0f}원</div>', unsafe_allow_html=True)
                c4.markdown(f'<div style="padding-top:4px;font-weight:600">{o["gross_revenue"]:,.0f}원</div>', unsafe_allow_html=True)
                c5.markdown(f'<div style="padding-top:4px;font-weight:800;color:{np_color}">{o["net_profit"]:,.0f}원</div>', unsafe_allow_html=True)
                c6.markdown(f'<div style="padding-top:4px;color:#64748B">{o["vat_payable"]:,.0f}원</div>', unsafe_allow_html=True)
                c7.markdown(f'<span class="badge {st_cls}">{st_lbl}</span>', unsafe_allow_html=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab D · 세금 계산기
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with sub_tax:
        from app.settlement.tax_engine import calculate_tax, quarterly_breakdown, INCOME_TAX_BRACKETS

        st.markdown(f"#### 🏛️ {sel_year}년 세금 추정 (연간 누적 기준)")

        # 연간 통계
        tax_est = tax

        if tax_est["gross_revenue"] <= 0:
            st.info("연간 주문 데이터가 없습니다. 주문을 등록하면 세금이 자동 계산됩니다.", icon="ℹ️")
        else:
            # KPI 행
            tk1, tk2, tk3, tk4 = st.columns(4)
            tax_kpis = [
                (tk1, "📦", format_krw(tax_est["gross_revenue"]), f"{sel_year}년 총매출"),
                (tk2, "💡", format_krw(tax_est["taxable_income"]), "과세 소득"),
                (tk3, "🏛️", format_krw(tax_est["vat_payable"]), "납부 부가세"),
                (tk4, "📑", format_krw(tax_est["income_tax"] + tax_est["local_tax"]), "종합소득세+지방세"),
            ]
            for col, icon, val, lbl in tax_kpis:
                with col:
                    st.markdown(metric_card(icon, val, lbl), unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # 상세 분해
            tl, tr = st.columns([1.3, 1], gap="large")

            with tl:
                st.markdown("##### 세금 분해")
                tax_rows = [
                    ("💵 연간 총매출 (VAT 포함)", tax_est["gross_revenue"], "#0F172A", False),
                    ("  └ 공급가액 (VAT 제외)", tax_est["gross_revenue"] / 1.1, "#475569", False),
                    ("  └ 매출세액 (10%)", tax_est["gross_revenue"] / 11.0, "#B45309", False),
                    ("🏛️ 납부 부가세", tax_est["vat_payable"], "#DC2626", True),
                    ("", 0, "", False),
                    ("💡 과세 소득 (총매출 - 비용)", tax_est["taxable_income"], "#0F172A", False),
                    ("📑 종합소득세", tax_est["income_tax"], "#DC2626", False),
                    ("📍 지방소득세 (소득세 × 10%)", tax_est["local_tax"], "#DC2626", False),
                    ("📊 세금 합계", tax_est["total_tax"], "#DC2626", True),
                    ("📉 실효세율", None, "#0F172A", True),
                ]
                for label, amount, color, is_bold in tax_rows:
                    if not label:
                        st.markdown('<hr style="margin:6px 0">', unsafe_allow_html=True)
                        continue
                    if amount is None:
                        val_str = f"{tax_est['effective_rate']:.1%}"
                    else:
                        val_str = f"{amount:,.0f}원"
                    st.markdown(
                        f'<div style="display:flex;justify-content:space-between;padding:{"6px 0;border-top:2px solid #E2E8F0;margin-top:4px" if is_bold else "3px 0"}">'
                        f'<span style="font-size:13px;color:#{"0F172A" if is_bold else "475569"};font-weight:{"700" if is_bold else "400"}">{label}</span>'
                        f'<span style="font-size:13px;color:{color};font-weight:{"800" if is_bold else "500"}">{val_str}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            with tr:
                st.markdown("##### 종합소득세 세율 구간")
                bracket_rows = []
                for low, high, rate, ded in INCOME_TAX_BRACKETS:
                    low_str = format_krw(low) if low > 0 else "0원"
                    high_str = format_krw(high) if high < float("inf") else "초과"
                    ti = tax_est["taxable_income"]
                    is_current = low <= ti <= high
                    bracket_rows.append({
                        "소득 구간": f"{low_str}~{high_str}",
                        "세율": f"{rate:.0%}",
                        "누진공제": f"{ded:,.0f}원",
                        "적용": "◀ 현재" if is_current else "",
                    })
                st.dataframe(
                    pd.DataFrame(bracket_rows),
                    use_container_width=True,
                    hide_index=True,
                    height=310,
                )

            st.divider()

            # 분기별 부가세 납부 일정
            st.markdown("##### 📅 분기별 부가세 납부 일정")
            monthly_rev = [mo["gross_revenue"] for mo in monthly]
            quarters = quarterly_breakdown(tax_est["gross_revenue"], monthly_rev)

            if quarters:
                qcols = st.columns(len(quarters))
                for col, q in zip(qcols, quarters):
                    q_months = sum(q["months"])
                    with col:
                        st.markdown(f"""
<div style="border:1px solid #E2E8F0;border-radius:12px;padding:14px 16px;text-align:center">
  <div style="font-size:14px;font-weight:800;color:#0F172A">{q['label']}</div>
  <div style="font-size:10px;color:#94A3B8;margin-bottom:8px">{(q['quarter']-1)*3+1}~{q['quarter']*3}월</div>
  <div style="font-size:11px;color:#64748B">매출</div>
  <div style="font-size:15px;font-weight:700;color:#0F172A">{format_krw(q['gross_revenue'])}</div>
  <div style="font-size:11px;color:#64748B;margin-top:6px">부가세</div>
  <div style="font-size:16px;font-weight:800;color:#DC2626">{format_krw(q['vat_payable'])}</div>
  <div style="font-size:10px;color:#94A3B8;margin-top:6px">
    {"1월 25일" if q['quarter']==1 else "4월 25일" if q['quarter']==2 else "7월 25일" if q['quarter']==3 else "10월 25일"} 신고
  </div>
</div>
""", unsafe_allow_html=True)
            else:
                st.info("주문 데이터가 있으면 분기별 부가세 납부 일정을 보여줍니다.")

            # 절세 팁
            st.markdown("##### 💡 절세 팁")
            st.markdown("""
<div style="background:#F0FDF4;border:1px solid #86EFAC;border-radius:12px;padding:16px 20px">
<ul style="margin:0;padding-left:18px;color:#166534;font-size:13px;line-height:2">
  <li>공급사에서 <b>세금계산서</b>를 반드시 수령 → 매입세액 공제로 부가세 절감</li>
  <li>광고비·물류비·포장재는 <b>사업 비용 처리</b> → 종합소득세 과세소득 감소</li>
  <li>연 매출 8,000만원 이하 <b>간이과세자</b> 선택 시 VAT 부담 경감 가능</li>
  <li>분기별 예정신고로 <b>납부세액 분산</b> → 자금 흐름 관리 유리</li>
  <li>노란우산공제 가입 시 연 최대 <b>500만원 소득공제</b> 가능</li>
</ul>
</div>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════
# TAB 7 · 재고 · 발주 자동화 (MOQ Engine)
# ════════════════════════════════════════════════════════════════════════
with tab_inv:
    import pandas as pd

    # ── 헤더 ──────────────────────────────────────────────────────────
    st.markdown("""
<div style="
  background:linear-gradient(135deg,#1C1917 0%,#44403C 55%,#78716C 100%);
  padding:20px 24px;border-radius:14px;margin-bottom:20px;
  box-shadow:0 6px 24px rgba(120,113,108,.35);
">
  <div style="color:#fff;font-size:18px;font-weight:800">🏭 Inventory & MOQ Engine</div>
  <div style="color:rgba(255,255,255,.6);font-size:12px;margin-top:4px">
    재고 현황 실시간 추적 · MOQ 기반 자동 발주 추천 · 발주서 관리
  </div>
</div>
""", unsafe_allow_html=True)

    # ── 대시보드 데이터 로드 ────────────────────────────────────────────
    inv_dash = get_inventory_dashboard()
    inv_all = inv_dash["all_inventories"]
    inv_suggestions = inv_dash["suggestions"]

    # ── 상품은 있지만 재고 미등록 시 초기화 배너 ────────────────────────
    _all_prods_count = list_products(limit=1)["total"] if hasattr(list_products(limit=1), '__getitem__') else 0
    try:
        _all_prods_count = list_products(limit=1)["total"]
    except Exception:
        _all_prods_count = 0
    _uninited = _all_prods_count - len(inv_all)

    if _all_prods_count == 0:
        st.info("📦 등록된 상품이 없습니다. **상품수집** 탭에서 상품을 먼저 수집하세요.", icon="ℹ️")
    elif _uninited > 0:
        _bi_col1, _bi_col2 = st.columns([3, 1])
        with _bi_col1:
            st.warning(
                f"📋 {_uninited}개 상품에 재고 레코드가 없습니다. "
                f"아래 버튼으로 전체 상품을 재고 목록에 자동 등록하세요.",
                icon="⚠️",
            )
        with _bi_col2:
            if st.button("⚡ 전체 재고 자동 등록", type="primary", use_container_width=True, key="inv_bulk_init"):
                with st.spinner("재고 레코드 생성 중..."):
                    _bi_res = bulk_init_inventory()
                st.success(f"✅ {_bi_res['created']}개 상품 재고 등록 완료 (기존 {_bi_res['already_exists']}개)")
                time.sleep(0.5)
                st.rerun()

    # ── KPI 카드 ────────────────────────────────────────────────────────
    ik1, ik2, ik3, ik4, ik5 = st.columns(5)
    kpi_inv = [
        (ik1, "📦", inv_dash["total_products"], "재고 관리 상품"),
        (ik2, "🔴", inv_dash["critical"], "재고 위험"),
        (ik3, "🟡", inv_dash["warning"], "발주 필요"),
        (ik4, "🟢", inv_dash["ok"], "재고 양호"),
        (ik5, "💰", f"{inv_dash['total_value']:,.0f}원", "재고 원가"),
    ]
    for col, icon, val, lbl in kpi_inv:
        with col:
            color = ""
            if lbl == "재고 위험" and inv_dash["critical"] > 0:
                color = "color:#DC2626;"
            elif lbl == "발주 필요" and inv_dash["warning"] > 0:
                color = "color:#B45309;"
            st.markdown(
                f'<div class="m-card">'
                f'<div class="m-icon">{icon}</div>'
                f'<div class="m-value" style="{color}">{val}</div>'
                f'<div class="m-label">{lbl}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Sub-Tab ──────────────────────────────────────────────────────────
    inv_sub_stock, inv_sub_moq, inv_sub_po, inv_sub_hist = st.tabs([
        "📊 재고 현황",
        "🔄 MOQ 발주 추천",
        "📋 발주서 관리",
        "📈 재고 이동 이력",
    ])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab A · 재고 현황
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with inv_sub_stock:
        sa_l, sa_r = st.columns([1, 2], gap="large")

        with sa_l:
            st.markdown("#### ➕ 재고 등록 / 조정")
            with st.container(border=True):
                prods_inv = list_products(limit=300)["items"]
                if not prods_inv:
                    st.warning("등록된 상품이 없습니다.")
                else:
                    prod_opts_inv = {
                        f"[{p['id']}] {p['name'][:38]}": p for p in prods_inv
                    }
                    sel_inv_key = st.selectbox(
                        "상품", list(prod_opts_inv.keys()),
                        label_visibility="collapsed", key="inv_prod_sel",
                    )
                    sel_inv_prod = prod_opts_inv[sel_inv_key]

                    inv_c1, inv_c2 = st.columns(2)
                    adj_delta = inv_c1.number_input(
                        "재고 변동 (+ 입고 / - 출고)", value=0,
                        min_value=-9999, max_value=9999, step=1, key="inv_delta",
                    )
                    adj_type = inv_c2.selectbox(
                        "유형",
                        ["in_adjust", "out_adjust", "in_purchase", "out_sale"],
                        format_func=lambda x: {
                            "in_adjust": "수동 입고",
                            "out_adjust": "수동 출고",
                            "in_purchase": "발주 입고",
                            "out_sale": "판매 출고",
                        }[x],
                        key="inv_mv_type",
                    )
                    adj_memo = st.text_input("메모", key="inv_memo")

                    st.markdown("**재고 설정값**")
                    ic1, ic2 = st.columns(2)
                    ic3, ic4 = st.columns(2)
                    ic5, ic6 = st.columns(2)
                    set_safety = ic1.number_input("안전 재고", value=10, min_value=0, key="inv_safety")
                    set_rp = ic2.number_input("재발주 포인트", value=20, min_value=0, key="inv_rp")
                    set_moq = ic3.number_input("MOQ", value=1, min_value=1, key="inv_moq")
                    set_rqty = ic4.number_input("표준 발주량", value=50, min_value=1, key="inv_rqty")
                    set_lead = ic5.number_input("납기일 (일)", value=7, min_value=1, key="inv_lead")
                    set_loc = ic6.text_input("창고 위치", key="inv_loc")

                    if st.button("💾 재고 저장", type="primary", use_container_width=True):
                        res = update_inventory(
                            product_id=sel_inv_prod["id"],
                            qty_delta=int(adj_delta),
                            movement_type=adj_type,
                            memo=adj_memo,
                            safety_stock=int(set_safety),
                            reorder_point=int(set_rp),
                            moq=int(set_moq),
                            reorder_qty=int(set_rqty),
                            lead_time_days=int(set_lead),
                            unit_cost=float(sel_inv_prod["supply_price"]),
                            location=set_loc or None,
                        )
                        if res["status"] == "ok":
                            st.success(f"✅ 저장 완료 — 현재 재고: {res['qty_on_hand']}개")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error("저장 실패")

        with sa_r:
            _sr_h1, _sr_h2, _sr_h3 = st.columns([2, 1, 1])
            _sr_h1.markdown("#### 📊 전체 재고 목록")
            with _sr_h2:
                if st.button("🔄 새로고침", key="inv_ref", use_container_width=True):
                    st.rerun()
            with _sr_h3:
                if inv_all:
                    _inv_df_exp = pd.DataFrame([{
                        "상품명": i["product_name"],
                        "SKU": i["sku"],
                        "보유재고": i["qty_on_hand"],
                        "가용재고": i["available_qty"],
                        "예약": i["qty_reserved"],
                        "입고예정": i["qty_incoming"],
                        "안전재고": i["safety_stock"],
                        "재발주포인트": i["reorder_point"],
                        "MOQ": i["moq"],
                        "단가": i["unit_cost"],
                        "재고원가": i["stock_value"],
                        "위치": i["location"],
                        "상태": i["urgency"],
                    } for i in inv_all])
                    st.download_button(
                        "📥 CSV", _inv_df_exp.to_csv(index=False, encoding="utf-8-sig").encode(),
                        file_name="inventory.csv", mime="text/csv",
                        use_container_width=True, key="inv_csv_dl",
                    )

            if not inv_all:
                st.markdown(
                    '<div class="empty-box"><div class="ei">📦</div>'
                    '<h3>재고 데이터 없음</h3>'
                    '<p>위의 <b>⚡ 전체 재고 자동 등록</b> 버튼을 눌러 상품을 재고 관리에 등록하세요</p>'
                    '<p style="color:#94A3B8;font-size:12px">또는 왼쪽 폼에서 상품을 선택해 개별 등록하세요</p></div>',
                    unsafe_allow_html=True,
                )
            else:
                urgency_order = {"critical": 0, "warning": 1, "ok": 2}
                sorted_inv = sorted(inv_all, key=lambda x: urgency_order.get(x["urgency"], 3))

                for inv_item in sorted_inv:
                    urgency = inv_item["urgency"]
                    border_color = (
                        "#FCA5A5" if urgency == "critical"
                        else "#FDE68A" if urgency == "warning"
                        else "#E2E8F0"
                    )
                    bg_color = (
                        "#FEF2F2" if urgency == "critical"
                        else "#FFFBEB" if urgency == "warning"
                        else "#fff"
                    )
                    urgency_badge = (
                        '<span style="background:#FEE2E2;color:#B91C1C;'
                        'padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700">🔴 위험</span>'
                        if urgency == "critical"
                        else
                        '<span style="background:#FEF3C7;color:#B45309;'
                        'padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700">🟡 발주필요</span>'
                        if urgency == "warning"
                        else
                        '<span style="background:#DCFCE7;color:#15803D;'
                        'padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700">🟢 양호</span>'
                    )

                    with st.container(border=True):
                        ri1, ri2, ri3, ri4 = st.columns([2.5, 1.2, 1.2, 1.2])
                        with ri1:
                            st.markdown(
                                f'{urgency_badge} '
                                f'<strong style="font-size:13px">{html.escape(inv_item["product_name"][:42])}</strong><br>'
                                f'<small style="color:#94A3B8">SKU: {inv_item["sku"]} · {inv_item["location"] or "위치 미지정"}</small>',
                                unsafe_allow_html=True,
                            )
                        with ri2:
                            st.markdown(
                                f'<div style="font-size:11px;color:#94A3B8">가용 재고</div>'
                                f'<div style="font-size:22px;font-weight:800;color:#0F172A">{inv_item["available_qty"]}</div>'
                                f'<div style="font-size:11px;color:#64748B">보유 {inv_item["qty_on_hand"]} / 예약 {inv_item["qty_reserved"]}</div>',
                                unsafe_allow_html=True,
                            )
                        with ri3:
                            st.markdown(
                                f'<div style="font-size:11px;color:#94A3B8">안전재고 / 재발주</div>'
                                f'<div style="font-size:15px;font-weight:700;color:#475569">{inv_item["safety_stock"]} / {inv_item["reorder_point"]}</div>'
                                f'<div style="font-size:11px;color:#64748B">입고예정 {inv_item["qty_incoming"]}개</div>',
                                unsafe_allow_html=True,
                            )
                        with ri4:
                            st.markdown(
                                f'<div style="font-size:11px;color:#94A3B8">재고 원가</div>'
                                f'<div style="font-size:15px;font-weight:700;color:#4F46E5">{inv_item["stock_value"]:,.0f}원</div>'
                                f'<div style="font-size:11px;color:#64748B">단가 {inv_item["unit_cost"]:,.0f}원</div>',
                                unsafe_allow_html=True,
                            )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab B · MOQ 발주 추천
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with inv_sub_moq:
        if not inv_suggestions:
            st.markdown(
                '<div class="empty-box"><div class="ei">✅</div>'
                '<h3>발주 필요 상품 없음</h3>'
                '<p>모든 상품의 재고가 재발주 포인트 이상입니다</p></div>',
                unsafe_allow_html=True,
            )
        else:
            crit_count = sum(1 for s in inv_suggestions if s["urgency"] == "critical")
            warn_count = sum(1 for s in inv_suggestions if s["urgency"] == "warning")

            if crit_count:
                st.error(f"🔴 **재고 위험 {crit_count}개** — 즉시 발주가 필요합니다!", icon="🚨")
            if warn_count:
                st.warning(f"🟡 발주 권장 {warn_count}개", icon="⚠️")

            st.markdown("---")

            # 발주 선택 상태 초기화
            if "po_cart" not in st.session_state:
                st.session_state["po_cart"] = {}

            for sug in inv_suggestions:
                urgency = sug["urgency"]
                border = "#FCA5A5" if urgency == "critical" else "#FDE68A"
                bg = "#FEF2F2" if urgency == "critical" else "#FFFBEB"
                urgency_lbl = "🔴 위험" if urgency == "critical" else "🟡 발주필요"

                with st.container(border=True):
                    mc1, mc2, mc3, mc4 = st.columns([2.5, 1.5, 1.5, 1.2])

                    with mc1:
                        st.markdown(
                            f'<span style="background:{"#FEE2E2" if urgency == "critical" else "#FEF3C7"};'
                            f'color:{"#B91C1C" if urgency == "critical" else "#B45309"};'
                            f'padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700">{urgency_lbl}</span> '
                            f'<strong style="font-size:13px">{html.escape(sug["product_name"][:42])}</strong><br>'
                            f'<small style="color:#64748B">{sug["sku"]} · 공급처: {sug["supplier"]}</small><br>'
                            f'<small style="color:#94A3B8">{sug["reason"]}</small>',
                            unsafe_allow_html=True,
                        )

                    with mc2:
                        st.markdown(
                            f'<div style="font-size:11px;color:#94A3B8">가용/재발주 포인트</div>'
                            f'<div style="font-size:18px;font-weight:800;color:#0F172A">'
                            f'{sug["available_qty"]} / {sug["reorder_point"]}</div>'
                            f'<div style="font-size:11px;color:#64748B">'
                            f'일 평균 {sug["avg_daily_sales"]}개 · {sug["days_of_stock"] if sug["days_of_stock"] >= 0 else "∞"}일분</div>',
                            unsafe_allow_html=True,
                        )

                    with mc3:
                        st.markdown(
                            f'<div style="font-size:11px;color:#94A3B8">추천 발주량 (MOQ {sug["moq"]})</div>'
                            f'<div style="font-size:20px;font-weight:800;color:#4F46E5">{sug["suggested_qty"]}개</div>'
                            f'<div style="font-size:12px;color:#64748B">예상 금액 {sug["suggested_cost"]:,.0f}원</div>',
                            unsafe_allow_html=True,
                        )

                    with mc4:
                        cart_key = f"cart_qty_{sug['product_id']}"
                        checked_key = f"cart_chk_{sug['product_id']}"
                        cart_qty = st.number_input(
                            "발주 수량",
                            value=sug["suggested_qty"],
                            min_value=sug["moq"],
                            step=sug["moq"],
                            key=cart_key,
                            label_visibility="collapsed",
                        )
                        checked = st.checkbox(
                            "발주 선택",
                            value=True,
                            key=checked_key,
                        )
                        if checked:
                            st.session_state["po_cart"][sug["product_id"]] = {
                                "product_id": sug["product_id"],
                                "quantity": cart_qty,
                                "unit_cost": sug["unit_cost"],
                                "product_name": sug["product_name"],
                            }
                        else:
                            st.session_state["po_cart"].pop(sug["product_id"], None)

            # ── 발주서 생성 버튼 ─────────────────────────────────────────
            st.divider()
            cart_items = list(st.session_state.get("po_cart", {}).values())
            if cart_items:
                po_c1, po_c2, po_c3 = st.columns([2, 1.5, 1.5])
                with po_c1:
                    po_supplier = st.text_input("공급처명", key="po_supplier_name",
                                                 placeholder="예: 온채널, 도매꾹, 제조사명")
                with po_c2:
                    po_lead = st.number_input("예상 납기일 (일)", value=7, min_value=1, key="po_lead_days")
                with po_c3:
                    po_memo = st.text_input("발주 메모", key="po_memo")

                total_po_cost = sum(i["quantity"] * i["unit_cost"] for i in cart_items)
                st.markdown(
                    f'<div style="background:#EEF2FF;border:1px solid #A5B4FC;border-radius:12px;'
                    f'padding:14px 18px;margin-bottom:12px">'
                    f'<span style="font-weight:700;color:#3730A3">📋 발주 합계: {len(cart_items)}종 · '
                    f'총 {sum(i["quantity"] for i in cart_items):,}개 · '
                    f'{total_po_cost:,.0f}원</span></div>',
                    unsafe_allow_html=True,
                )

                if st.button(
                    f"📋 발주서 생성 ({len(cart_items)}개 상품, {total_po_cost:,.0f}원)",
                    type="primary",
                    use_container_width=True,
                ):
                    res_po = create_purchase_order(
                        items=cart_items,
                        supplier=po_supplier,
                        memo=po_memo,
                        expected_days=int(po_lead),
                    )
                    if res_po["status"] == "ok":
                        st.success(
                            f"✅ 발주서 생성 완료 — {res_po['po_number']} "
                            f"(총 {res_po['total_amount']:,.0f}원)"
                        )
                        st.session_state["po_cart"] = {}
                        time.sleep(0.8)
                        st.rerun()
                    else:
                        st.error(f"❌ {res_po.get('error', '')}")
            else:
                st.info("발주할 상품을 위에서 선택하세요.", icon="ℹ️")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab C · 발주서 관리
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with inv_sub_po:
        poc1, poc2, poc3 = st.columns([1, 1, 1])
        with poc1:
            po_flt_status = st.selectbox(
                "상태 필터",
                ["전체", "draft", "confirmed", "ordered", "received", "cancelled"],
                format_func=lambda x: {
                    "전체": "전체",
                    "draft": "초안",
                    "confirmed": "확정",
                    "ordered": "발주완료",
                    "received": "입고완료",
                    "cancelled": "취소",
                }.get(x, x),
                key="po_flt", label_visibility="collapsed",
            )
        with poc2:
            if st.button("🔄 새로고침", key="po_ref", use_container_width=True):
                st.rerun()
        with poc3:
            pass

        po_list = list_purchase_orders(
            status="" if po_flt_status == "전체" else po_flt_status
        )

        if not po_list:
            st.markdown(
                '<div class="empty-box"><div class="ei">📋</div>'
                '<h3>발주서 없음</h3>'
                '<p>MOQ 발주 추천 탭에서 발주서를 생성하세요</p></div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption(f"발주서 {len(po_list)}건")

            po_status_map = {
                "draft": ("bd-draft", "초안"),
                "confirmed": ("bd-pending", "확정"),
                "ordered": ("bd-listed", "발주완료"),
                "received": ("bd-success", "입고완료"),
                "cancelled": ("bd-failed", "취소"),
            }

            for po in po_list:
                st_cls, st_lbl = po_status_map.get(po["status"], ("bd-draft", po["status"]))
                is_receivable = po["status"] in ("confirmed", "ordered")
                is_cancellable = po["status"] in ("draft", "confirmed")

                with st.container(border=True):
                    ph1, ph2, ph3, ph4, ph5 = st.columns([2, 1.2, 1.2, 1, 1])

                    with ph1:
                        st.markdown(
                            f'<span class="badge {st_cls}">{st_lbl}</span> '
                            f'<strong style="font-size:14px">{po["po_number"]}</strong><br>'
                            f'<small style="color:#64748B">공급처: {po["supplier"] or "미지정"}</small>'
                            + (f'<br><small style="color:#94A3B8">{po["memo"][:40]}</small>' if po["memo"] else ""),
                            unsafe_allow_html=True,
                        )
                        # 발주 항목 미리보기
                        for it in po["items"][:3]:
                            st.caption(f"  • {it['product_name'][:30]} × {it['quantity']}개 ({it['total_cost']:,.0f}원)")
                        if len(po["items"]) > 3:
                            st.caption(f"  ... 외 {len(po['items'])-3}개")

                    with ph2:
                        st.markdown(
                            f'<div style="font-size:11px;color:#94A3B8">발주 금액</div>'
                            f'<div style="font-size:18px;font-weight:800;color:#4F46E5">{po["total_amount"]:,.0f}원</div>'
                            f'<div style="font-size:11px;color:#64748B">{len(po["items"])}개 상품</div>',
                            unsafe_allow_html=True,
                        )

                    with ph3:
                        st.markdown(
                            f'<div style="font-size:11px;color:#94A3B8">발주일 / 예상입고</div>'
                            f'<div style="font-size:13px;font-weight:600;color:#0F172A">{po["ordered_at"] or "-"}</div>'
                            f'<div style="font-size:12px;color:#64748B">{po["expected_at"] or "-"}</div>',
                            unsafe_allow_html=True,
                        )

                    with ph4:
                        if is_receivable:
                            if st.button("📥 입고", key=f"recv_{po['id']}", use_container_width=True,
                                         type="primary"):
                                res_recv = receive_purchase_order(po["id"])
                                if res_recv["status"] == "ok":
                                    st.success("✅ 입고 완료")
                                    time.sleep(0.5)
                                    st.rerun()
                                else:
                                    st.error(res_recv.get("error", ""))

                    with ph5:
                        if is_cancellable:
                            if st.button("🗑 취소", key=f"cancel_po_{po['id']}", use_container_width=True):
                                res_cancel = update_po_status(po["id"], "cancelled")
                                if res_cancel["status"] == "ok":
                                    st.rerun()
                                else:
                                    st.error(res_cancel.get("error", ""))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab D · 재고 이동 이력
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with inv_sub_hist:
        _hist_c1, _hist_c2, _hist_c3 = st.columns([2, 1, 1])
        with _hist_c1:
            st.markdown("#### 📈 전체 재고 이동 이력")
        with _hist_c2:
            _hist_limit = st.selectbox("조회 건수", [30, 50, 100, 200],
                                       key="hist_limit", label_visibility="collapsed")
        with _hist_c3:
            if st.button("🔄 새로고침", key="hist_ref", use_container_width=True):
                st.rerun()

        _mv_all = get_recent_stock_movements(limit=_hist_limit)

        if not _mv_all:
            st.markdown(
                '<div class="empty-box"><div class="ei">📋</div>'
                '<h3>재고 이동 이력 없음</h3>'
                '<p>재고 등록·조정·발주 입고가 발생하면 자동으로 기록됩니다</p></div>',
                unsafe_allow_html=True,
            )
        else:
            _mv_type_label = {
                "in_adjust": ("📥", "수동 입고", "#DCFCE7", "#15803D"),
                "out_adjust": ("📤", "수동 출고", "#FEE2E2", "#B91C1C"),
                "in_purchase": ("📦", "발주 입고", "#DBEAFE", "#1D4ED8"),
                "out_sale": ("🛒", "판매 출고", "#FEF3C7", "#B45309"),
            }
            # DataFrame for overview
            _df_mv = pd.DataFrame([{
                "시각": m["created_at"],
                "상품명": m["product_name"],
                "유형": _mv_type_label.get(m["movement_type"], ("", m["movement_type"], "", ""))[1],
                "변동": f'+{m["quantity"]}' if m["quantity"] > 0 else str(m["quantity"]),
                "변동후재고": m["qty_after"],
                "메모": m["memo"],
            } for m in _mv_all])

            # Summary stats
            _in_total = sum(m["quantity"] for m in _mv_all if m["quantity"] > 0)
            _out_total = sum(abs(m["quantity"]) for m in _mv_all if m["quantity"] < 0)
            _sc1, _sc2, _sc3 = st.columns(3)
            _sc1.metric("📥 총 입고", f"{_in_total:,}개")
            _sc2.metric("📤 총 출고", f"{_out_total:,}개")
            _sc3.metric("📋 이동 건수", f"{len(_mv_all)}건")

            # Download
            _dl_col, _ = st.columns([1, 3])
            with _dl_col:
                st.download_button(
                    "📥 CSV 다운로드",
                    _df_mv.to_csv(index=False, encoding="utf-8-sig").encode(),
                    file_name="stock_movements.csv", mime="text/csv",
                    use_container_width=True, key="mv_csv_dl",
                )

            # List view
            for mv in _mv_all:
                mv_icon, mv_lbl, mv_bg, mv_tc = _mv_type_label.get(
                    mv["movement_type"], ("", mv["movement_type"], "#F1F5F9", "#64748B")
                )
                qty_str = f'+{mv["quantity"]}' if mv["quantity"] > 0 else str(mv["quantity"])
                qty_color = "#15803D" if mv["quantity"] > 0 else "#DC2626"

                mv_c1, mv_c2, mv_c3, mv_c4 = st.columns([2.5, 1.2, 1.2, 1.5])
                with mv_c1:
                    st.markdown(
                        f'<span style="background:{mv_bg};color:{mv_tc};padding:2px 8px;'
                        f'border-radius:8px;font-size:11px;font-weight:700">{mv_icon} {mv_lbl}</span> '
                        f'<span style="font-size:13px;font-weight:600">'
                        f'{html.escape(mv["product_name"][:40])}</span><br>'
                        f'<small style="color:#94A3B8">{mv["created_at"]}</small>',
                        unsafe_allow_html=True,
                    )
                with mv_c2:
                    st.markdown(
                        f'<div style="font-size:20px;font-weight:800;color:{qty_color}">{qty_str}개</div>'
                        f'<div style="font-size:11px;color:#64748B">변동</div>',
                        unsafe_allow_html=True,
                    )
                with mv_c3:
                    st.markdown(
                        f'<div style="font-size:16px;font-weight:700;color:#0F172A">{mv["qty_after"]}개</div>'
                        f'<div style="font-size:11px;color:#64748B">변동 후 재고</div>',
                        unsafe_allow_html=True,
                    )
                with mv_c4:
                    if mv["memo"]:
                        st.caption(mv["memo"][:40])
                st.divider()


# ════════════════════════════════════════════════════════════════════════
# TAB 8 · 알림 · 리포트 (Notification Engine)
# ════════════════════════════════════════════════════════════════════════
with tab_notify:

    # ── 헤더 ──────────────────────────────────────────────────────────
    st.markdown("""
<div style="
  background:linear-gradient(135deg,#1E3A5F 0%,#1D4ED8 55%,#2563EB 100%);
  padding:20px 24px;border-radius:14px;margin-bottom:20px;
  box-shadow:0 6px 24px rgba(37,99,235,.35);
">
  <div style="color:#fff;font-size:18px;font-weight:800">📱 Notification Engine</div>
  <div style="color:rgba(255,255,255,.6);font-size:12px;margin-top:4px">
    Telegram 실시간 알림 · 재고 위험 감지 · 일일 정산 리포트
  </div>
</div>
""", unsafe_allow_html=True)

    # ── 텔레그램 연결 상태 배너 ────────────────────────────────────────
    from app.config import get_settings as _gs
    _cfg = _gs()
    _tg_ok = bool(
        getattr(_cfg, "telegram_bot_token", "") and
        getattr(_cfg, "telegram_chat_id", "")
    )

    if _tg_ok:
        _ntg_col1, _ntg_col2 = st.columns([3, 1])
        with _ntg_col1:
            st.success(
                f"✅ 텔레그램 봇 설정됨  |  Chat ID: `{_cfg.telegram_chat_id}`",
                icon="📱",
            )
        with _ntg_col2:
            if st.button("📡 연결 확인", key="ntab_quick_test", use_container_width=True):
                with st.spinner("확인 중..."):
                    _qt = test_telegram_connection()
                if _qt["ok"]:
                    st.success(f"✅ @{_qt.get('bot_name','?')} 응답")
                else:
                    st.error(f"❌ {_qt.get('error','')}")
    else:
        st.error(
            "❌ 텔레그램 미설정 — `.env`에 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` 입력 후 재시작",
            icon="📱",
        )

    # ── 알림 통계 카드 ─────────────────────────────────────────────────
    n_stats = get_notification_stats()
    by_lv = n_stats["by_level"]

    nk1, nk2, nk3, nk4, nk5, nk6 = st.columns(6)
    nkpi = [
        (nk1, "📨", n_stats["total_7d"], "7일 총 발송", ""),
        (nk2, "✅", n_stats["ok_7d"], "성공", ""),
        (nk3, "❌", n_stats["failed_7d"], "실패", "color:#DC2626;" if n_stats["failed_7d"] > 0 else ""),
        (nk4, "🚨", by_lv.get("critical", 0), "위험", "color:#DC2626;" if by_lv.get("critical", 0) > 0 else ""),
        (nk5, "⚠️", by_lv.get("warning", 0), "경고", "color:#B45309;" if by_lv.get("warning", 0) > 0 else ""),
        (nk6, "ℹ️", by_lv.get("info", 0) + by_lv.get("success", 0), "정보/성공", ""),
    ]
    for col, icon, val, lbl, clr in nkpi:
        with col:
            st.markdown(
                f'<div class="m-card">'
                f'<div class="m-icon">{icon}</div>'
                f'<div class="m-value" style="{clr}">{val}</div>'
                f'<div class="m-label">{lbl}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Sub-Tab ──────────────────────────────────────────────────────────
    ntab_log, ntab_send, ntab_setting = st.tabs([
        "📋 알림 이력",
        "📤 수동 발송",
        "⚙️ 텔레그램 설정",
    ])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab A · 알림 이력
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with ntab_log:
        import pandas as pd

        nl1, nl2, nl3, nl4 = st.columns([1.5, 1.5, 1, 1])
        with nl1:
            flt_nlv = st.selectbox(
                "레벨 필터",
                ["전체", "critical", "warning", "info", "success"],
                format_func=lambda x: {
                    "전체": "전체", "critical": "🚨 위험", "warning": "⚠️ 경고",
                    "info": "ℹ️ 정보", "success": "✅ 성공",
                }.get(x, x),
                key="ntab_lv_flt", label_visibility="collapsed",
            )
        with nl2:
            _nl_limit = st.selectbox("건수", [50, 100, 200], key="ntab_limit",
                                     label_visibility="collapsed")
        with nl3:
            if st.button("🔄 새로고침", key="ntab_ref", use_container_width=True):
                st.rerun()

        logs = get_notification_logs(
            limit=_nl_limit,
            level="" if flt_nlv == "전체" else flt_nlv,
        )

        with nl4:
            if logs:
                _nl_df = pd.DataFrame([{
                    "시각": lg["sent_at"], "레벨": lg["level"],
                    "제목": lg["title"], "내용": lg["body"][:80],
                    "상태": lg["status"], "오류": lg["error"] or "",
                } for lg in logs])
                st.download_button(
                    "📥 CSV", _nl_df.to_csv(index=False, encoding="utf-8-sig").encode(),
                    file_name="notifications.csv", mime="text/csv",
                    use_container_width=True, key="ntab_csv",
                )

        if not logs:
            st.markdown(
                '<div class="empty-box"><div class="ei">📭</div>'
                '<h3>알림 이력 없음</h3>'
                '<p><b>수동 발송</b> 탭에서 테스트 메시지를 발송하거나<br>'
                '스케줄러를 활성화하면 알림이 자동으로 기록됩니다</p></div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption(f"최근 {len(logs)}건")

            _lv_badge = {
                "critical": '<span style="background:#FEE2E2;color:#B91C1C;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700">🚨 위험</span>',
                "warning":  '<span style="background:#FEF3C7;color:#B45309;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700">⚠️ 경고</span>',
                "info":     '<span style="background:#DBEAFE;color:#1D4ED8;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700">ℹ️ 정보</span>',
                "success":  '<span style="background:#DCFCE7;color:#15803D;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700">✅ 성공</span>',
            }
            _st_badge = {
                "ok":     '<span style="background:#DCFCE7;color:#15803D;padding:2px 7px;border-radius:6px;font-size:10px">발송됨</span>',
                "failed": '<span style="background:#FEE2E2;color:#B91C1C;padding:2px 7px;border-radius:6px;font-size:10px">실패</span>',
            }

            for lg in logs:
                lv_html = _lv_badge.get(lg["level"], f'<span>{lg["level"]}</span>')
                st_html = _st_badge.get(lg["status"], lg["status"])
                with st.container():
                    lc1, lc2, lc3 = st.columns([2.5, 2.5, 0.8])
                    with lc1:
                        st.markdown(
                            f'{lv_html} '
                            f'<strong style="font-size:13px">{html.escape(lg["title"])}</strong><br>'
                            f'<small style="color:#94A3B8">{lg["event_type"]} · {lg["sent_at"]}</small>',
                            unsafe_allow_html=True,
                        )
                    with lc2:
                        if lg["body"]:
                            st.markdown(
                                f'<div style="font-size:12px;color:#475569;'
                                f'background:#F8FAFC;border-radius:8px;padding:6px 10px">'
                                f'{html.escape(lg["body"][:120])}'
                                f'{"…" if len(lg["body"]) > 120 else ""}</div>',
                                unsafe_allow_html=True,
                            )
                    with lc3:
                        st.markdown(st_html, unsafe_allow_html=True)
                        if lg["error"]:
                            st.caption(f"⚠️ {lg['error'][:50]}")
                    st.divider()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab B · 수동 발송
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with ntab_send:
        _ns1, _ns2 = st.columns(2, gap="large")

        with _ns1:
            # 즉시 발송 액션
            with st.container(border=True):
                st.markdown("##### 📊 일일 정산 리포트")
                st.caption("이번 달 매출·순이익·플랫폼별 현황·세금 추정 요약을 텔레그램으로 전송합니다.")
                if st.button("📊 리포트 발송", use_container_width=True,
                             disabled=not _tg_ok, key="ntab_daily_btn", type="primary"):
                    with st.spinner("리포트 생성 및 발송 중..."):
                        res_rpt = send_daily_report()
                    if res_rpt["status"] == "ok":
                        st.success("✅ 일일 리포트 발송 완료")
                    else:
                        st.error(f"❌ 발송 실패: {res_rpt.get('error','')}")

            st.markdown("")

            with st.container(border=True):
                st.markdown("##### 🏭 재고 위험 알림")
                st.caption("재고 위험(critical) / 발주 필요(warning) 상품을 스캔해 텔레그램으로 전송합니다.")
                if st.button("🏭 재고 알림 발송", use_container_width=True,
                             disabled=not _tg_ok, key="ntab_inv_btn"):
                    with st.spinner("재고 스캔 중..."):
                        res_inv = trigger_inventory_alerts()
                    crit_n, warn_n = res_inv["critical"], res_inv["warning"]
                    if crit_n == 0 and warn_n == 0:
                        st.info("현재 재고 위험·경고 상품이 없습니다.")
                    else:
                        st.success(
                            f"✅ 위험 {crit_n}개 / 경고 {warn_n}개 → {res_inv['sent']}건 전송"
                        )

        with _ns2:
            with st.container(border=True):
                st.markdown("##### ✍️ 직접 메시지 발송")
                st.caption("텔레그램으로 원하는 내용을 직접 전송합니다.")
                custom_title = st.text_input("제목", placeholder="알림 제목", key="ntab_custom_title")
                custom_msg = st.text_area(
                    "메시지 내용", placeholder="텔레그램으로 보낼 메시지를 입력하세요...",
                    key="ntab_custom_msg", height=120,
                )
                _cm1, _cm2 = st.columns(2)
                custom_level = _cm1.selectbox(
                    "레벨",
                    ["info", "success", "warning", "critical"],
                    format_func=lambda x: {
                        "info": "ℹ️ 정보", "success": "✅ 성공",
                        "warning": "⚠️ 경고", "critical": "🚨 위험",
                    }[x],
                    key="ntab_custom_lv",
                )
                _can_send = _tg_ok and bool(custom_msg.strip())
                with _cm2:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("✉️ 발송", use_container_width=True,
                                 disabled=not _can_send, key="ntab_custom_btn",
                                 type="primary"):
                        from app.notify.events import notify, NotifyLevel, EventType
                        ok_c = notify(
                            level=NotifyLevel(custom_level),
                            title=custom_title.strip() or "수동 알림",
                            body=custom_msg.strip(),
                            event_type=EventType.SYSTEM_TEST,
                        )
                        if ok_c:
                            st.success("✅ 발송 완료")
                        else:
                            st.error("❌ 발송 실패")
                if not _tg_ok:
                    st.warning("텔레그램 미설정 — 설정 탭에서 구성하세요.")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab C · 텔레그램 설정
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with ntab_setting:
        _ts_l, _ts_r = st.columns([1, 1], gap="large")

        with _ts_l:
            st.markdown("#### 🔌 현재 연결 상태")
            with st.container(border=True):
                _tg_status_color = "#15803D" if _tg_ok else "#B91C1C"
                _tg_status_bg = "#DCFCE7" if _tg_ok else "#FEE2E2"
                st.markdown(
                    f'<div style="background:{_tg_status_bg};border-radius:10px;padding:12px 16px;margin-bottom:12px">'
                    f'<div style="font-weight:700;color:{_tg_status_color};font-size:14px">'
                    f'{"✅ 텔레그램 봇 설정됨" if _tg_ok else "❌ 텔레그램 미설정"}</div>'
                    f'<div style="font-size:12px;color:#64748B;margin-top:6px">'
                    f'Bot Token: <code>{"✅" if _tg_ok else "❌ 미설정"}</code><br>'
                    f'Chat ID: <code>{_cfg.telegram_chat_id or "❌ 미설정"}</code>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
                if st.button("📡 연결 테스트 메시지 발송", type="primary",
                             use_container_width=True, disabled=not _tg_ok, key="ntab_test_btn"):
                    with st.spinner("테스트 중..."):
                        res_test = test_telegram_connection()
                    if res_test["ok"]:
                        st.success(f"✅ @{res_test.get('bot_name','?')} 봇으로 메시지 발송 성공")
                    else:
                        st.error(f"❌ 실패: {res_test.get('error','')}")

        with _ts_r:
            st.markdown("#### 📖 설정 방법")
            with st.container(border=True):
                st.markdown("""
**1단계: 텔레그램 봇 생성**
- Telegram 앱에서 `@BotFather` 검색
- `/newbot` 명령 실행 → 봇 이름/아이디 입력
- 발급된 **Bot Token** 복사

**2단계: Chat ID 확인**
- 생성한 봇에게 메시지 전송
- 아래 URL에서 chat id 확인:
```
https://api.telegram.org/bot<TOKEN>/getUpdates
```

**3단계: .env 파일 업데이트**
```
TELEGRAM_BOT_TOKEN=1234567890:ABCD...
TELEGRAM_CHAT_ID=123456789
```

**4단계:** 앱 재시작 후 `연결 테스트` 버튼 클릭
""")

        st.markdown("---")
        st.markdown("##### 📨 자동 알림 이벤트 목록")
        _event_data = [
            ("업로드 성공", "✅", "쿠팡/스마트스토어 상품 업로드 성공 시"),
            ("업로드 실패", "❌", "업로드 실패 시 (오류 메시지 포함)"),
            ("발주서 생성", "📋", "MOQ 발주서 생성 시"),
            ("입고 완료", "📦", "발주 물건 입고 처리 시"),
            ("재고 위험", "🔴", "가용 재고 ≤ 안전재고 (스케줄러 자동 감지)"),
            ("재고 경고", "🟡", "가용 재고 ≤ 재발주 포인트"),
            ("일일 정산 리포트", "📊", "매일 21:00 자동 발송 (스케줄러 활성 시)"),
            ("파이프라인 완료", "⚡", "자동 파이프라인 실행 완료 시"),
        ]
        for ename, eicon, edesc in _event_data:
            _ea, _eb, _ec = st.columns([0.5, 1.5, 3])
            _ea.markdown(f'<div style="font-size:18px;padding-top:4px">{eicon}</div>',
                         unsafe_allow_html=True)
            _eb.markdown(f'<div style="font-weight:600;font-size:13px;padding-top:6px">{ename}</div>',
                         unsafe_allow_html=True)
            _ec.markdown(f'<div style="font-size:12px;color:#64748B;padding-top:6px">{edesc}</div>',
                         unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════
# TAB 9 · 스케줄러 (Cron 전자동화)
# ════════════════════════════════════════════════════════════════════════
with tab_sched:
    import pandas as pd

    # ── 헤더 ──────────────────────────────────────────────────────────
    sched_status = get_scheduler_status()

    st.markdown(f"""
<div style="
  background:linear-gradient(135deg,#312E81 0%,#4338CA 55%,#6366F1 100%);
  padding:20px 24px;border-radius:14px;margin-bottom:20px;
  box-shadow:0 6px 24px rgba(99,102,241,.35);
">
  <div style="display:flex;align-items:center;gap:14px">
    <div style="font-size:18px;font-weight:800;color:#fff">⏰ Scheduler Engine</div>
    <div style="
      background:{"rgba(74,222,128,.2)" if sched_status["running"] else "rgba(248,113,113,.2)"};
      color:{"#4ADE80" if sched_status["running"] else "#F87171"};
      border:1px solid {"#4ADE80" if sched_status["running"] else "#F87171"};
      padding:3px 12px;border-radius:20px;font-size:12px;font-weight:700
    ">{"● 실행 중" if sched_status["running"] else "● 중지됨"}</div>
  </div>
  <div style="color:rgba(255,255,255,.6);font-size:12px;margin-top:4px">
    Cron 전자동화 · {sched_status["enabled_jobs"]}/{sched_status["total_jobs"]}개 작업 활성
    · 시간대: {sched_status["timezone"]}
  </div>
</div>
""", unsafe_allow_html=True)

    # ── KPI 카드 + 빠른 제어 ────────────────────────────────────────────
    sk1, sk2, sk3, sk4, sk5, sk6 = st.columns(6)
    total_runs = sum(j["run_count"] for j in sched_status["jobs"])
    ok_jobs = sum(1 for j in sched_status["jobs"] if j["last_status"] == "ok")
    fail_jobs = sum(1 for j in sched_status["jobs"] if j["last_status"] == "failed")
    for col, icon, val, lbl, clr in [
        (sk1, "⚙️", sched_status["total_jobs"], "전체 작업", ""),
        (sk2, "✅", sched_status["enabled_jobs"], "활성", "color:#15803D;" if sched_status["enabled_jobs"] > 0 else ""),
        (sk3, "⏸", sched_status["total_jobs"] - sched_status["enabled_jobs"], "비활성", ""),
        (sk4, "▶️", total_runs, "총 실행", ""),
        (sk5, "✔️", ok_jobs, "성공", ""),
        (sk6, "❌", fail_jobs, "실패", "color:#DC2626;" if fail_jobs > 0 else ""),
    ]:
        with col:
            st.markdown(
                f'<div class="m-card">'
                f'<div class="m-icon">{icon}</div>'
                f'<div class="m-value" style="{clr}">{val}</div>'
                f'<div class="m-label">{lbl}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── 권장 설정 배너 (모든 작업이 비활성일 때) ─────────────────────────
    if sched_status["enabled_jobs"] == 0:
        _rec_col1, _rec_col2 = st.columns([3, 1])
        with _rec_col1:
            st.info(
                "⏰ 모든 스케줄 작업이 비활성화되어 있습니다. "
                "**권장 설정 적용** 버튼으로 핵심 작업 3개(재고 체크·일일 리포트·가격 최적화)를 활성화하세요.",
                icon="💡",
            )
        with _rec_col2:
            if st.button("⚡ 권장 설정 적용", type="primary", use_container_width=True, key="sched_recommended"):
                _rec_jobs = ["inventory_check", "daily_report", "price_optimize"]
                _rec_ok = 0
                for _rjid in _rec_jobs:
                    _r = toggle_scheduled_job(_rjid, True)
                    if _r["status"] == "ok":
                        _rec_ok += 1
                st.success(f"✅ {_rec_ok}개 작업 활성화 완료")
                time.sleep(0.5)
                st.rerun()
    else:
        st.markdown("<br>", unsafe_allow_html=True)

    sched_tab_jobs, sched_tab_logs = st.tabs(["⚙️ 작업 관리", "📋 실행 로그"])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab A · 작업 관리
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with sched_tab_jobs:

        # 전체 제어 버튼
        _sj_h1, _sj_h2, _sj_h3 = st.columns([2, 1, 1])
        with _sj_h2:
            if st.button("▶ 전체 활성화", use_container_width=True, key="sched_all_on"):
                for _j in sched_status["jobs"]:
                    if not _j["enabled"]:
                        toggle_scheduled_job(_j["job_id"], True)
                time.sleep(0.3)
                st.rerun()
        with _sj_h3:
            if st.button("⏸ 전체 비활성화", use_container_width=True, key="sched_all_off"):
                for _j in sched_status["jobs"]:
                    if _j["enabled"]:
                        toggle_scheduled_job(_j["job_id"], False)
                time.sleep(0.3)
                st.rerun()

        # cron 프리셋
        CRON_PRESETS = {
            "매분 (테스트)":         "* * * * *",
            "매시간 정각":            "0 * * * *",
            "매일 새벽 03:00":        "0 3 * * *",
            "매일 오전 06:00":        "0 6 * * *",
            "매일 오후 21:00":        "0 21 * * *",
            "매주 월요일 09:00":      "0 9 * * 1",
            "매주 일요일 자정":       "0 0 * * 0",
        }

        _status_badge_sched = {
            "ok":      '<span style="background:#DCFCE7;color:#15803D;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700">✅ 성공</span>',
            "failed":  '<span style="background:#FEE2E2;color:#B91C1C;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700">❌ 실패</span>',
            "running": '<span style="background:#DBEAFE;color:#1D4ED8;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700">⏳ 실행중</span>',
            "":        '<span style="background:#F1F5F9;color:#64748B;padding:2px 8px;border-radius:8px;font-size:11px">미실행</span>',
        }

        for job in sched_status["jobs"]:
            jid = job["job_id"]
            enabled = job["enabled"]
            border = "#A5B4FC" if enabled else "#E2E8F0"
            bg = "#F5F3FF" if enabled else "#FAFAFA"
            st_html = _status_badge_sched.get(job["last_status"], "")

            with st.container(border=True):

                jc1, jc2, jc3, jc4 = st.columns([2.5, 1.8, 1.2, 1.2])

                with jc1:
                    active_dot = (
                        '<span style="display:inline-block;width:8px;height:8px;'
                        'border-radius:50%;background:#4ADE80;margin-right:6px;'
                        'vertical-align:middle"></span>'
                        if enabled else
                        '<span style="display:inline-block;width:8px;height:8px;'
                        'border-radius:50%;background:#94A3B8;margin-right:6px;'
                        'vertical-align:middle"></span>'
                    )
                    st.markdown(
                        f'{active_dot}'
                        f'<strong style="font-size:14px">{job["name"]}</strong><br>'
                        f'<small style="color:#64748B">{job["description"]}</small><br>'
                        f'<code style="font-size:12px;background:#F1F5F9;padding:1px 6px;'
                        f'border-radius:4px">{job["cron_expr"]}</code> '
                        + (f'<small style="color:#94A3B8">· 다음 실행: {job["next_run_at"]}</small>' if job["next_run_at"] else ""),
                        unsafe_allow_html=True,
                    )

                with jc2:
                    st.markdown(
                        f'<div style="font-size:11px;color:#94A3B8">최근 실행 / 횟수</div>'
                        f'<div style="font-size:13px;font-weight:600;color:#0F172A">'
                        f'{job["last_run_at"] or "없음"}</div>'
                        f'<div style="font-size:12px;color:#64748B">{job["run_count"]}회 실행</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(st_html, unsafe_allow_html=True)
                    if job["last_error"]:
                        st.caption(f"⚠️ {job['last_error'][:50]}")

                with jc3:
                    # cron 변경 expander
                    with st.expander("🕐 일정 변경"):
                        preset_key = f"preset_{jid}"
                        preset_sel = st.selectbox(
                            "프리셋",
                            ["직접 입력"] + list(CRON_PRESETS.keys()),
                            key=preset_key,
                            label_visibility="collapsed",
                        )
                        cron_default = CRON_PRESETS.get(preset_sel, job["cron_expr"])
                        new_cron = st.text_input(
                            "cron",
                            value=cron_default,
                            key=f"cron_inp_{jid}",
                            label_visibility="collapsed",
                        )
                        if st.button("저장", key=f"cron_save_{jid}", use_container_width=True):
                            res_cr = update_job_cron(jid, new_cron.strip())
                            if res_cr["status"] == "ok":
                                st.success("✅")
                                time.sleep(0.3)
                                st.rerun()
                            else:
                                st.error(res_cr.get("error", ""))

                with jc4:
                    # 활성/비활성 토글
                    if st.button(
                        "⏸ 비활성화" if enabled else "▶ 활성화",
                        key=f"toggle_{jid}",
                        use_container_width=True,
                        type="primary" if not enabled else "secondary",
                    ):
                        res_tg = toggle_scheduled_job(jid, not enabled)
                        if res_tg["status"] == "ok":
                            time.sleep(0.3)
                            st.rerun()
                        else:
                            st.error(res_tg.get("error", ""))

                    # 즉시 실행
                    if st.button(
                        "⚡ 즉시 실행",
                        key=f"runnow_{jid}",
                        use_container_width=True,
                    ):
                        res_rn = run_job_now(jid)
                        if res_rn["status"] == "ok":
                            st.success(f"✅ {job['name']} 실행 시작")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error(res_rn.get("error", ""))

        st.markdown("---")
        st.markdown("""
<div style="background:#F8FAFF;border:1px solid #C7D2FE;border-radius:12px;padding:14px 18px">
<b>⏱ cron 표현식 형식:</b> <code>분 시 일 월 요일</code><br>
<small style="color:#475569">
<code>0 3 * * *</code> 매일 03:00 &nbsp;·&nbsp;
<code>0 * * * *</code> 매시간 &nbsp;·&nbsp;
<code>0 9 * * 1</code> 매주 월 09:00 &nbsp;·&nbsp;
<code>*/30 * * * *</code> 30분마다 &nbsp;·&nbsp;
<code>0 0,12 * * *</code> 하루 2회(자정/정오)
</small>
</div>
""", unsafe_allow_html=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab B · 실행 로그
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with sched_tab_logs:
        sl1, sl2, sl3, sl4 = st.columns([2, 1.5, 1, 1])
        with sl1:
            flt_job = st.selectbox(
                "작업 필터",
                ["전체"] + [j["job_id"] for j in sched_status["jobs"]],
                format_func=lambda x: (
                    "전체" if x == "전체"
                    else next((j["name"] for j in sched_status["jobs"] if j["job_id"] == x), x)
                ),
                key="sched_log_flt", label_visibility="collapsed",
            )
        with sl2:
            _sl_limit = st.selectbox("건수", [50, 100, 200], key="sl_limit",
                                     label_visibility="collapsed")
        with sl3:
            if st.button("🔄 새로고침", key="sched_log_ref", use_container_width=True):
                st.rerun()

        run_logs = get_job_run_logs(
            job_id="" if flt_job == "전체" else flt_job,
            limit=_sl_limit,
        )

        with sl4:
            if run_logs:
                import pandas as pd
                _rl_df = pd.DataFrame([{
                    "작업": next((j["name"] for j in sched_status["jobs"]
                                  if j["job_id"] == rl["job_id"]), rl["job_id"]),
                    "시작": rl["started_at"],
                    "소요(s)": rl["duration_sec"],
                    "상태": rl["status"],
                    "오류": rl["error"] or "",
                } for rl in run_logs])
                st.download_button(
                    "📥 CSV", _rl_df.to_csv(index=False, encoding="utf-8-sig").encode(),
                    file_name="job_logs.csv", mime="text/csv",
                    use_container_width=True, key="rl_csv_dl",
                )

        if not run_logs:
            st.markdown(
                '<div class="empty-box"><div class="ei">📋</div>'
                '<h3>실행 로그 없음</h3>'
                '<p>작업을 <b>활성화</b>하거나 <b>⚡ 즉시 실행</b>하면 로그가 기록됩니다</p>'
                '<p style="color:#94A3B8;font-size:12px">위 작업 관리 탭 → ⚡ 즉시 실행 버튼을 눌러보세요</p>'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            # Summary
            _rl_ok = sum(1 for r in run_logs if r["status"] == "ok")
            _rl_fail = sum(1 for r in run_logs if r["status"] == "failed")
            _rl_run = sum(1 for r in run_logs if r["status"] == "running")
            _rl_m1, _rl_m2, _rl_m3, _rl_m4 = st.columns(4)
            _rl_m1.metric("총 기록", f"{len(run_logs)}건")
            _rl_m2.metric("✅ 성공", f"{_rl_ok}건")
            _rl_m3.metric("❌ 실패", f"{_rl_fail}건")
            _rl_m4.metric("⏳ 실행중", f"{_rl_run}건")

            _rlog_st = {
                "ok":      '<span style="background:#DCFCE7;color:#15803D;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700">✅ 성공</span>',
                "failed":  '<span style="background:#FEE2E2;color:#B91C1C;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700">❌ 실패</span>',
                "running": '<span style="background:#DBEAFE;color:#1D4ED8;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700">⏳ 실행중</span>',
            }

            for rl in run_logs:
                job_name = next(
                    (j["name"] for j in sched_status["jobs"] if j["job_id"] == rl["job_id"]),
                    rl["job_id"],
                )
                st_html = _rlog_st.get(rl["status"], rl["status"])
                dur = f"{rl['duration_sec']}s" if rl["duration_sec"] is not None else "실행중"

                result_str = ""
                try:
                    rdata = json.loads(rl["result"] or "{}")
                    if rdata:
                        result_str = " · ".join(
                            f"{k}: {v}" for k, v in list(rdata.items())[:4]
                        )
                except Exception:
                    result_str = rl["result"][:80] if rl["result"] else ""

                with st.container():
                    rc1, rc2, rc3 = st.columns([2, 2.5, 1])
                    with rc1:
                        st.markdown(
                            f'<strong style="font-size:13px">{job_name}</strong><br>'
                            f'<small style="color:#94A3B8">{rl["started_at"]} · {dur}</small>',
                            unsafe_allow_html=True,
                        )
                    with rc2:
                        if result_str:
                            st.markdown(
                                f'<div style="font-size:12px;color:#475569;'
                                f'background:#F8FAFC;border-radius:8px;padding:5px 10px">'
                                f'{html.escape(result_str[:120])}</div>',
                                unsafe_allow_html=True,
                            )
                        if rl["error"]:
                            st.caption(f"⚠️ {rl['error'][:80]}")
                    with rc3:
                        st.markdown(st_html, unsafe_allow_html=True)
                    st.divider()


# ════════════════════════════════════════════════════════════════════════
# TAB 11 · 설정 & 연결 상태 + 시스템 하드닝
# ════════════════════════════════════════════════════════════════════════
with tab_cfg:
    import pandas as pd

    # ── 헤더 ──────────────────────────────────────────────────────────
    st.markdown("""
<div style="
  background:linear-gradient(135deg,#0F172A 0%,#1E293B 55%,#334155 100%);
  padding:20px 24px;border-radius:14px;margin-bottom:20px;
  box-shadow:0 6px 24px rgba(15,23,42,.35);
">
  <div style="color:#fff;font-size:18px;font-weight:800">⚙️ System Configuration</div>
  <div style="color:rgba(255,255,255,.6);font-size:12px;margin-top:4px">
    API 연결 상태 · 시스템 헬스 · Circuit Breaker · 환경 설정
  </div>
</div>
""", unsafe_allow_html=True)

    from app.config import get_settings
    cfg = get_settings()

    # ── Sub-Tab ──────────────────────────────────────────────────────────
    cfg_tab1, cfg_tab2, cfg_tab3, cfg_tab4 = st.tabs([
        "🔌 연결 상태",
        "🛡️ 시스템 헬스",
        "📋 .env 설정 가이드",
        "🔑 현재 설정값",
    ])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab A · 연결 상태 (실시간 테스트)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with cfg_tab1:
        from app.suppliers.onchannel import is_logged_in as _onc_is_logged_in
        _onc_logged_in = _onc_is_logged_in()

        dom_key_ok = bool(cfg.domeggook_api_key and len(cfg.domeggook_api_key) > 10)
        cp_ok = bool(cfg.coupang_access_key and cfg.coupang_secret_key and cfg.coupang_vendor_id)
        ss_ok = bool(cfg.naver_client_id and cfg.naver_client_secret)
        ai_ok = bool(cfg.claude_api_key)
        tg_ok = bool(cfg.telegram_bot_token and cfg.telegram_chat_id)
        dl_ok = bool(cfg.naver_search_client_id and cfg.naver_search_client_secret)

        # 연결 상태 요약 KPI
        _conn_ok_count = sum([dom_key_ok, _onc_logged_in, cp_ok, ss_ok, ai_ok, tg_ok, dl_ok])
        _conn_total = 7
        _conn_color = "#15803D" if _conn_ok_count >= 5 else "#B45309" if _conn_ok_count >= 3 else "#DC2626"
        st.markdown(
            f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;'
            f'padding:12px 20px;margin-bottom:16px;display:flex;align-items:center;gap:16px">'
            f'<div style="font-size:28px;font-weight:900;color:{_conn_color}">{_conn_ok_count}/{_conn_total}</div>'
            f'<div><div style="font-weight:700;color:#0F172A">연결 서비스 현황</div>'
            f'<div style="font-size:12px;color:#64748B">{_conn_ok_count}개 서비스 연결됨</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        def _conn_row(icon, name, ok, detail, test_key=None, test_svc=None):
            dot = "🟢" if ok else "🔴"
            tc = "#15803D" if ok else "#B91C1C"
            bg = "#F0FDF4" if ok else "#FFF5F5"

            _cc1, _cc2 = st.columns([4, 1])
            with _cc1:
                st.markdown(
                    f'<div style="background:{bg};border-radius:10px;padding:10px 16px;margin-bottom:4px">'
                    f'<div style="display:flex;align-items:center;gap:8px">'
                    f'<span style="font-size:16px">{dot}</span>'
                    f'<span style="font-weight:700;color:{tc};font-size:13px">{icon} {name}</span>'
                    f'</div>'
                    f'<div style="font-size:11px;color:#64748B;margin-top:4px;margin-left:24px">{detail}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with _cc2:
                if test_key and test_svc:
                    if st.button("🔍 테스트", key=test_key, use_container_width=True):
                        with st.spinner("테스트 중..."):
                            # .env 변경 후 재시작 없이 바로 적용되도록 모든 싱글턴 초기화
                            from app.config import reload_settings
                            from app.platforms.coupang import reset_coupang_uploader
                            from app.platforms.smartstore import reset_smartstore_uploader
                            from app.suppliers.onchannel import reset_client as _reset_onc
                            reload_settings()
                            reset_coupang_uploader()
                            reset_smartstore_uploader()
                            _reset_onc()
                            _tr = test_service_connection(test_svc)
                        if _tr["ok"]:
                            st.success(f"✅ {_tr.get('detail','')} ({_tr['ms']}ms)")
                        else:
                            st.error(f"❌ {_tr.get('error','')} ({_tr['ms']}ms)")
                else:
                    st.markdown("")

        _conn_row("🏪", "도매꾹 Private API", dom_key_ok,
                  f"키 등록됨 ({cfg.domeggook_api_key[:8]}...)" if dom_key_ok else "API 키 미설정 — .env 확인")
        _conn_row("🛒", "온채널 로그인", _onc_logged_in,
                  f"로그인 성공 (공급가 조회 가능)" if _onc_logged_in
                  else f"로그인 실패 (ID: {cfg.onchannel_login_id or '미설정'})")
        _conn_row("🔍", "온채널 검색", True,
                  "항상 가능 — 로그인 시 공급가, 비로그인 시 가격 0",
                  test_key="test_db", test_svc="database")
        _conn_row("🟡", "쿠팡 Wing API", cp_ok,
                  f"Vendor: {cfg.coupang_vendor_id}" if cp_ok else "자격증명 미설정",
                  test_key="test_coupang", test_svc="coupang")
        _conn_row("🟢", "스마트스토어 API", ss_ok,
                  f"Client ID: {cfg.naver_client_id[:14]}..." if ss_ok else "미설정",
                  test_key="test_ss", test_svc="smartstore")
        _conn_row("🤖", "Claude AI", ai_ok,
                  f"Heavy: {cfg.claude_model_heavy} · Light: {cfg.claude_model}" if ai_ok else "API 키 미설정",
                  test_key="test_claude", test_svc="claude")
        _conn_row("📱", "텔레그램 봇", tg_ok,
                  f"Chat ID: {cfg.telegram_chat_id}" if tg_ok else "BOT_TOKEN / CHAT_ID 미설정",
                  test_key="test_tg", test_svc="telegram")
        _conn_row("📊", "네이버 데이터랩", dl_ok,
                  f"Client ID: {cfg.naver_search_client_id[:10]}..." if dl_ok else "미설정 — 시장분석 트렌드 불가",
                  test_key="test_naver", test_svc="naver_search")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab B · 시스템 헬스 (Health · CB · RL)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with cfg_tab2:
        _hc_col1, _hc_col2, _hc_col3 = st.columns([1, 1, 1])
        with _hc_col1:
            if st.button("🩺 헬스 체크 실행", type="primary", use_container_width=True, key="cfg_hc_run"):
                with st.spinner("8개 서비스 점검 중..."):
                    hc_result = run_health_check(save_logs=True)
                st.session_state["last_hc"] = hc_result
        with _hc_col2:
            if st.button("🔄 새로고침", use_container_width=True, key="cfg_cb_ref"):
                st.rerun()
        with _hc_col3:
            if st.button("📋 이력 보기", use_container_width=True, key="cfg_hl_ref"):
                st.session_state["show_hl"] = not st.session_state.get("show_hl", False)

        # 헬스 체크 결과
        last_hc = st.session_state.get("last_hc")
        if last_hc:
            _ov_color = {"ok": "#047857", "degraded": "#B45309", "down": "#DC2626"}.get(last_hc["overall"], "#64748B")
            _ov_icon  = {"ok": "✅", "degraded": "⚠️", "down": "❌"}.get(last_hc["overall"], "❓")
            st.markdown(
                f'<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;'
                f'padding:12px 18px;margin-bottom:12px;margin-top:10px">'
                f'<span style="font-weight:700;color:{_ov_color};font-size:15px">'
                f'{_ov_icon} 전체 상태: {last_hc["overall"].upper()}</span>'
                f'<span style="font-size:12px;color:#94A3B8;margin-left:12px">'
                f'{last_hc["checked_at"]} · {last_hc["ok"]}/{last_hc["total"]}개 정상</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            _hc_colors = {
                "ok": ("#DCFCE7","#15803D"),
                "degraded": ("#FEF3C7","#B45309"),
                "down": ("#FEE2E2","#B91C1C"),
                "unknown": ("#F1F5F9","#64748B"),
            }
            hc_cols = st.columns(4)
            for i, svc in enumerate(last_hc["services"]):
                bg, tc = _hc_colors.get(svc["status"], ("#F1F5F9","#64748B"))
                svc_icon = {"ok":"✅","degraded":"⚠️","down":"❌","unknown":"❓"}.get(svc["status"],"❓")
                with hc_cols[i % 4]:
                    st.markdown(
                        f'<div style="background:{bg};border-radius:10px;padding:10px 12px;margin-bottom:8px">'
                        f'<div style="font-size:12px;font-weight:700;color:{tc}">'
                        f'{svc_icon} {svc["service"]}</div>'
                        f'<div style="font-size:11px;color:{tc};margin-top:3px">'
                        f'{svc["latency_ms"]}ms'
                        + (f'<br><small>{svc["detail"][:40]}</small>' if svc["detail"] else "")
                        + (f'<br><small style="color:#B91C1C">{svc["error"][:45]}</small>' if svc["error"] else "")
                        + f'</div></div>',
                        unsafe_allow_html=True,
                    )
        else:
            st.info("위 🩺 버튼을 눌러 시스템 상태를 점검하세요.", icon="💡")

        st.markdown("---")
        st.markdown("**⚡ Circuit Breaker 상태**")
        cb_list = get_circuit_breaker_status()
        rl_list = get_rate_limiter_status()
        rl_map  = {r["service"]: r for r in rl_list}

        _cb_state_style = {
            "closed":    ("🟢", "#DCFCE7", "#15803D"),
            "open":      ("🔴", "#FEE2E2", "#B91C1C"),
            "half_open": ("🟡", "#FEF3C7", "#B45309"),
        }

        cb_hdr = st.columns([1.5, 1, 0.8, 1.3, 1.3, 1])
        for col, txt in zip(cb_hdr, ["서비스", "상태", "실패/임계", "마지막 실패", "Rate Limit", "리셋"]):
            col.markdown(
                f'<div style="font-size:11px;font-weight:700;color:#94A3B8;'
                f'text-transform:uppercase;padding:3px 0">{txt}</div>',
                unsafe_allow_html=True,
            )

        for cb in cb_list:
            svc = cb["service"]
            dot, bg, tc = _cb_state_style.get(cb["state"], ("⚪", "#F1F5F9", "#64748B"))
            rl  = rl_map.get(svc, {})
            rl_txt = f"{rl.get('rate',0):.1f}/s · {rl.get('tokens',0):.0f}t" if rl else "—"

            c1, c2, c3, c4, c5, c6 = st.columns([1.5, 1, 0.8, 1.3, 1.3, 1])
            c1.markdown(f'<div style="font-size:12px;font-weight:600;color:#0F172A;padding-top:4px">{svc}</div>', unsafe_allow_html=True)
            c2.markdown(f'<span style="background:{bg};color:{tc};padding:2px 7px;border-radius:8px;font-size:11px;font-weight:700">{dot} {cb["state"]}</span>', unsafe_allow_html=True)
            c3.markdown(f'<div style="font-size:13px;font-weight:700;color:{"#DC2626" if cb["failure_count"]>0 else "#0F172A"};padding-top:4px">{cb["failure_count"]}/{cb["failure_threshold"]}</div>', unsafe_allow_html=True)
            c4.markdown(f'<div style="font-size:11px;color:#64748B;padding-top:4px">{cb["last_failure"][-8:] if cb["last_failure"] else "없음"}</div>', unsafe_allow_html=True)
            c5.markdown(f'<div style="font-size:11px;color:#475569;padding-top:4px">{rl_txt}</div>', unsafe_allow_html=True)
            with c6:
                if cb["state"] != "closed":
                    if st.button("리셋", key=f"cb_reset_{svc}", use_container_width=True):
                        res_reset = reset_circuit_breaker(svc)
                        if res_reset["status"] == "ok":
                            st.success(f"✅ {svc} 리셋")
                            time.sleep(0.3)
                            st.rerun()

        # 헬스 체크 이력
        if st.session_state.get("show_hl"):
            st.markdown("---")
            hl_rows = get_health_logs(limit=40)
            if hl_rows:
                df_hl = pd.DataFrame([{
                    "시각": r["checked_at"][-8:],
                    "서비스": r["service"],
                    "상태": r["status"],
                    "응답(ms)": r["latency_ms"],
                    "상세": (r["detail"] or r["error"] or "")[:35],
                } for r in hl_rows])
                st.dataframe(df_hl, use_container_width=True, hide_index=True, height=300)
            else:
                st.info("이력 없음 — 헬스 체크를 먼저 실행하세요.")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab C · .env 설정 가이드
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with cfg_tab3:
        from app.suppliers.onchannel import _logged_in as _onc_li2

        dom_key_ok2 = bool(cfg.domeggook_api_key and len(cfg.domeggook_api_key) > 10)
        cp_ok2 = bool(cfg.coupang_access_key and cfg.coupang_secret_key and cfg.coupang_vendor_id)
        ss_ok2 = bool(cfg.naver_client_id and cfg.naver_client_secret)

        st.markdown("""
> ⚠️ `.env` 파일 수정 후 **앱을 재시작**해야 변경사항이 적용됩니다.
""")

        with st.expander("🏪 도매꾹 Private API 설정", expanded=not dom_key_ok2):
            st.markdown(f"""
**현재 상태:** {'✅ 키 등록됨' if dom_key_ok2 else '❌ 키 미설정'}

1. [도매꾹 파트너 API 신청](https://domeggook.com/main/api/overview.phtml) → API 키 발급
2. Private API 관리: https://mobile.domeggook.com/privateAPI/management
3. `.env` 파일 업데이트:
```
DOMEGGOOK_API_KEY=발급받은_키
```
> 도매꾹 없이도 **온채널** 검색으로 운영 가능합니다.
""")

        with st.expander("🛒 온채널 로그인 설정", expanded=not _onc_li2):
            st.markdown(f"""
**현재 계정:** `{cfg.onchannel_login_id or '미설정'}`

`.env` 파일에서 실제 온채널 계정으로 업데이트:
```
ONCHANNEL_LOGIN_ID=your_email@example.com
ONCHANNEL_LOGIN_PW=your_password
```
> 로그인 없이도 검색 가능 — 단, 공급가는 로그인 후에만 표시됩니다.
""")

        with st.expander("🟡 쿠팡 Wing API 설정", expanded=not cp_ok2):
            st.markdown(f"""
**현재 상태:** {'✅ 자격증명 등록됨' if cp_ok2 else '❌ 미설정'}

1. [쿠팡 Wing](https://wing.coupang.com) → API 관리 → 키 발급
2. IP 화이트리스트 등록: `openapisupport@coupang.com`
3. `.env` 파일 업데이트:
```
COUPANG_ACCESS_KEY=발급받은_키
COUPANG_SECRET_KEY=시크릿_키
COUPANG_VENDOR_ID=A00000000
COUPANG_OUTBOUND_SHIPPING_PLACE_CODE=출고지코드
COUPANG_RETURN_CENTER_CODE=반품지코드
```
""")

        with st.expander("🟢 스마트스토어 API 설정", expanded=not ss_ok2):
            st.markdown(f"""
**현재 상태:** {'✅ 자격증명 등록됨' if ss_ok2 else '❌ 미설정'}

1. [네이버 커머스 API](https://api.commerce.naver.com) → 앱 생성 → 키 발급
2. IMAGE API 권한 추가 신청 (이미지 업로드에 필요)
3. `.env` 파일 업데이트:
```
NAVER_CLIENT_ID=발급받은_클라이언트ID
NAVER_CLIENT_SECRET=$2a$04$발급받은_시크릿
```
""")

        with st.expander("📱 텔레그램 알림 봇 설정", expanded=not bool(cfg.telegram_bot_token)):
            st.markdown("""
1. Telegram → `@BotFather` → `/newbot` → 봇 토큰 발급
2. 생성한 봇에게 메시지 전송
3. `https://api.telegram.org/bot<TOKEN>/getUpdates` 에서 Chat ID 확인
4. `.env` 파일 업데이트:
```
TELEGRAM_BOT_TOKEN=1234567890:ABCD...
TELEGRAM_CHAT_ID=123456789
```
""")

        with st.expander("🤖 Claude AI API 설정"):
            st.markdown(f"""
**현재 상태:** {'✅ API 키 등록됨' if bool(cfg.claude_api_key) else '❌ 미설정'}
**현재 모델:** Heavy `{cfg.claude_model_heavy}` · Light `{cfg.claude_model}`

1. [Anthropic Console](https://console.anthropic.com/) → API Keys → 키 생성
2. `.env` 파일 업데이트:
```
CLAUDE_API_KEY=sk-ant-api03-...
CLAUDE_MODEL_HEAVY=claude-sonnet-4-6
CLAUDE_MODEL_LIGHT=claude-haiku-4-5-20251001
```
""")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Sub-Tab D · 현재 설정값
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with cfg_tab4:
        import shutil

        st.info("🔒 민감한 값은 일부만 표시됩니다. .env 파일을 직접 편집하세요.", icon="🔒")

        _cfg_data = [
            ("🛒 온채널", "ONCHANNEL_LOGIN_ID", cfg.onchannel_login_id or "❌", bool(cfg.onchannel_login_id)),
            ("🛒 온채널", "ONCHANNEL_LOGIN_PW", "✅ 설정됨" if cfg.onchannel_login_pw else "❌", bool(cfg.onchannel_login_pw)),
            ("🏪 도매꾹", "DOMEGGOOK_API_KEY", (cfg.domeggook_api_key[:12]+"...") if cfg.domeggook_api_key else "❌", bool(cfg.domeggook_api_key)),
            ("🟡 쿠팡", "COUPANG_VENDOR_ID", cfg.coupang_vendor_id or "❌", bool(cfg.coupang_vendor_id)),
            ("🟡 쿠팡", "COUPANG_ACCESS_KEY", "✅ 설정됨" if cfg.coupang_access_key else "❌", bool(cfg.coupang_access_key)),
            ("🟢 스마트스토어", "NAVER_CLIENT_ID", (cfg.naver_client_id[:14]+"...") if cfg.naver_client_id else "❌", bool(cfg.naver_client_id)),
            ("🟢 스마트스토어", "NAVER_CLIENT_SECRET", "✅ 설정됨" if cfg.naver_client_secret else "❌", bool(cfg.naver_client_secret)),
            ("📊 네이버 검색", "NAVER_SEARCH_CLIENT_ID", (cfg.naver_search_client_id[:12]+"...") if cfg.naver_search_client_id else "❌", bool(cfg.naver_search_client_id)),
            ("🤖 Claude AI", "CLAUDE_API_KEY", "✅ 설정됨" if cfg.claude_api_key else "❌", bool(cfg.claude_api_key)),
            ("🤖 Claude AI", "CLAUDE_MODEL_HEAVY", cfg.claude_model_heavy, True),
            ("🤖 Claude AI", "CLAUDE_MODEL_LIGHT", cfg.claude_model, True),
            ("📱 텔레그램", "TELEGRAM_BOT_TOKEN", "✅ 설정됨" if cfg.telegram_bot_token else "❌", bool(cfg.telegram_bot_token)),
            ("📱 텔레그램", "TELEGRAM_CHAT_ID", cfg.telegram_chat_id or "❌", bool(cfg.telegram_chat_id)),
            ("⏰ 스케줄러", "SCHEDULER_ENABLED", str(cfg.scheduler_enabled), cfg.scheduler_enabled),
            ("⏰ 스케줄러", "SCHEDULER_TIMEZONE", cfg.scheduler_timezone, True),
            ("💾 데이터베이스", "DB_PATH", cfg.db_path, True),
        ]

        df_cfg = pd.DataFrame([{
            "서비스": s, "키": k,
            "값": v,
            "상태": "✅" if ok else "❌",
        } for s, k, v, ok in _cfg_data])
        st.dataframe(df_cfg, use_container_width=True, hide_index=True, height=500)

        st.divider()

        # 시스템 정보
        st.markdown("##### 💻 시스템 정보")
        import sys, platform
        _disk = shutil.disk_usage(".")
        _disk_pct = _disk.used / _disk.total * 100
        _sys_data = {
            "Python 버전": sys.version.split()[0],
            "운영체제": platform.system() + " " + platform.release(),
            "DB 파일": cfg.db_path,
            "디스크 사용": f"{_disk_pct:.1f}% (여유 {_disk.free/(1024**3):.1f}GB)",
        }
        for k, v in _sys_data.items():
            _s1, _s2 = st.columns([1, 2])
            _s1.markdown(f"`{k}`")
            _s2.markdown(v)
