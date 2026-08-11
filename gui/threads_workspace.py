from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import streamlit as st
from sqlalchemy import desc, func, select

from app.db import Product, get_db, init_db
from app.social.threads import auth_models as _auth_models  # noqa: F401
from app.social.threads import growth_models as _growth_models  # noqa: F401
from app.social.threads import models as _models  # noqa: F401
from app.social.threads.auth import credential_status, refresh_stored_credential
from app.social.threads.client import ThreadsClient
from app.social.threads.content_engine import generate_threads_content
from app.social.threads.growth_models import OrderAttribution, ScheduledSocialPost, SocialContentDraft, TrackingClick, TrackingLink
from app.social.threads.models import ThreadsAutomationRule, ThreadsComment, ThreadsPost, ThreadsReply
from app.social.threads.tracking import attribution_summary, create_tracking_link
from gui.ui_ko import ai_source_label, angle_label, intent_label, media_label, platform_label, status_label

KST = ZoneInfo("Asia/Seoul")


def _count(db, model, *where) -> int:
    stmt = select(func.count()).select_from(model)
    for c in where:
        stmt = stmt.where(c)
    return int(db.scalar(stmt) or 0)


def _products() -> list[Product]:
    with get_db() as db:
        return list(db.scalars(select(Product).order_by(desc(Product.updated_at)).limit(1500)).all())


def _product_label(p: Product) -> str:
    return f"#{p.id} · {p.name[:52]} · {p.sell_price:,.0f}원"


def _send_reply(reply_id: int, text: str) -> tuple[bool, str]:
    with get_db() as db:
        reply = db.get(ThreadsReply, reply_id)
        if not reply:
            return False, "답글을 찾을 수 없습니다."
        comment = db.get(ThreadsComment, reply.comment_id)
        if not comment:
            return False, "원본 댓글을 찾을 수 없습니다."
        try:
            remote_id = ThreadsClient().publish_text(text.strip(), reply_to_id=comment.threads_comment_id)
            reply.reply_text = text.strip()
            reply.threads_reply_id = remote_id
            reply.source = "human"
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


def _publish_now(media_type: str, text: str, media_url: str, alt_text: str, carousel_json: str) -> str:
    client = ThreadsClient()
    media_type = media_type.upper()
    if media_type == "TEXT":
        return client.publish_text(text)
    if media_type == "IMAGE":
        return client.publish_image(media_url, text, alt_text)
    if media_type == "VIDEO":
        return client.publish_video(media_url, text, alt_text)
    items = json.loads(carousel_json or "[]")
    return client.publish_carousel(items, text)


def render() -> None:
    init_db()
    products = _products()
    product_map = {p.id: p for p in products}

    st.markdown(
        """
        <style>
        .threads-hero{background:linear-gradient(135deg,#111827,#312E81 55%,#6D28D9);color:#fff;
          padding:24px 28px;border-radius:18px;margin-bottom:16px;box-shadow:0 12px 34px rgba(49,46,129,.18)}
        .threads-hero h2{margin:0;font-size:25px}.threads-hero p{margin:7px 0 0;color:rgba(255,255,255,.7)}
        .thread-card{border:1px solid #E2E8F0;border-radius:14px;padding:14px;background:#fff}
        </style>
        <div class="threads-hero"><h2>🧵 소셜커머스 → 스레드</h2>
        <p>AI 콘텐츠 → 게시·예약 → 댓글 영업 → 추적 → 스마트스토어·쿠팡 구매 귀속을 한 곳에서 관리합니다.</p></div>
        """,
        unsafe_allow_html=True,
    )

    tabs = st.tabs([
        "📊 현황판", "✨ 콘텐츠", "📝 게시물", "💬 댓글", "🔥 구매 가능 고객",
        "🤖 AI 답글함", "⚙️ 자동화", "🔐 API 설정",
    ])
    tab_dash, tab_content, tab_posts, tab_comments, tab_leads, tab_inbox, tab_rules, tab_api = tabs

    with tab_dash:
        with get_db() as db:
            metrics = {
                "posts": _count(db, ThreadsPost),
                "comments": _count(db, ThreadsComment),
                "hot": _count(db, ThreadsComment, ThreadsComment.purchase_intent_score >= .70),
                "sent": _count(db, ThreadsReply, ThreadsReply.status == "sent"),
                "drafts": _count(db, SocialContentDraft),
                "scheduled": _count(db, ScheduledSocialPost, ScheduledSocialPost.status == "scheduled"),
                "clicks": _count(db, TrackingClick),
                "orders": _count(db, OrderAttribution, OrderAttribution.attribution_type != "unattributed"),
            }
        cols = st.columns(8)
        for col, (icon, value, label) in zip(cols, [
            ("📝", metrics["posts"], "게시물"), ("💬", metrics["comments"], "댓글"),
            ("🔥", metrics["hot"], "구매 가능"), ("✅", metrics["sent"], "발행 답글"),
            ("✨", metrics["drafts"], "콘텐츠"), ("🗓️", metrics["scheduled"], "예약"),
            ("🔗", metrics["clicks"], "클릭"), ("🛒", metrics["orders"], "귀속 주문"),
        ]):
            col.metric(f"{icon} {label}", value)
        attr = attribution_summary()
        a, b, c = st.columns(3)
        a.metric("귀속 매출", f"{attr.get('attributed_revenue', 0):,.0f}원")
        b.metric("평균 귀속 신뢰도", f"{attr.get('avg_confidence', 0)*100:.1f}%")
        token = credential_status()
        c.metric("스레드 토큰", f"{token.get('days_remaining', '-')}일" if token.get("connected") else "미연결")

    with tab_content:
        st.subheader("AI 콘텐츠 자동 생성")
        if not products:
            st.info("상품 DB에 상품을 먼저 등록하세요.")
        else:
            c1, c2 = st.columns([1, 1.5], gap="large")
            with c1:
                pid = st.selectbox("상품", [p.id for p in products], format_func=lambda x: _product_label(product_map[x]), key="content_pid")
                angle = st.selectbox("콘텐츠 유형", ["problem_solution", "experience", "question", "comparison", "listicle"], format_func=angle_label)
                cta = st.text_input("댓글 유도 키워드", placeholder="청소기")
                count = st.slider("후보 개수", 1, 5, 3)
                if st.button("✨ AI 콘텐츠 생성", type="primary", use_container_width=True):
                    p = product_map[pid]
                    context = {"id": p.id, "name": p.name, "category": p.category, "brand": p.brand,
                               "origin": p.origin, "material": p.material, "sell_price": p.sell_price}
                    with st.spinner("콘텐츠 생성 중..."):
                        variants = generate_threads_content(context, angle, cta, count)
                    with get_db() as db:
                        for v in variants:
                            db.add(SocialContentDraft(product_id=pid, angle=angle, body=v["body"], cta_keyword=v["cta_keyword"], ai_source=v["source"], score=float(v["score"])))
                        db.commit()
                    st.success(f"{len(variants)}개 후보를 저장했습니다.")
                    st.rerun()
            with c2:
                st.markdown("#### 최근 콘텐츠 후보")
                with get_db() as db:
                    drafts = list(db.scalars(select(SocialContentDraft).order_by(desc(SocialContentDraft.created_at)).limit(20)).all())
                for d in drafts:
                    with st.container(border=True):
                        st.caption(f"#{d.id} · {angle_label(d.angle)} · 점수 {d.score:.0f} · {ai_source_label(d.ai_source)}")
                        st.write(d.body)

        st.divider()
        st.subheader("추적 링크 + 게시 예약")
        left, right = st.columns(2, gap="large")
        with left:
            if products:
                track_pid = st.selectbox("추적 상품", [p.id for p in products], format_func=lambda x: _product_label(product_map[x]), key="track_pid")
                platform = st.selectbox("목적 판매처", ["smartstore", "coupang"], format_func=platform_label)
                destination = st.text_input("실제 상품 주소", placeholder="https://...")
                campaign = st.text_input("캠페인 식별값", placeholder="threads-202608-carclean")
                if st.button("🔗 추적 링크 생성", use_container_width=True):
                    try:
                        row = create_tracking_link(track_pid, platform, destination, campaign, "threads")
                        base = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
                        st.success(f"{base}/t/{row.code}")
                    except Exception as exc:
                        st.error(str(exc))
        with right:
            with get_db() as db:
                drafts = list(db.scalars(select(SocialContentDraft).order_by(desc(SocialContentDraft.created_at)).limit(100)).all())
                links = list(db.scalars(select(TrackingLink).order_by(desc(TrackingLink.created_at)).limit(100)).all())
            if drafts and products:
                draft_id = st.selectbox("예약할 콘텐츠", [d.id for d in drafts], format_func=lambda x: f"#{x} · {next(d.body for d in drafts if d.id == x)[:45]}")
                d = next(x for x in drafts if x.id == draft_id)
                schedule_pid = d.product_id
                link_id = st.selectbox("추적 링크", [None] + [x.id for x in links], format_func=lambda x: "없음" if x is None else f"#{x}")
                media_type = st.selectbox("미디어", ["TEXT", "IMAGE", "VIDEO", "CAROUSEL"], key="schedule_media", format_func=media_label)
                media_url = st.text_input("이미지/영상 공개 주소", disabled=media_type not in {"IMAGE", "VIDEO"})
                alt_text = st.text_input("대체 설명", disabled=media_type == "TEXT")
                carousel_json = st.text_area("슬라이드형 미디어 설정(JSON)", value='[{"media_type":"IMAGE","image_url":"https://..."},{"media_type":"IMAGE","image_url":"https://..."}]', disabled=media_type != "CAROUSEL")
                schedule_date = st.date_input("예약 날짜", value=(datetime.now(KST) + timedelta(days=1)).date())
                schedule_time = st.time_input("예약 시간", value=(datetime.now(KST) + timedelta(hours=1)).time().replace(second=0, microsecond=0))
                if st.button("🗓️ 예약 저장", type="primary", use_container_width=True):
                    local = datetime.combine(schedule_date, schedule_time).replace(tzinfo=KST)
                    utc = local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
                    try:
                        items = json.loads(carousel_json) if media_type == "CAROUSEL" else []
                        with get_db() as db:
                            row = ScheduledSocialPost(
                                draft_id=d.id, product_id=schedule_pid, content=d.body, campaign_key=campaign,
                                cta_keyword=d.cta_keyword, tracking_link_id=link_id, scheduled_at=utc,
                                media_type=media_type, media_url=media_url, alt_text=alt_text,
                                carousel_items_json=json.dumps(items, ensure_ascii=False),
                            )
                            db.add(row)
                            current = db.get(SocialContentDraft, d.id)
                            if current:
                                current.status = "scheduled"
                                current.tracking_link_id = link_id
                            db.commit()
                        st.success("예약을 저장했습니다.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

    with tab_posts:
        st.subheader("즉시 게시 / 게시 이력")
        left, right = st.columns([1, 1.3], gap="large")
        with left:
            media_type = st.selectbox("게시 형식", ["TEXT", "IMAGE", "VIDEO", "CAROUSEL"], key="publish_media", format_func=media_label)
            text = st.text_area("본문", max_chars=500, height=160)
            media_url = st.text_input("이미지/영상 공개 주소", disabled=media_type not in {"IMAGE", "VIDEO"}, key="publish_url")
            alt_text = st.text_input("대체 설명", disabled=media_type == "TEXT", key="publish_alt")
            carousel_json = st.text_area("슬라이드형 미디어 설정(JSON)", value='[]', disabled=media_type != "CAROUSEL", key="publish_carousel")
            post_pid = st.selectbox("연결 상품", [None] + [p.id for p in products], format_func=lambda x: "미연결" if x is None else _product_label(product_map[x])) if products else None
            if st.button("🧵 스레드에 지금 발행", type="primary", use_container_width=True):
                try:
                    remote = _publish_now(media_type, text.strip(), media_url.strip(), alt_text.strip(), carousel_json)
                    with get_db() as db:
                        db.add(ThreadsPost(threads_post_id=remote, product_id=post_pid, content=text.strip(), status="published"))
                        db.commit()
                    st.success(f"발행 완료 · {remote}")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        with right:
            with get_db() as db:
                posts = list(db.scalars(select(ThreadsPost).order_by(desc(ThreadsPost.published_at)).limit(100)).all())
                schedules = list(db.scalars(select(ScheduledSocialPost).order_by(desc(ScheduledSocialPost.scheduled_at)).limit(50)).all())
            st.markdown("#### 게시 이력")
            st.dataframe([{"번호":p.id,"내용":p.content[:80],"스레드 게시물 ID":p.threads_post_id,"발행":p.published_at} for p in posts], use_container_width=True, hide_index=True)
            st.markdown("#### 예약 현황")
            st.dataframe([{"번호":s.id,"형식":media_label(s.media_type),"상태":status_label(s.status),"예약(한국시간)":s.scheduled_at.replace(tzinfo=ZoneInfo('UTC')).astimezone(KST).strftime('%m-%d %H:%M'),"오류":s.error[:80]} for s in schedules], use_container_width=True, hide_index=True)

    with tab_comments:
        st.subheader("댓글 관리")
        a, b, c = st.columns(3)
        intent_options = ["전체", "PURCHASE_INTENT", "SHIPPING", "STOCK", "PRICE", "COMPATIBILITY", "PRODUCT_INFO", "COMPLAINT", "RETURN", "UNKNOWN"]
        intent = a.selectbox("문의 유형", intent_options, format_func=lambda x: "전체" if x == "전체" else intent_label(x))
        minimum = b.slider("최소 구매의도", 0, 100, 0, 5) / 100
        human = c.checkbox("사람 확인 필요만")
        with get_db() as db:
            stmt = select(ThreadsComment).where(ThreadsComment.purchase_intent_score >= minimum)
            if intent != "전체":
                stmt = stmt.where(ThreadsComment.intent == intent)
            if human:
                stmt = stmt.where(ThreadsComment.requires_human.is_(True))
            rows = list(db.scalars(stmt.order_by(desc(ThreadsComment.received_at)).limit(300)).all())
        st.dataframe([{"사용자":r.author_username or r.author_id,"댓글":r.comment_text,"문의 유형":intent_label(r.intent),"구매의도":f"{r.purchase_intent_score*100:.0f}%","사람확인":"⚠️" if r.requires_human else "","수신":r.received_at} for r in rows], use_container_width=True, hide_index=True)

    with tab_leads:
        st.subheader("구매 가능 고객")
        threshold = st.slider("구매 가능 기준", 50, 100, 70, 5) / 100
        with get_db() as db:
            leads = list(db.scalars(select(ThreadsComment).where(ThreadsComment.purchase_intent_score >= threshold).order_by(desc(ThreadsComment.purchase_intent_score)).limit(200)).all())
        for lead in leads:
            icon = "🔥" if lead.purchase_intent_score >= .85 else "🟠"
            with st.container(border=True):
                st.markdown(f"**{icon} {lead.purchase_intent_score*100:.0f}% · @{lead.author_username or lead.author_id or '알 수 없음'} · {intent_label(lead.intent)}**")
                st.write(lead.comment_text)

    with tab_inbox:
        st.subheader("AI 답글함")
        with get_db() as db:
            inbox = list(db.execute(
                select(ThreadsReply, ThreadsComment).join(ThreadsComment, ThreadsReply.comment_id == ThreadsComment.id)
                .where(ThreadsReply.status.in_(["pending", "human_review", "failed"]))
                .order_by(desc(ThreadsComment.purchase_intent_score), desc(ThreadsReply.created_at)).limit(200)
            ).all())
        if not inbox:
            st.info("검수할 답글이 없습니다.")
        for reply, comment in inbox:
            with st.expander(f"{comment.purchase_intent_score*100:.0f}% · @{comment.author_username or comment.author_id or '알 수 없음'} · {intent_label(comment.intent)}", expanded=comment.requires_human or comment.purchase_intent_score >= .85):
                st.write(comment.comment_text)
                if comment.requires_human:
                    st.warning("민감 문의: 사람 확인이 필요합니다.")
                edited = st.text_area("답글 초안", value=reply.reply_text, max_chars=450, key=f"inbox_{reply.id}")
                s1, s2 = st.columns(2)
                if s1.button("💾 저장", key=f"save_{reply.id}", use_container_width=True):
                    with get_db() as db:
                        row = db.get(ThreadsReply, reply.id)
                        row.reply_text = edited.strip()
                        row.source = "human"
                        db.commit()
                    st.success("저장했습니다.")
                    st.rerun()
                if s2.button("✅ 승인·발행", key=f"send_{reply.id}", type="primary", use_container_width=True):
                    ok, msg = _send_reply(reply.id, edited)
                    (st.success if ok else st.error)(msg)
                    st.rerun()

    with tab_rules:
        st.subheader("자동화 규칙")
        left, right = st.columns([.9, 1.3], gap="large")
        with left:
            with st.form("rule_form", clear_on_submit=True):
                keyword = st.text_input("감지 키워드")
                template = st.text_area("답글", max_chars=450)
                priority = st.number_input("우선순위", 1, 9999, 100)
                save = st.form_submit_button("규칙 저장", type="primary", use_container_width=True)
            if save and keyword.strip() and template.strip():
                with get_db() as db:
                    exists = db.scalar(select(ThreadsAutomationRule).where(ThreadsAutomationRule.keyword == keyword.strip()))
                    if exists:
                        st.error("같은 키워드가 이미 있습니다.")
                    else:
                        db.add(ThreadsAutomationRule(keyword=keyword.strip(), reply_template=template.strip(), priority=int(priority), enabled=True))
                        db.commit()
                        st.success("저장했습니다.")
                        st.rerun()
        with right:
            with get_db() as db:
                rules = list(db.scalars(select(ThreadsAutomationRule).order_by(ThreadsAutomationRule.priority)).all())
            for r in rules:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([4,1,1])
                    c1.markdown(f"**{'🟢' if r.enabled else '⚪'} `{r.keyword}`** · {r.priority}")
                    c1.caption(r.reply_template)
                    if c2.button("켜기/끄기", key=f"rt_{r.id}"):
                        with get_db() as db:
                            row = db.get(ThreadsAutomationRule,r.id)
                            row.enabled = not row.enabled
                            db.commit()
                        st.rerun()
                    if c3.button("삭제", key=f"rd_{r.id}"):
                        with get_db() as db:
                            row = db.get(ThreadsAutomationRule,r.id)
                            db.delete(row)
                            db.commit()
                        st.rerun()

    with tab_api:
        st.subheader("Meta 스레드 API 설정")
        status = credential_status()
        if status.get("connected"):
            a,b,c,d = st.columns(4)
            a.metric("계정", f"@{status.get('username') or status.get('threads_user_id')}")
            b.metric("토큰 잔여", f"{status.get('days_remaining')}일")
            c.metric("상태", status_label(status.get("status")))
            d.metric("만료일", (status.get("expires_at") or "")[:10])
            if status.get("days_remaining") is not None and status["days_remaining"] <= 7:
                st.warning("토큰 만료가 임박했습니다. 지금 갱신하세요.")
            if st.button("♻️ 60일 토큰 갱신", type="primary"):
                try:
                    st.success(f"갱신 완료 · 잔여 {refresh_stored_credential().get('days_remaining')}일")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        else:
            st.warning("연결된 스레드 OAuth 계정이 없습니다.")
            api_internal = os.getenv("SOCIAL_API_INTERNAL_URL", "http://social-api:8000").rstrip("/")
            try:
                result = httpx.get(f"{api_internal}/api/v1/threads/oauth/start", timeout=5).json()
                st.link_button("🔗 Meta 스레드 계정 연결", result["authorization_url"], type="primary")
            except Exception as exc:
                st.info("소셜 API가 실행된 뒤 OAuth 연결 버튼이 활성화됩니다.")
                st.caption(str(exc))

        st.divider()
        st.markdown("#### 필수 환경설정 상태")
        checks = {
            "THREADS_APP_ID": os.getenv("THREADS_APP_ID", ""),
            "THREADS_APP_SECRET": os.getenv("THREADS_APP_SECRET", ""),
            "THREADS_OAUTH_REDIRECT_URI": os.getenv("THREADS_OAUTH_REDIRECT_URI", ""),
            "THREADS_TOKEN_ENCRYPTION_KEY": os.getenv("THREADS_TOKEN_ENCRYPTION_KEY", ""),
            "THREADS_VERIFY_TOKEN": os.getenv("THREADS_VERIFY_TOKEN", ""),
            "PUBLIC_BASE_URL": os.getenv("PUBLIC_BASE_URL", ""),
            "TRACKING_HASH_SALT": os.getenv("TRACKING_HASH_SALT", ""),
        }
        st.dataframe([{"설정 항목":k,"상태":"✅ 설정됨" if v else "❌ 미설정"} for k,v in checks.items()], use_container_width=True, hide_index=True)
        st.caption("접근 토큰은 OAuth 완료 후 암호화되어 DB에 저장되며 화면에는 원문을 노출하지 않습니다.")
