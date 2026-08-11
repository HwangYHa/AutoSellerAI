"""AutoSellerAI — Social Commerce / Threads control center."""
from __future__ import annotations

import os
from datetime import datetime

import streamlit as st
from sqlalchemy import desc, func, select

from app.db import Product, get_db, init_db
from app.social.threads import models as _threads_models  # register metadata
from app.social.threads.ai_agent import classify_and_draft
from app.social.threads.client import ThreadsClient, ThreadsConfig
from app.social.threads.models import (
    ThreadsAutomationRule,
    ThreadsComment,
    ThreadsPost,
    ThreadsReply,
)


st.set_page_config(
    page_title="Social Commerce · Threads | AutoSeller AI",
    page_icon="🧵",
    layout="wide",
    initial_sidebar_state="expanded",
)
init_db()


# ── visual system ─────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .block-container {padding-top: 1.4rem; max-width: 1380px;}
    .threads-hero {
        background: linear-gradient(135deg,#111827 0%,#312E81 58%,#6D28D9 100%);
        color:white;padding:24px 28px;border-radius:18px;margin-bottom:18px;
        box-shadow:0 12px 34px rgba(49,46,129,.20);
    }
    .threads-hero h2{margin:0;font-size:24px;font-weight:800;}
    .threads-hero p{margin:6px 0 0;color:rgba(255,255,255,.68);font-size:13px;}
    .signal-card{border:1px solid #E2E8F0;border-radius:14px;padding:14px;background:#fff;}
    .signal-title{font-size:11px;color:#94A3B8;font-weight:700;text-transform:uppercase;letter-spacing:.04em;}
    .signal-value{font-size:25px;color:#0F172A;font-weight:800;margin-top:4px;}
    .lead-hot{background:#FEF2F2;border:1px solid #FECACA;border-radius:12px;padding:12px 14px;margin-bottom:8px;}
    .lead-warm{background:#FFF7ED;border:1px solid #FED7AA;border-radius:12px;padding:12px 14px;margin-bottom:8px;}
    .lead-cool{background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;padding:12px 14px;margin-bottom:8px;}
    .status-ok{color:#047857;font-weight:700}.status-off{color:#B45309;font-weight:700}.status-bad{color:#B91C1C;font-weight:700}
    </style>
    """,
    unsafe_allow_html=True,
)

st.sidebar.markdown("## 🛒 Social Commerce")
st.sidebar.markdown("**🧵 Threads**")
st.sidebar.caption("콘텐츠 → 댓글 → AI 영업 → 구매 유입")

st.markdown(
    """
    <div class="threads-hero">
      <h2>🧵 Threads AI Sales</h2>
      <p>Threads 게시물·댓글·구매의도·자동응답을 AutoSellerAI 상품 데이터와 연결해 한 곳에서 관리합니다.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ── helpers ───────────────────────────────────────────────────────────
def _scalar_count(db, model, *where) -> int:
    stmt = select(func.count()).select_from(model)
    for condition in where:
        stmt = stmt.where(condition)
    return int(db.scalar(stmt) or 0)


def _summary() -> dict[str, int | float]:
    with get_db() as db:
        posts = _scalar_count(db, ThreadsPost)
        comments = _scalar_count(db, ThreadsComment)
        ai_replies = _scalar_count(db, ThreadsReply)
        sent = _scalar_count(db, ThreadsReply, ThreadsReply.status == "sent")
        pending = _scalar_count(db, ThreadsReply, ThreadsReply.status.in_(["pending", "human_review"]))
        hot = _scalar_count(db, ThreadsComment, ThreadsComment.purchase_intent_score >= 0.70)
        human = _scalar_count(db, ThreadsComment, ThreadsComment.requires_human.is_(True))
        rules = _scalar_count(db, ThreadsAutomationRule, ThreadsAutomationRule.enabled.is_(True))
        avg_score = float(db.scalar(select(func.avg(ThreadsComment.purchase_intent_score))) or 0.0)
        return {
            "posts": posts,
            "comments": comments,
            "replies": ai_replies,
            "sent": sent,
            "pending": pending,
            "hot": hot,
            "human": human,
            "rules": rules,
            "avg_score": avg_score,
        }


def _products() -> list[Product]:
    with get_db() as db:
        return list(db.scalars(select(Product).order_by(desc(Product.updated_at)).limit(1000)).all())


def _product_label(product: Product) -> str:
    return f"#{product.id} · {product.name[:55]} · {product.sell_price:,.0f}원"


def _lead_label(score: float) -> tuple[str, str]:
    if score >= 0.85:
        return "🔥 HOT", "lead-hot"
    if score >= 0.70:
        return "🟠 WARM", "lead-warm"
    return "⚪ NORMAL", "lead-cool"


def _send_reply(reply_id: int) -> tuple[bool, str]:
    with get_db() as db:
        reply = db.get(ThreadsReply, reply_id)
        if not reply:
            return False, "답글을 찾을 수 없습니다."
        comment = db.get(ThreadsComment, reply.comment_id)
        if not comment:
            return False, "원본 댓글을 찾을 수 없습니다."
        text = reply.reply_text.strip()
        if not text:
            return False, "답글 내용이 비어 있습니다."
        try:
            remote_id = ThreadsClient().publish_text(text, reply_to_id=comment.threads_comment_id)
            reply.threads_reply_id = remote_id
            reply.status = "sent"
            reply.sent_at = datetime.utcnow()
            reply.error = ""
            db.commit()
            return True, remote_id
        except Exception as exc:
            reply.status = "failed"
            reply.error = str(exc)[:1000]
            db.commit()
            return False, str(exc)


def _delete_rule(rule_id: int) -> None:
    with get_db() as db:
        row = db.get(ThreadsAutomationRule, rule_id)
        if row:
            db.delete(row)
            db.commit()


def _toggle_rule(rule_id: int) -> None:
    with get_db() as db:
        row = db.get(ThreadsAutomationRule, rule_id)
        if row:
            row.enabled = not row.enabled
            db.commit()


summary = _summary()
products = _products()
product_map = {p.id: p for p in products}

# top operation status
cfg = ThreadsConfig.from_env()
configured = bool(cfg.user_id and cfg.access_token)
auto_reply = os.getenv("THREADS_AUTO_REPLY", "false").lower() == "true"
redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    st.markdown(
        f"**API 연결** · {'<span class=status-ok>설정됨</span>' if configured else '<span class=status-bad>미설정</span>'}",
        unsafe_allow_html=True,
    )
with c2:
    st.markdown(
        f"**Auto Reply** · {'<span class=status-ok>ON</span>' if auto_reply else '<span class=status-off>검수 모드</span>'}",
        unsafe_allow_html=True,
    )
with c3:
    st.caption(f"Queue: {redis_url} · 자동답글은 환경변수 THREADS_AUTO_REPLY=true일 때만 발행됩니다.")

(
    tab_dash,
    tab_posts,
    tab_comments,
    tab_leads,
    tab_rules,
    tab_inbox,
    tab_settings,
) = st.tabs([
    "📊 Dashboard",
    "📝 게시물",
    "💬 댓글",
    "🔥 HOT Leads",
    "⚙️ 자동화 Rule",
    "🤖 AI Sales Inbox",
    "🔐 Threads 설정",
])


# ═══════════════════════════════════════════════════════════════════════
# Dashboard
# ═══════════════════════════════════════════════════════════════════════
with tab_dash:
    st.subheader("Threads 영업 현황")
    cols = st.columns(6)
    cards = [
        ("📝", summary["posts"], "게시물"),
        ("💬", summary["comments"], "댓글"),
        ("🤖", summary["replies"], "AI 초안"),
        ("✅", summary["sent"], "발행 답글"),
        ("🔥", summary["hot"], "HOT Leads"),
        ("👤", summary["human"], "사람 확인"),
    ]
    for col, (icon, value, label) in zip(cols, cards):
        with col:
            st.markdown(
                f'<div class="signal-card"><div class="signal-title">{icon} {label}</div>'
                f'<div class="signal-value">{value}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("### 전환 신호")
    a, b, c = st.columns(3)
    a.metric("평균 구매의도", f"{summary['avg_score'] * 100:.1f}%")
    b.metric("활성 자동화 Rule", f"{summary['rules']}개")
    c.metric("검수/발행 대기", f"{summary['pending']}건")

    left, right = st.columns([1.35, 1], gap="large")
    with left:
        st.markdown("#### 최근 댓글")
        with get_db() as db:
            recent = list(db.scalars(select(ThreadsComment).order_by(desc(ThreadsComment.received_at)).limit(10)).all())
        if not recent:
            st.info("아직 수집된 Threads 댓글이 없습니다.")
        else:
            st.dataframe(
                [
                    {
                        "사용자": r.author_username or r.author_id or "-",
                        "댓글": r.comment_text,
                        "Intent": r.intent,
                        "구매의도": f"{r.purchase_intent_score * 100:.0f}%",
                        "사람확인": "필요" if r.requires_human else "-",
                        "수신": r.received_at.strftime("%m-%d %H:%M"),
                    }
                    for r in recent
                ],
                use_container_width=True,
                hide_index=True,
            )

    with right:
        st.markdown("#### 운영 체크")
        checks = [
            (configured, "Threads User ID / Access Token"),
            (bool(cfg.app_secret), "Webhook App Secret"),
            (bool(cfg.verify_token), "Webhook Verify Token"),
            (summary["rules"] > 0, "자동화 Rule 1개 이상"),
            (not auto_reply, "초기 검수 모드 권장"),
        ]
        for ok, label in checks:
            st.write(f"{'✅' if ok else '⚠️'} {label}")
        st.caption("초기에는 자동발행보다 AI 초안 + 사람 승인 방식으로 데이터를 쌓는 것을 권장합니다.")


# ═══════════════════════════════════════════════════════════════════════
# Posts
# ═══════════════════════════════════════════════════════════════════════
with tab_posts:
    st.subheader("Threads 게시물")
    compose, history = st.columns([0.95, 1.35], gap="large")

    with compose:
        st.markdown("#### 새 게시물")
        with st.form("threads_publish_form", clear_on_submit=False):
            selected_product = st.selectbox(
                "연결 상품",
                options=[None] + [p.id for p in products],
                format_func=lambda pid: "상품 연결 없음" if pid is None else _product_label(product_map[pid]),
            )
            text = st.text_area(
                "본문",
                height=180,
                max_chars=500,
                placeholder="정보형 콘텐츠를 작성하세요. 예: 차에서 과자 부스러기 청소할 때 가장 귀찮은 곳이 시트 사이더라고요...",
            )
            cc1, cc2 = st.columns(2)
            campaign_key = cc1.text_input("Campaign Key", placeholder="car-cleaning-202608")
            cta_keyword = cc2.text_input("CTA 댓글 키워드", placeholder="청소기")
            publish = st.form_submit_button("🧵 Threads에 발행", type="primary", use_container_width=True)

        if publish:
            if not text.strip():
                st.error("게시물 본문을 입력하세요.")
            elif not configured:
                st.error("Threads 설정에서 User ID와 Access Token을 먼저 구성하세요.")
            else:
                try:
                    with st.spinner("Threads 게시 중..."):
                        remote_id = ThreadsClient().publish_text(text.strip())
                        with get_db() as db:
                            row = ThreadsPost(
                                threads_post_id=remote_id,
                                product_id=selected_product,
                                campaign_key=campaign_key.strip(),
                                content=text.strip(),
                                cta_keyword=cta_keyword.strip(),
                                status="published",
                            )
                            db.add(row)
                            db.commit()
                    st.success(f"발행 완료 · Threads ID {remote_id}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"발행 실패: {exc}")

    with history:
        st.markdown("#### 게시 이력")
        with get_db() as db:
            posts = list(db.scalars(select(ThreadsPost).order_by(desc(ThreadsPost.published_at)).limit(100)).all())
        if not posts:
            st.info("게시 이력이 없습니다.")
        else:
            for post in posts:
                p = product_map.get(post.product_id) if post.product_id else None
                with st.container(border=True):
                    h1, h2 = st.columns([4, 1])
                    h1.markdown(f"**{post.content[:180]}{'…' if len(post.content) > 180 else ''}**")
                    h2.caption(post.published_at.strftime("%Y-%m-%d %H:%M"))
                    st.caption(
                        f"상품: {p.name if p else '미연결'} · CTA: {post.cta_keyword or '-'} · Campaign: {post.campaign_key or '-'} · ID: {post.threads_post_id}"
                    )


# ═══════════════════════════════════════════════════════════════════════
# Comments
# ═══════════════════════════════════════════════════════════════════════
with tab_comments:
    st.subheader("댓글 관리")
    f1, f2, f3 = st.columns(3)
    intent_filter = f1.selectbox("Intent", ["전체", "PURCHASE_INTENT", "SHIPPING", "STOCK", "PRICE", "COMPATIBILITY", "PRODUCT_INFO", "COMPLAINT", "RETURN", "UNKNOWN"])
    human_only = f2.checkbox("사람 확인 필요만")
    min_score = f3.slider("최소 구매의도", 0, 100, 0, 5) / 100

    with get_db() as db:
        stmt = select(ThreadsComment).where(ThreadsComment.purchase_intent_score >= min_score)
        if intent_filter != "전체":
            stmt = stmt.where(ThreadsComment.intent == intent_filter)
        if human_only:
            stmt = stmt.where(ThreadsComment.requires_human.is_(True))
        rows = list(db.scalars(stmt.order_by(desc(ThreadsComment.received_at)).limit(300)).all())

    if not rows:
        st.info("조건에 맞는 댓글이 없습니다.")
    else:
        st.dataframe(
            [
                {
                    "ID": r.id,
                    "사용자": r.author_username or r.author_id or "-",
                    "댓글": r.comment_text,
                    "Intent": r.intent,
                    "구매의도": f"{r.purchase_intent_score * 100:.0f}%",
                    "감정": r.sentiment,
                    "사람확인": "⚠️" if r.requires_human else "",
                    "처리": "✅" if r.processed else "대기",
                    "수신": r.received_at.strftime("%Y-%m-%d %H:%M"),
                }
                for r in rows
            ],
            use_container_width=True,
            hide_index=True,
        )


# ═══════════════════════════════════════════════════════════════════════
# HOT Leads
# ═══════════════════════════════════════════════════════════════════════
with tab_leads:
    st.subheader("HOT Leads")
    threshold = st.slider("Lead 기준", 50, 100, 70, 5) / 100
    with get_db() as db:
        leads = list(
            db.scalars(
                select(ThreadsComment)
                .where(ThreadsComment.purchase_intent_score >= threshold)
                .order_by(desc(ThreadsComment.purchase_intent_score), desc(ThreadsComment.received_at))
                .limit(200)
            ).all()
        )

    if not leads:
        st.info("현재 기준 이상의 Lead가 없습니다.")
    else:
        for lead in leads:
            label, css = _lead_label(lead.purchase_intent_score)
            st.markdown(
                f'<div class="{css}"><b>{label} · {lead.purchase_intent_score*100:.0f}%</b> '
                f'<span style="color:#64748B">@{lead.author_username or lead.author_id or "unknown"}</span><br>'
                f'<span style="font-size:14px;color:#0F172A">{lead.comment_text}</span><br>'
                f'<span style="font-size:11px;color:#64748B">{lead.intent} · {lead.received_at.strftime("%Y-%m-%d %H:%M")}</span></div>',
                unsafe_allow_html=True,
            )


# ═══════════════════════════════════════════════════════════════════════
# Rules
# ═══════════════════════════════════════════════════════════════════════
with tab_rules:
    st.subheader("자동화 Rule")
    left, right = st.columns([0.9, 1.3], gap="large")
    with left:
        st.markdown("#### Rule 추가")
        with st.form("thread_rule_form", clear_on_submit=True):
            keyword = st.text_input("감지 키워드", placeholder="청소기")
            reply_template = st.text_area("자동 답글", height=120, max_chars=450)
            rule_product_id = st.selectbox(
                "상품 범위",
                options=[None] + [p.id for p in products],
                format_func=lambda pid: "모든 상품" if pid is None else _product_label(product_map[pid]),
                key="rule_product",
            )
            priority = st.number_input("우선순위 (낮을수록 먼저)", min_value=1, max_value=9999, value=100)
            submitted = st.form_submit_button("Rule 저장", type="primary", use_container_width=True)
        if submitted:
            if not keyword.strip() or not reply_template.strip():
                st.error("키워드와 답글을 입력하세요.")
            else:
                with get_db() as db:
                    exists = db.scalar(select(ThreadsAutomationRule).where(ThreadsAutomationRule.keyword == keyword.strip()))
                    if exists:
                        st.error("같은 키워드 Rule이 이미 있습니다.")
                    else:
                        db.add(
                            ThreadsAutomationRule(
                                keyword=keyword.strip(),
                                reply_template=reply_template.strip(),
                                product_id=rule_product_id,
                                priority=int(priority),
                                enabled=True,
                            )
                        )
                        db.commit()
                        st.success("Rule을 저장했습니다.")
                        st.rerun()

    with right:
        st.markdown("#### 현재 Rule")
        with get_db() as db:
            rules = list(db.scalars(select(ThreadsAutomationRule).order_by(ThreadsAutomationRule.priority.asc())).all())
        if not rules:
            st.info("등록된 Rule이 없습니다.")
        for rule in rules:
            p = product_map.get(rule.product_id) if rule.product_id else None
            with st.container(border=True):
                r1, r2, r3 = st.columns([4, 1, 1])
                r1.markdown(f"**{'🟢' if rule.enabled else '⚪'} `{rule.keyword}`** · 우선순위 {rule.priority}")
                r1.caption(f"{rule.reply_template}\n\n범위: {p.name if p else '모든 상품'}")
                if r2.button("ON/OFF", key=f"toggle_rule_{rule.id}", use_container_width=True):
                    _toggle_rule(rule.id)
                    st.rerun()
                if r3.button("삭제", key=f"delete_rule_{rule.id}", use_container_width=True):
                    _delete_rule(rule.id)
                    st.rerun()


# ═══════════════════════════════════════════════════════════════════════
# AI Sales Inbox
# ═══════════════════════════════════════════════════════════════════════
with tab_inbox:
    st.subheader("AI Sales Inbox")
    st.caption("AI가 만든 초안을 검토하고, 구매 가능성이 높은 문의부터 처리합니다.")
    show_all = st.checkbox("처리 완료까지 모두 보기", value=False)

    with get_db() as db:
        stmt = (
            select(ThreadsReply, ThreadsComment)
            .join(ThreadsComment, ThreadsReply.comment_id == ThreadsComment.id)
            .order_by(desc(ThreadsComment.purchase_intent_score), desc(ThreadsReply.created_at))
        )
        if not show_all:
            stmt = stmt.where(ThreadsReply.status.in_(["pending", "human_review", "failed"]))
        inbox = list(db.execute(stmt.limit(200)).all())

    if not inbox:
        st.info("처리할 AI Sales Inbox 항목이 없습니다.")
    else:
        for reply, comment in inbox:
            label, _ = _lead_label(comment.purchase_intent_score)
            with st.expander(
                f"{label} {comment.purchase_intent_score*100:.0f}% · @{comment.author_username or comment.author_id or 'unknown'} · {comment.intent}",
                expanded=comment.purchase_intent_score >= 0.85 or comment.requires_human,
            ):
                st.markdown("**고객 댓글**")
                st.write(comment.comment_text)
                if comment.requires_human:
                    st.warning("반품/불만 등 민감 문의로 분류되어 사람 확인이 필요합니다.")
                st.markdown("**AI / Rule 답글 초안**")
                edited = st.text_area(
                    "답글",
                    value=reply.reply_text,
                    max_chars=450,
                    key=f"reply_text_{reply.id}",
                    label_visibility="collapsed",
                )
                x1, x2, x3 = st.columns([1, 1, 2])
                if x1.button("💾 초안 저장", key=f"save_reply_{reply.id}", use_container_width=True):
                    with get_db() as db:
                        row = db.get(ThreadsReply, reply.id)
                        if row:
                            row.reply_text = edited.strip()
                            row.source = "human" if edited.strip() != reply.reply_text else row.source
                            db.commit()
                    st.success("저장했습니다.")
                    st.rerun()
                if x2.button("🚀 승인·발행", key=f"send_reply_{reply.id}", type="primary", use_container_width=True):
                    if not configured:
                        st.error("Threads API 설정이 필요합니다.")
                    else:
                        with get_db() as db:
                            row = db.get(ThreadsReply, reply.id)
                            if row:
                                row.reply_text = edited.strip()
                                row.source = "human"
                                db.commit()
                        ok, msg = _send_reply(reply.id)
                        if ok:
                            st.success(f"발행 완료 · {msg}")
                            st.rerun()
                        else:
                            st.error(f"발행 실패: {msg}")
                x3.caption(f"상태: {reply.status} · 생성원: {reply.source} · {reply.created_at.strftime('%Y-%m-%d %H:%M')}")


# ═══════════════════════════════════════════════════════════════════════
# Settings
# ═══════════════════════════════════════════════════════════════════════
with tab_settings:
    st.subheader("Threads 설정")
    st.info("보안상 Access Token/App Secret은 화면이나 DB에 저장하지 않고 `.env` 환경변수로 관리합니다.")

    s1, s2 = st.columns(2, gap="large")
    with s1:
        st.markdown("#### Meta / Threads")
        st.text_input("THREADS_USER_ID", value=cfg.user_id, disabled=True)
        st.text_input("THREADS_ACCESS_TOKEN", value="설정됨" if cfg.access_token else "미설정", disabled=True, type="password")
        st.text_input("THREADS_APP_SECRET", value="설정됨" if cfg.app_secret else "미설정", disabled=True, type="password")
        st.text_input("THREADS_VERIFY_TOKEN", value="설정됨" if cfg.verify_token else "미설정", disabled=True, type="password")
        st.text_input("Graph API Base", value=cfg.graph_base_url, disabled=True)

    with s2:
        st.markdown("#### 자동화 / Queue")
        st.text_input("REDIS_URL", value=redis_url, disabled=True)
        st.text_input("THREADS_AUTO_REPLY", value=str(auto_reply).lower(), disabled=True)
        st.markdown("**권장 운영 단계**")
        st.write("1. 댓글 수집 + Intent 분석")
        st.write("2. AI 답글 초안 + 사람 승인")
        st.write("3. 검증된 키워드 Rule만 자동답글")
        st.write("4. 일반 상품문의까지 제한적 자동화")

    st.markdown("#### 필요한 Threads API 권한")
    st.code("threads_basic\nthreads_content_publish\nthreads_manage_replies\nthreads_read_replies", language="text")
    st.caption("Webhook Callback: /api/v1/threads/webhook · Social API: http://localhost:8000/docs")
