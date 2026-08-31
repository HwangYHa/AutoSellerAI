"""AutoSellerAI Stable Diffusion human image studio."""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from app.image_studio.mappings import (
    AGE_MAP,
    BACKGROUND_MAP,
    BODY_FRAME_MAP,
    CAMERA_MAP,
    CHEST_PROPORTION_MAP,
    DOF_MAP,
    EXPRESSION_MAP,
    FACE_SHAPE_MAP,
    GENDER_MAP,
    HAIR_COLOR_MAP,
    HAIR_STYLE_MAP,
    HEIGHT_MAP,
    LIGHTING_MAP,
    LIP_STYLE_MAP,
    MOOD_MAP,
    NOSE_STYLE_MAP,
    OUTFIT_COLOR_MAP,
    OUTFIT_MAP,
    PERSONALITY_MAP,
    POSE_MAP,
    PRESETS,
    SHOULDER_MAP,
    SHOT_MAP,
    SKIN_TONE_MAP,
    WAIST_HIP_MAP,
    EYE_STYLE_MAP,
)
from app.image_studio.prompt_builder import build_prompt
from app.image_studio.schemas import HumanImageRequest
from app.image_studio.sd_webui_client import StableDiffusionWebUIClient
from app.image_studio.service import create_generation, generation_to_dict, list_generations


st.set_page_config(page_title="AI 인물 이미지 스튜디오 | AutoSellerAI", page_icon="🎨", layout="wide")

st.markdown(
    """
    <style>
      .block-container{max-width:1480px;padding-top:1.2rem}
      .sd-hero{padding:22px 26px;border-radius:18px;background:linear-gradient(135deg,#111827,#4338ca 58%,#7c3aed);color:white;margin-bottom:18px}
      .sd-hero h2{margin:0;font-weight:850}.sd-hero p{margin:7px 0 0;color:rgba(255,255,255,.76)}
      .status-card{padding:12px 14px;border:1px solid #e2e8f0;border-radius:12px;background:#fff}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="sd-hero">
      <h2>🎨 AI 인물 이미지 스튜디오</h2>
      <p>복잡한 Stable Diffusion 프롬프트 대신 외형·체형·의상·분위기·촬영 조건을 선택하면 AutoSellerAI가 최종 프롬프트와 WebUI API payload를 자동 구성합니다.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=15, show_spinner=False)
def _capabilities():
    return StableDiffusionWebUIClient().capabilities().model_dump()


def _keys(mapping) -> list[str]:
    return list(mapping.keys())


def _choice(label: str, mapping, key: str, default: str):
    options = _keys(mapping)
    current = st.session_state.get(key, default)
    if current not in options:
        current = default
    return st.selectbox(label, options, index=options.index(current), key=key)


def _apply_preset(name: str) -> None:
    p = PRESETS[name]
    values = {
        "sd_shot": p["shot"],
        "sd_background": p["background"],
        "sd_lighting": p["lighting"],
        "sd_camera": p["camera"],
        "sd_dof": p["dof"],
        "sd_steps": int(p["steps"]),
        "sd_cfg": float(p["cfg_scale"]),
        "sd_width": int(p["width"]),
        "sd_height": int(p["height"]),
        "sd_hr": bool(p["hires"]),
    }
    for key, value in values.items():
        st.session_state[key] = value


caps = _capabilities()
status_col, model_col, ad_col, refresh_col = st.columns([1.2, 2.2, 1.2, 1])
with status_col:
    if caps["ok"]:
        st.success("WebUI 연결됨")
    else:
        st.error("WebUI 연결 안 됨")
with model_col:
    st.caption("현재 WebUI / 체크포인트")
    st.code((caps.get("base_url") or "-") + "\n" + (caps.get("model") or "체크포인트 확인 불가"), language=None)
with ad_col:
    st.metric("ADetailer", "사용 가능" if caps.get("adetailer_available") else "미감지")
with refresh_col:
    if st.button("🔄 연결 재확인", use_container_width=True):
        _capabilities.clear()
        st.rerun()

if not caps["ok"]:
    st.warning(
        (caps.get("error") or "Stable Diffusion WebUI에 연결할 수 없습니다.")
        + "\n\nDocker Compose 사용 시 AutoSellerAI는 `host.docker.internal:7860`으로 호스트 WebUI에 연결합니다. "
        "WebUI가 API를 받도록 실행되어 있어야 합니다."
    )

preset_col, apply_col = st.columns([4, 1])
with preset_col:
    preset = st.selectbox("빠른 프리셋", list(PRESETS.keys()), key="sd_preset")
with apply_col:
    st.write("")
    st.write("")
    if st.button("프리셋 적용", type="secondary", use_container_width=True):
        _apply_preset(preset)
        st.rerun()

(tab_person, tab_body, tab_style, tab_scene, tab_advanced, tab_history) = st.tabs(
    ["🙂 얼굴·헤어", "🧍 체형", "👗 의상·분위기", "📷 촬영", "⚙️ 고급 설정", "🖼️ 생성 이력"]
)

with tab_person:
    c1, c2, c3 = st.columns(3)
    with c1:
        gender = _choice("성별", GENDER_MAP, "sd_gender", "여성")
        age = _choice("연령대", AGE_MAP, "sd_age", "20대 후반")
        skin_tone = _choice("피부톤", SKIN_TONE_MAP, "sd_skin", "내추럴")
    with c2:
        hair_style = _choice("헤어스타일", HAIR_STYLE_MAP, "sd_hair", "긴 웨이브")
        hair_color = _choice("헤어 컬러", HAIR_COLOR_MAP, "sd_hair_color", "다크브라운")
        face_shape = _choice("얼굴형", FACE_SHAPE_MAP, "sd_face", "계란형")
    with c3:
        eye_style = _choice("눈매", EYE_STYLE_MAP, "sd_eye", "자연스러운 눈매")
        nose_style = _choice("코", NOSE_STYLE_MAP, "sd_nose", "자연스러운 코")
        lip_style = _choice("입술", LIP_STYLE_MAP, "sd_lip", "자연스러운 입술")
        expression = _choice("표정", EXPRESSION_MAP, "sd_expression", "은은한 미소")

with tab_body:
    st.caption("신체 옵션은 실사 자연스러움을 우선하도록 범위를 제한했습니다. 과도한 비율 지시는 손·관절·의상 왜곡을 크게 늘릴 수 있습니다.")
    c1, c2, c3 = st.columns(3)
    with c1:
        body_frame = _choice("전체 체형", BODY_FRAME_MAP, "sd_body", "균형형")
        height_impression = _choice("키 인상", HEIGHT_MAP, "sd_height_impression", "평균적인 인상")
    with c2:
        shoulder = _choice("어깨선", SHOULDER_MAP, "sd_shoulder", "균형 잡힌 어깨")
        waist_hip = _choice("허리·골반 실루엣", WAIST_HIP_MAP, "sd_waist_hip", "균형형")
    with c3:
        chest_proportion = _choice("상체 비율", CHEST_PROPORTION_MAP, "sd_chest", "자연스러운 비율")

with tab_style:
    c1, c2 = st.columns(2)
    with c1:
        outfit = _choice("의상 스타일", OUTFIT_MAP, "sd_outfit", "데일리 캐주얼")
        outfit_color = _choice("의상 컬러", OUTFIT_COLOR_MAP, "sd_outfit_color", "자동/자연스럽게")
    with c2:
        mood = _choice("분위기", MOOD_MAP, "sd_mood", "자연스러움")
        personality = _choice("성격/인상", PERSONALITY_MAP, "sd_personality", "밝고 친근함")

with tab_scene:
    c1, c2, c3 = st.columns(3)
    with c1:
        pose = _choice("포즈", POSE_MAP, "sd_pose", "카메라 바라보기")
        shot = _choice("구도", SHOT_MAP, "sd_shot", PRESETS[preset]["shot"])
    with c2:
        background = _choice("배경", BACKGROUND_MAP, "sd_background", PRESETS[preset]["background"])
        lighting = _choice("조명", LIGHTING_MAP, "sd_lighting", PRESETS[preset]["lighting"])
    with c3:
        depth_of_field = _choice("심도", DOF_MAP, "sd_dof", PRESETS[preset]["dof"])
        camera = _choice("카메라 느낌", CAMERA_MAP, "sd_camera", PRESETS[preset]["camera"])

with tab_advanced:
    available_samplers = [x for x in caps.get("samplers", []) if x] or ["DPM++ 2M"]
    available_schedulers = [x for x in caps.get("schedulers", []) if x] or ["Karras"]
    available_upscalers = [x for x in caps.get("upscalers", []) if x] or ["R-ESRGAN 4x+"]
    checkpoints = [""] + [x for x in caps.get("checkpoints", []) if x]

    c1, c2, c3 = st.columns(3)
    with c1:
        steps = st.slider("Steps", 10, 60, int(st.session_state.get("sd_steps", PRESETS[preset]["steps"])), key="sd_steps")
        cfg_scale = st.slider("CFG Scale", 1.0, 12.0, float(st.session_state.get("sd_cfg", PRESETS[preset]["cfg_scale"])), 0.5, key="sd_cfg")
        sampler_name = st.selectbox("Sampler", available_samplers, index=available_samplers.index("DPM++ 2M") if "DPM++ 2M" in available_samplers else 0)
        scheduler = st.selectbox("Scheduler", available_schedulers, index=available_schedulers.index("Karras") if "Karras" in available_schedulers else 0)
    with c2:
        width = st.number_input("기본 폭", min_value=384, max_value=1536, step=64, value=int(st.session_state.get("sd_width", PRESETS[preset]["width"])), key="sd_width")
        height = st.number_input("기본 높이", min_value=384, max_value=2048, step=64, value=int(st.session_state.get("sd_height", PRESETS[preset]["height"])), key="sd_height")
        seed = st.number_input("Seed (-1 = 랜덤)", min_value=-1, max_value=2147483647, value=-1, step=1)
        batch_size = st.slider("생성 장수", 1, 4, 1)
    with c3:
        enable_hr = st.checkbox("Hires.fix 사용", value=bool(st.session_state.get("sd_hr", PRESETS[preset]["hires"])), key="sd_hr")
        hr_upscaler = st.selectbox("Hires 업스케일러", available_upscalers, index=available_upscalers.index("R-ESRGAN 4x+") if "R-ESRGAN 4x+" in available_upscalers else 0)
        hr_scale = st.slider("Hires 배율", 1.0, 2.0, 1.5, 0.1)
        denoising_strength = st.slider("Hires Denoising", 0.1, 0.7, 0.32, 0.01)
        checkpoint = st.selectbox("체크포인트 (비우면 현재 모델)", checkpoints, format_func=lambda x: "현재 WebUI 체크포인트" if not x else x)

    st.markdown("#### ADetailer")
    a1, a2, a3 = st.columns(3)
    adetailer_enabled = a1.checkbox("얼굴 ADetailer", value=True, disabled=not bool(caps.get("adetailer_available")))
    adetailer_model = a2.text_input("ADetailer 모델", value="face_yolov8n.pt")
    adetailer_denoising = a3.slider("ADetailer denoising", 0.1, 0.7, 0.32, 0.01)

    with st.expander("직접 프롬프트 추가 (선택)"):
        custom_positive = st.text_area("추가 Positive Prompt", max_chars=1200, placeholder="구조화 옵션으로 표현하기 어려운 장면만 추가하세요.")
        custom_negative = st.text_area("추가 Negative Prompt", max_chars=1200, placeholder="특정 체크포인트에서 반복되는 문제를 제외할 때 사용하세요.")

# Variables are initialized by Streamlit while rendering all tab bodies above.
request = HumanImageRequest(
    preset=preset,
    gender=gender,
    age=age,
    hair_style=hair_style,
    hair_color=hair_color,
    face_shape=face_shape,
    eye_style=eye_style,
    nose_style=nose_style,
    lip_style=lip_style,
    skin_tone=skin_tone,
    expression=expression,
    body_frame=body_frame,
    height_impression=height_impression,
    shoulder=shoulder,
    waist_hip=waist_hip,
    chest_proportion=chest_proportion,
    outfit=outfit,
    outfit_color=outfit_color,
    mood=mood,
    personality=personality,
    pose=pose,
    shot=shot,
    background=background,
    lighting=lighting,
    depth_of_field=depth_of_field,
    camera=camera,
    custom_positive=custom_positive,
    custom_negative=custom_negative,
    width=int(width),
    height=int(height),
    steps=int(steps),
    cfg_scale=float(cfg_scale),
    sampler_name=sampler_name,
    scheduler=scheduler,
    seed=int(seed),
    batch_size=int(batch_size),
    enable_hr=bool(enable_hr),
    hr_scale=float(hr_scale),
    hr_upscaler=hr_upscaler,
    hr_second_pass_steps=10,
    denoising_strength=float(denoising_strength),
    adetailer_enabled=bool(adetailer_enabled),
    adetailer_model=adetailer_model.strip() or "face_yolov8n.pt",
    adetailer_denoising_strength=float(adetailer_denoising),
    checkpoint=checkpoint,
)

bundle = build_prompt(request)
st.markdown("### 🧠 AutoSellerAI 최종 프롬프트")
with st.expander("생성 전에 Positive / Negative Prompt 확인", expanded=False):
    st.caption(bundle.subject_summary)
    st.text_area("Positive", value=bundle.positive, height=180, disabled=True)
    st.text_area("Negative", value=bundle.negative, height=150, disabled=True)

left_action, right_action = st.columns([3, 1])
with left_action:
    generate_disabled = not bool(caps["ok"])
    if st.button("✨ Stable Diffusion 이미지 생성", type="primary", use_container_width=True, disabled=generate_disabled):
        try:
            row = create_generation(request)
            st.success(f"이미지 생성 작업 #{row.id}을 전용 image worker에 등록했습니다. 생성 이력에서 상태를 확인하세요.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
with right_action:
    if st.button("🔄 이력 새로고침", use_container_width=True):
        st.rerun()

with tab_history:
    rows = list_generations(60)
    if not rows:
        st.info("아직 생성 이력이 없습니다.")
    for row in rows:
        data = generation_to_dict(row)
        status_icon = {"queued": "⏳", "running": "🎨", "completed": "✅", "failed": "❌"}.get(data["status"], "•")
        title = f"{status_icon} #{row.id} · {row.preset or '-'} · {row.subject_summary or '-'}"
        with st.expander(title, expanded=row.status == "completed" and row == rows[0]):
            c1, c2, c3 = st.columns(3)
            c1.metric("상태", row.status)
            c2.caption(f"생성: {row.created_at:%Y-%m-%d %H:%M:%S}")
            c3.caption(f"RQ: {row.rq_job_id or '-'}")
            if data["warnings"]:
                st.warning("\n".join(f"• {x}" for x in data["warnings"]))
            if row.error:
                st.error(row.error)

            paths = [Path(x) for x in data["image_paths"]]
            existing = [p for p in paths if p.exists()]
            if existing:
                cols = st.columns(min(len(existing), 3))
                for idx, path in enumerate(existing):
                    with cols[idx % len(cols)]:
                        st.image(str(path), caption=path.name, use_container_width=True)
                        st.download_button(
                            "PNG 저장",
                            data=path.read_bytes(),
                            file_name=path.name,
                            mime="image/png",
                            key=f"download_sd_{row.id}_{idx}",
                            use_container_width=True,
                        )
            elif row.status == "completed":
                st.warning("DB에는 완료로 기록됐지만 이미지 파일을 현재 컨테이너에서 찾지 못했습니다.")

            with st.expander("프롬프트 / 생성 메타데이터"):
                st.text_area("Positive Prompt", row.prompt, height=150, disabled=True, key=f"p_{row.id}")
                st.text_area("Negative Prompt", row.negative_prompt, height=120, disabled=True, key=f"n_{row.id}")
                info = data["response_info"]
                if info:
                    st.json(info)
                if data["payload"]:
                    safe_payload = dict(data["payload"])
                    st.code(json.dumps(safe_payload, ensure_ascii=False, indent=2), language="json")
