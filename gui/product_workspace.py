"""Seller OS v2 상품관리 워크스페이스.

원칙:
- 한 화면에서 검색 → 판단 → 일괄작업 → 상세확인 순서만 사용한다.
- 공급처/판매채널별 예외 로직은 app.services 계층에 숨긴다.
- 외부 이미지 URL을 브라우저에 직접 핫링크하지 않고 서버측으로 받아 표시한다.
- 깨진 이미지 URL은 명확한 placeholder로 처리한다.
"""
from __future__ import annotations

import streamlit as st

from app.media.image_display import clear_display_image_cache, fetch_display_image
from app.pipeline import upload_product
from app.services.product_catalog import (
    SOURCE_LABELS,
    delete_products,
    get_catalog,
    get_product_snapshot,
    repair_all_product_images,
    repair_product_image_urls,
    set_products_status,
)


def _money(value: float | int) -> str:
    return f"{float(value or 0):,.0f}원"


def _channel_badges(channels: list[str]) -> str:
    labels = []
    if "coupang" in channels:
        labels.append("🟠 쿠팡")
    if "smartstore" in channels:
        labels.append("🟢 스마트스토어")
    return " · ".join(labels) if labels else "미등록"


def _render_placeholder(height: int = 112, caption: str = "이미지 없음") -> None:
    st.markdown(
        f"""
        <div style="width:100%;height:{height}px;border:1px solid #e2e8f0;border-radius:12px;
        background:#f8fafc;display:flex;align-items:center;justify-content:center;
        color:#94a3b8;font-size:26px">🖼️</div>
        """,
        unsafe_allow_html=True,
    )
    if caption:
        st.caption(caption)


def _image_bytes(url: str, source_url: str = "") -> bytes | None:
    if not url:
        return None
    return fetch_display_image(str(url), str(source_url or ""))


def _render_remote_image(url: str, source_url: str = "", *, height: int = 112) -> bool:
    """외부 URL을 서버측으로 다운로드해 Streamlit에 표시한다."""
    data = _image_bytes(url, source_url)
    if not data:
        _render_placeholder(height=height, caption="이미지 불러오기 실패")
        return False
    st.image(data, use_container_width=True)
    return True


def _render_product_card(item: dict) -> None:
    with st.container(border=True):
        image_col, info_col, action_col = st.columns([1.1, 4.8, 1.4], vertical_alignment="center")
        with image_col:
            if item.get("image_url"):
                _render_remote_image(item["image_url"], item.get("source_url", ""))
            else:
                _render_placeholder()

        with info_col:
            st.markdown(f"**{item['name']}**")
            st.caption(
                f"{item['source_label']} · {item['sku']} · {item['status_label']} · "
                f"{_channel_badges(item['channels'])}"
            )
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("판매가", _money(item["sell_price"]))
            p2.metric("공급가", _money(item["supply_price"]) if item["supply_price"] else "-")
            margin = item.get("margin_pct")
            p3.metric("단순마진", f"{margin:.1f}%" if margin is not None else "-")
            p4.metric("이미지", f"{item['image_count']} + 상세 {item['detail_image_count']}")
            if item.get("issues"):
                st.caption("⚠️ " + " · ".join(item["issues"]))

        with action_col:
            selected = st.checkbox("선택", key=f"catalog_select_{item['id']}")
            if selected:
                current = set(st.session_state.get("catalog_selected_ids", []))
                current.add(item["id"])
                st.session_state["catalog_selected_ids"] = sorted(current)
            else:
                current = set(st.session_state.get("catalog_selected_ids", []))
                if item["id"] in current:
                    current.remove(item["id"])
                    st.session_state["catalog_selected_ids"] = sorted(current)

            if st.button("상세", key=f"detail_{item['id']}", use_container_width=True):
                st.session_state["catalog_detail_id"] = item["id"]
                st.rerun()
            if item.get("source_url"):
                st.link_button("원본 보기", item["source_url"], use_container_width=True)


def _render_detail_panel(product_id: int) -> None:
    item = get_product_snapshot(product_id)
    if not item:
        st.session_state.pop("catalog_detail_id", None)
        return

    st.divider()
    title_col, close_col = st.columns([6, 1])
    title_col.markdown(f"### 상품 상세 · #{item['id']}")
    if close_col.button("닫기", use_container_width=True):
        st.session_state.pop("catalog_detail_id", None)
        st.rerun()

    left, right = st.columns([1.7, 3.3], gap="large")
    with left:
        if item["images"]:
            _render_remote_image(item["images"][0], item.get("source_url", ""), height=220)
            if len(item["images"]) > 1:
                thumbs = st.columns(min(4, len(item["images"]) - 1))
                for col, url in zip(thumbs, item["images"][1:5]):
                    with col:
                        data = _image_bytes(url, item.get("source_url", ""))
                        if data:
                            st.image(data, use_container_width=True)
                        else:
                            _render_placeholder(height=72, caption="")
        else:
            _render_placeholder(height=220)

    with right:
        st.markdown(f"#### {item['name']}")
        st.write(f"**공급처/유입:** {item['source_label']}")
        st.write(f"**상태:** {item['status_label']}")
        st.write(f"**판매채널:** {_channel_badges(item['channels'])}")
        st.write(f"**판매가:** {_money(item['sell_price'])}")
        st.write(f"**공급가:** {_money(item['supply_price']) if item['supply_price'] else '-'}")
        st.write(f"**원산지:** {item['origin'] or '-'}")
        st.write(f"**카테고리:** {item['category'] or '-'}")
        st.write(f"**브랜드:** {item['brand'] or '-'}")

        if item.get("listings"):
            st.markdown("**판매채널 연결**")
            st.dataframe(
                [{
                    "채널": x["platform"],
                    "상품번호": x["platform_id"],
                    "상태": x["status"],
                    "오류": x["error"][:100],
                } for x in item["listings"]],
                use_container_width=True,
                hide_index=True,
            )

    if item.get("detail_images"):
        with st.expander(f"상세 이미지 {len(item['detail_images'])}장"):
            for start in range(0, min(len(item["detail_images"]), 18), 3):
                cols = st.columns(3)
                for col, url in zip(cols, item["detail_images"][start:start + 3]):
                    with col:
                        data = _image_bytes(url, item.get("source_url", ""))
                        if data:
                            st.image(data, use_container_width=True)
                        else:
                            _render_placeholder(height=120, caption="")

    if item.get("options"):
        with st.expander("옵션"):
            st.json(item["options"], expanded=False)


def _run_bulk_upload(ids: list[int], platforms: list[str]) -> None:
    successes = 0
    failures: list[str] = []
    progress = st.progress(0)
    for index, product_id in enumerate(ids, start=1):
        results = upload_product(product_id, platforms)
        if all(x.get("status") == "success" for x in results):
            successes += 1
        else:
            errors = "; ".join(
                f"{x.get('platform')}: {x.get('error', '')}" for x in results if x.get("status") != "success"
            )
            failures.append(f"#{product_id} {errors}")
        progress.progress(index / max(len(ids), 1))
    if successes:
        st.success(f"{successes}개 상품 판매채널 등록 완료")
    if failures:
        st.error("등록 실패: " + " | ".join(failures[:5]))


def _show_image_repair_result(result: dict) -> None:
    local = result.get("local", {})
    suppliers = result.get("suppliers", {})
    marketplaces = result.get("marketplaces", {})

    st.success(
        "이미지 복구 완료 · "
        f"URL 정리 {local.get('changed', 0)}건 · "
        f"공급처 재조회 {suppliers.get('checked', 0)}개 / 갱신 {suppliers.get('updated', 0)}개"
    )
    if suppliers.get("still_missing"):
        st.warning(f"공급처 재조회 후에도 대표 이미지가 없는 상품: {suppliers['still_missing']}개")
    if suppliers.get("errors"):
        with st.expander("공급처 이미지 재조회 오류"):
            for error in suppliers["errors"]:
                st.write("- " + error)

    for platform, label in (("coupang", "쿠팡"), ("smartstore", "스마트스토어")):
        p = marketplaces.get(platform) or {}
        if p.get("ok"):
            st.caption(
                f"✅ {label}: 발견 {p.get('total_found', 0)} · 신규 {p.get('created', 0)} · "
                f"변경 {p.get('updated', 0)}"
            )
        elif p:
            st.warning(f"{label} 재동기화는 실패했습니다: {p.get('error', '알 수 없는 오류')}")


def render_product_workspace() -> None:
    st.session_state.setdefault("catalog_selected_ids", [])
    st.markdown("### 📦 상품 관리")
    st.caption("상품을 찾고 → 상태를 판단하고 → 필요한 작업만 실행합니다. 공급처별 세부 메뉴를 오갈 필요가 없습니다.")

    # 진입 시에는 네트워크 요청 없이 저장된 URL 형식만 정리한다.
    if not st.session_state.get("catalog_image_repair_done"):
        repair_product_image_urls()
        st.session_state["catalog_image_repair_done"] = True

    f1, f2, f3, f4, f5 = st.columns([2.4, 1.1, 1.2, 1.1, 1.1])
    search = f1.text_input("상품 검색", placeholder="상품명 · SKU · 상품번호", label_visibility="collapsed")
    status_label = f2.selectbox("상태", ["전체", "판매 준비", "판매중", "준비중"], label_visibility="collapsed")
    source_label = f3.selectbox(
        "공급처",
        ["전체", "도매꾹", "도매매", "온채널", "오너클랜", "쿠팡 직접등록", "스마트스토어 직접등록"],
        label_visibility="collapsed",
    )
    channel_label = f4.selectbox("채널", ["전체", "쿠팡", "스마트스토어"], label_visibility="collapsed")
    action_only = f5.toggle("조치 필요만", value=False)

    reverse_status = {"판매 준비": "ready", "판매중": "listed", "준비중": "draft"}
    reverse_source = {v: k for k, v in SOURCE_LABELS.items()}
    reverse_channel = {"쿠팡": "coupang", "스마트스토어": "smartstore"}

    page = int(st.session_state.get("catalog_page", 1))
    data = get_catalog(
        search=search,
        status=reverse_status.get(status_label, ""),
        source=reverse_source.get(source_label, ""),
        channel=reverse_channel.get(channel_label, ""),
        page=page,
        page_size=20,
        action_only=action_only,
    )
    if page > data["pages"]:
        st.session_state["catalog_page"] = data["pages"]
        st.rerun()

    metrics = data["metrics"]
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("전체 상품", metrics["total"])
    m2.metric("판매중", metrics["listed"])
    m3.metric("판매 준비", metrics["ready"])
    m4.metric("조치 필요", metrics["needs_action"])
    m5.metric("이미지 없음", metrics["no_image"])

    with st.container(border=True):
        b1, b2, b3, b4 = st.columns([1.3, 1.4, 1.4, 2.5])
        if b1.button("🔄 판매채널 동기화", use_container_width=True):
            st.switch_page("pages/05_판매채널_상품동기화.py")
        if b2.button("➕ 공급처 상품 가져오기", use_container_width=True):
            st.switch_page("pages/30_상품소싱.py")
        if b3.button("🖼️ 전체 이미지 복구", use_container_width=True):
            with st.spinner("공급처 원본·판매채널 API에서 대표/상세 이미지를 다시 수집 중입니다..."):
                result = repair_all_product_images(include_marketplaces=True)
                clear_display_image_cache()
            st.session_state["catalog_last_image_repair"] = result
            st.rerun()
        b4.caption(
            "이미지가 없거나 깨지면 ‘전체 이미지 복구’를 한 번 실행하세요. "
            "도매꾹·도매매·온채널·오너클랜 원본과 쿠팡·스마트스토어를 다시 조회합니다."
        )

    last_repair = st.session_state.pop("catalog_last_image_repair", None)
    if last_repair:
        _show_image_repair_result(last_repair)

    selected_ids = sorted(set(int(x) for x in st.session_state.get("catalog_selected_ids", [])))
    if selected_ids:
        with st.container(border=True):
            st.markdown(f"**선택 {len(selected_ids)}개 · 일괄 작업**")
            a1, a2, a3, a4, a5 = st.columns([1.1, 1.1, 1.4, 1.2, 1.0])
            cp = a1.checkbox("쿠팡", value=True, key="bulk_cp")
            ss = a2.checkbox("스마트스토어", value=True, key="bulk_ss")
            if a3.button("판매채널 등록", type="primary", use_container_width=True):
                platforms = [p for p, enabled in [("coupang", cp), ("smartstore", ss)] if enabled]
                if not platforms:
                    st.warning("등록할 판매채널을 선택하세요.")
                else:
                    _run_bulk_upload(selected_ids, platforms)
                    st.session_state["catalog_selected_ids"] = []
                    st.rerun()
            if a4.button("판매 준비로 변경", use_container_width=True):
                set_products_status(selected_ids, "ready")
                st.session_state["catalog_selected_ids"] = []
                st.rerun()
            if a5.button("선택 해제", use_container_width=True):
                for pid in selected_ids:
                    st.session_state[f"catalog_select_{pid}"] = False
                st.session_state["catalog_selected_ids"] = []
                st.rerun()

            with st.expander("위험 작업"):
                confirm = st.checkbox("선택 상품을 AutoSellerAI 로컬 DB에서 삭제하는 것을 확인합니다.")
                if st.button("선택 상품 삭제", disabled=not confirm):
                    deleted = delete_products(selected_ids)
                    st.session_state["catalog_selected_ids"] = []
                    st.success(f"{deleted}개 삭제 완료")
                    st.rerun()

    if not data["items"]:
        st.info("조건에 맞는 상품이 없습니다. 필터를 줄이거나 공급처 상품을 가져오세요.")
    else:
        for item in data["items"]:
            _render_product_card(item)

    if data["pages"] > 1:
        prev_col, mid_col, next_col = st.columns([1, 2, 1])
        if prev_col.button("← 이전", disabled=page <= 1, use_container_width=True):
            st.session_state["catalog_page"] = page - 1
            st.rerun()
        mid_col.markdown(
            f"<div style='text-align:center;padding:8px'>페이지 {page} / {data['pages']} · {data['total']}개</div>",
            unsafe_allow_html=True,
        )
        if next_col.button("다음 →", disabled=page >= data["pages"], use_container_width=True):
            st.session_state["catalog_page"] = page + 1
            st.rerun()

    detail_id = st.session_state.get("catalog_detail_id")
    if detail_id:
        _render_detail_panel(int(detail_id))
