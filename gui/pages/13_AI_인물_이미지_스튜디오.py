"""AutoSellerAI Stable Diffusion human image studio."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
from app.image_studio.prompt_builder import build_prompt, build_txt2img_payload
from app.image_studio.schemas import HumanImageRequest
from app.image_studio.sd_webui_client import StableDiffusionWebUIClient, choose_upscaler
from app.image_studio.service import (
    create_generation,
    generation_to_dict,
    get_image_queue_status,
    list_generations,
)


st.set_page_config(page_title="AI 인물 이미지 스튜디오 | AutoSellerAI", page_icon="🎨", layout="wide")

st.markdown(
    """
    <style>
      .block-container{max-width:1540px;padding-top:1.0rem;padding-bottom:3rem}
      .sd-hero{padding:24px 28px;border-radius:20px;background:linear-gradient(135deg,#0f172a,#312e81 52%,#7c3aed);color:white;margin-bottom:16px;box-shadow:0 14px 30px rgba(49,46,129,.16)}
      .sd-hero h2{margin:0;font-weight:850;letter-spacing:-.02em}.sd-hero p{margin:8px 0 0;color:rgba(255,255,255,.78);line-height:1.55}
      .sd-note{padding:12px 14px;border-radius:12px;background:#f8fafc;border:1px solid #e2e8f0;color:#334155;font-size:.92rem}
      .sd-ready{padding:13px 15px;border-radius:14px;background:#f0fdf4;border:1px solid #bbf7d0;color:#166534;font-weight:700}
      .sd-blocked{padding:13px 15px;border-radius:14px;background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;font-weight:700}
      .sd-summary{padding:14px 16px;border-radius:14px;background:#111827;color:#f8fafc;line-height:1.65}
      div[data-testid="stMetric"]{background:#fff;border:1px solid #e5e7eb;padding:10px 12px;border-radius:14px}
      .stTabs [data-baseweb="tab-list"]{gap:6px;flex-wrap:wrap}
      .stTabs [data-baseweb="tab"]{height:42px;border-radius:10px;padding-left:14px;padding-right:14px}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="sd-hero">
      <h2>🎨 AI 인물 이미지 스튜디오</h2>
      <p>Stable Diffusion WebUI를 직접 열어 프롬프트·샘플러·Hires.fix를 반복 설정하지 않아도 됩니다. 인물의 외형, 체형, 의상, 분위기와 촬영 조건만 고르면 AutoSellerAI가 최종 프롬프트와 API payload를 자동 구성하고 전용 image-worker에서 생성합니다.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=12, show_spinner=False)
def _capabilities() -> dict[str, Any]:
    return StableDiffusionWebUIClient().capabilities().model_dump()


@st.cache_data(ttl=5, show_spinner=False)
def _queue_status() -> dict[str, Any]:
    return get_image_queue_status()


def _keys(mapping) -> list[str]:
    return list(mapping.keys())


def _ensure_state(key: str, value: Any) -> None:
    if key not in st.session_state:
        st.session_state[key] = value


def _choice(label: str, mapping, key: str, default: str, *, help: str | None = None):
    options = _keys(mapping)
    current = st.session_state.get(key, default)
    if current not in options:
        st.session_state[key] = default
    elif key not in st.session_state:
        st.session_state[key] = current
    return st.selectbox(label, options, key=key, help=help)


def _available_select(label: str, options: list[str], key: str, default: str, *, help: str | None = None):
    options = list(dict.fromkeys(x for x in options if x is not None))
    if not options:
        options = [default]
    current = st.session_state.get(key, default)
    if current not in options:
        st.session_state[key] = default if default in options else options[0]
    elif key not in st.session_state:
        st.session_state[key] = current
    return st.selectbox(label, options, key=key, help=help)


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


REQUEST_TO_STATE = {
    "preset": "sd_preset",
    "gender": "sd_gender",
    "age": "sd_age",
    "hair_style": "sd_hair",
    "hair_color": "sd_hair_color",
    "face_shape": "sd_face",
    "eye_style": "sd_eye",
    "nose_style": "sd_nose",
    "lip_style": "sd_lip",
    "skin_tone": "sd_skin",
    "expression": "sd_expression",
    "body_frame": "sd_body",
    "height_impression": "sd_height_impression",
    "shoulder": "sd_shoulder",
    "waist_hip": "sd_waist_hip",
    "chest_proportion": "sd_chest",
    "outfit": "sd_outfit",
    "outfit_color": "sd_outfit_color",
    "mood": "sd_mood",
    "personality": "sd_personality",
    "pose": "sd_pose",
    "shot": "sd_shot",
    "background": "sd_background",
    "lighting": "sd_lighting",
    "depth_of_field": "sd_dof",
    "camera": "sd_camera",
    "custom_positive": "sd_custom_positive",
    "custom_negative": "sd_custom_negative",
    "width": "sd_width",
    "height": "sd_height",
    "steps": "sd_steps",
    "cfg_scale": "sd_cfg",
    "sampler_name": "sd_sampler",
    "scheduler": "sd_scheduler",
    "seed": "sd_seed",
    "batch_size": "sd_batch",
    "enable_hr": "sd_hr",
    "hr_scale": "sd_hr_scale",
    "hr_upscaler": "sd_hr_upscaler",
    "hr_second_pass_steps": "sd_hr_steps",
    "denoising_strength": "sd_denoise",
    "adetailer_enabled": "sd_adetailer_enabled",
    "adetailer_model": "sd_adetailer_model",
    "adetailer_confidence": "sd_ad_confidence",
    "adetailer_denoising_strength": "sd_ad_denoise",
    "checkpoint": "sd_checkpoint",
}


def _queue_form_load(request_data: dict[str, Any]) -> None:
    st.session_state["_sd_pending_request"] = dict(request_data or {})


def _consume_pending_form_load() -> None:
    payload = st.session_state.pop("_sd_pending_request", None)
    if not isinstance(payload, dict):
        return
    try:
        validated = HumanImageRequest.model_validate(payload).model_dump()
    except Exception:
        validated = HumanImageRequest().model_dump()
    for field, key in REQUEST_TO_STATE.items():
        if field in validated:
            st.session_state[key] = validated[field]


def _resolved_seed(data: dict[str, Any]) -> int | None:
    info = data.get("response_info") or {}
    if not isinstance(info, dict):
        return None
    all_seeds = info.get("all_seeds")
    if isinstance(all_seeds, list) and all_seeds:
        try:
            return int(all_seeds[0])
        except Exception:
            pass
    try:
        value = info.get("seed")
        return int(value) if value is not None else None
    except Exception:
        return None


def _rerun_history(data: dict[str, Any], *, random_seed: bool) -> None:
    request_data = dict(data.get("request") or {})
    if random_seed:
        request_data["seed"] = -1
    elif int(request_data.get("seed", -1)) == -1:
        resolved = _resolved_seed(data)
        if resolved is not None:
            request_data["seed"] = resolved
    request = HumanImageRequest.model_validate(request_data)
    row = create_generation(request)
    st.session_state["sd_last_generation_id"] = row.id


_consume_pending_form_load()

caps = _capabilities()
queue_info = _queue_status()
webui_ok = bool(caps.get("ok"))
worker_ok = bool(queue_info.get("ok")) and int(queue_info.get("workers", 0)) > 0
runtime_ready = webui_ok and worker_ok

# -----------------------------------------------------------------------------
# Runtime control plane
# -----------------------------------------------------------------------------
st.markdown("### 🔌 생성 환경")
status_col, worker_col, model_col, ad_col, refresh_col = st.columns([1.1, 1.1, 2.4, 1.1, 1.1])
with status_col:
    st.metric("Stable Diffusion", "연결됨" if webui_ok else "연결 안 됨")
with worker_col:
    worker_label = f"{queue_info.get('workers', 0)}개"
    st.metric("Image Worker", worker_label if queue_info.get("ok") else "확인 실패", f"대기 {queue_info.get('queued', 0)}")
with model_col:
    st.caption("WebUI 주소 / 현재 체크포인트")
    st.code((caps.get("base_url") or "-") + "\n" + (caps.get("model") or "체크포인트 확인 불가"), language=None)
with ad_col:
    st.metric("ADetailer", "사용 가능" if caps.get("adetailer_available") else "미감지")
with refresh_col:
    st.write("")
    if st.button("🔄 상태 재확인", use_container_width=True):
        _capabilities.clear()
        _queue_status.clear()
        st.rerun()

if runtime_ready:
    st.markdown('<div class="sd-ready">✅ 생성 준비 완료 · WebUI와 전용 image-worker가 모두 정상입니다.</div>', unsafe_allow_html=True)
else:
    reasons = []
    if not webui_ok:
        reasons.append("Stable Diffusion WebUI API 연결 필요")
    if not worker_ok:
        reasons.append("image-worker 실행 필요")
    st.markdown(
        '<div class="sd-blocked">⚠️ 이미지 생성 전 확인: ' + " · ".join(reasons) + "</div>",
        unsafe_allow_html=True,
    )

with st.expander("🪟 webui-user.bat 설정 / 연결 문제 해결", expanded=not webui_ok):
    st.markdown(
        "AutoSellerAI가 Docker Compose에서 실행될 때는 Windows 호스트의 Stable Diffusion WebUI를 `host.docker.internal:7860`으로 호출합니다. "
        "따라서 WebUI는 API와 외부 인터페이스 수신이 켜져 있어야 합니다."
    )
    st.code("set COMMANDLINE_ARGS=--api --listen --port 7860", language="bat")
    st.caption("기존 COMMANDLINE_ARGS에 `--xformers`, `--medvram` 같은 옵션이 이미 있다면 지우지 말고 `--api --listen --port 7860`만 추가하세요.")
    c1, c2, c3 = st.columns(3)
    c1.code("http://127.0.0.1:7860", language=None)
    c2.code("http://127.0.0.1:7860/docs", language=None)
    c3.code("http://host.docker.internal:7860", language=None)
    if not webui_ok and caps.get("error"):
        st.error(caps["error"])
    if not queue_info.get("ok") and queue_info.get("error"):
        st.error(f"Redis/image-worker 상태 확인 실패: {queue_info['error']}")

# -----------------------------------------------------------------------------
# Quick preset / reset
# -----------------------------------------------------------------------------
st.markdown("### 🚀 빠른 시작")
quick1, quick2, quick3 = st.columns([3.6, 1.2, 1.2])
with quick1:
    preset = _available_select("목적 프리셋", list(PRESETS.keys()), "sd_preset", "실사 인플루언서")
with quick2:
    st.write("")
    st.write("")
    if st.button("⚡ 프리셋 적용", use_container_width=True):
        _apply_preset(preset)
        st.rerun()
with quick3:
    st.write("")
    st.write("")
    if st.button("↩️ 전체 기본값", use_container_width=True):
        _queue_form_load(HumanImageRequest().model_dump())
        st.rerun()

st.caption("프리셋은 촬영·해상도·품질 설정을 빠르게 맞춥니다. 얼굴, 체형, 의상은 아래 탭에서 원하는 캐릭터에 맞춰 별도로 조정할 수 있습니다.")

(tab_person, tab_body, tab_style, tab_scene, tab_advanced, tab_prompt, tab_history) = st.tabs(
    [
        "🙂 얼굴·헤어",
        "🧍 체형",
        "👗 의상·분위기",
        "📷 촬영",
        "⚙️ 고급 설정",
        "🧠 프롬프트·Payload",
        "🖼️ 생성 이력",
    ]
)

# -----------------------------------------------------------------------------
# Character appearance
# -----------------------------------------------------------------------------
with tab_person:
    st.caption("모든 연령 선택지는 성인으로 제한됩니다. 얼굴 특징은 세부 수치보다 실제 사진에서 자연스럽게 표현되는 범주로 구성했습니다.")
    c1, c2, c3 = st.columns(3)
    with c1:
        gender = _choice("성별", GENDER_MAP, "sd_gender", "여성")
        age = _choice("연령대", AGE_MAP, "sd_age", "20대 후반")
        skin_tone = _choice("피부톤", SKIN_TONE_MAP, "sd_skin", "내추럴")
        expression = _choice("표정", EXPRESSION_MAP, "sd_expression", "은은한 미소")
    with c2:
        hair_style = _choice("헤어스타일", HAIR_STYLE_MAP, "sd_hair", "긴 웨이브")
        hair_color = _choice("헤어 컬러", HAIR_COLOR_MAP, "sd_hair_color", "다크브라운")
        face_shape = _choice("얼굴형", FACE_SHAPE_MAP, "sd_face", "계란형")
    with c3:
        eye_style = _choice("눈매", EYE_STYLE_MAP, "sd_eye", "자연스러운 눈매")
        nose_style = _choice("코", NOSE_STYLE_MAP, "sd_nose", "자연스러운 코")
        lip_style = _choice("입술", LIP_STYLE_MAP, "sd_lip", "자연스러운 입술")

with tab_body:
    st.caption("과도한 수치형 신체 비율은 Stable Diffusion에서 손·관절·의상 왜곡을 늘리기 때문에, 실사 품질을 유지할 수 있는 인상 중심 옵션으로 제한했습니다.")
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
    st.info("성격은 이미지에서 직접 보이는 속성이 아니므로 표정, 자세, 시선, 전체 분위기로 변환해 프롬프트에 반영됩니다.")

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
    if shot == "전신":
        st.info("전신 구도에서는 다리·신발·발끝 크롭 방지 네거티브 프롬프트가 자동 추가됩니다.")
    if depth_of_field == "배경까지 선명":
        st.info("배경까지 선명 모드에서는 bokeh·shallow depth of field·blurred background를 자동 억제합니다.")

# -----------------------------------------------------------------------------
# Advanced WebUI controls
# -----------------------------------------------------------------------------
with tab_advanced:
    available_samplers = [x for x in caps.get("samplers", []) if x] or ["DPM++ 2M"]
    available_schedulers = [x for x in caps.get("schedulers", []) if x] or ["Karras"]
    available_upscalers = [x for x in caps.get("upscalers", []) if x] or ["R-ESRGAN 4x+"]
    checkpoints = [""] + [x for x in caps.get("checkpoints", []) if x]

    _ensure_state("sd_steps", int(PRESETS[preset]["steps"]))
    _ensure_state("sd_cfg", float(PRESETS[preset]["cfg_scale"]))
    _ensure_state("sd_width", int(PRESETS[preset]["width"]))
    _ensure_state("sd_height", int(PRESETS[preset]["height"]))
    _ensure_state("sd_seed", -1)
    _ensure_state("sd_batch", 1)
    _ensure_state("sd_hr", bool(PRESETS[preset]["hires"]))
    _ensure_state("sd_hr_scale", 1.5)
    _ensure_state("sd_hr_steps", 10)
    _ensure_state("sd_denoise", 0.32)
    _ensure_state("sd_adetailer_enabled", True)
    _ensure_state("sd_adetailer_model", "face_yolov8n.pt")
    _ensure_state("sd_ad_confidence", 0.30)
    _ensure_state("sd_ad_denoise", 0.32)
    _ensure_state("sd_custom_positive", "")
    _ensure_state("sd_custom_negative", "")

    st.markdown("#### 생성 엔진")
    c1, c2, c3 = st.columns(3)
    with c1:
        steps = st.slider("Steps", 10, 80, key="sd_steps", help="실사 기준 24~36 정도부터 시작하는 것을 권장합니다.")
        cfg_scale = st.slider("CFG Scale", 1.0, 20.0, step=0.5, key="sd_cfg", help="너무 높이면 프롬프트를 과하게 따라가며 피부와 색감이 인위적으로 변할 수 있습니다.")
        sampler_name = _available_select("Sampler", available_samplers, "sd_sampler", "DPM++ 2M")
        scheduler = _available_select("Scheduler", available_schedulers, "sd_scheduler", "Karras")
    with c2:
        width = st.number_input("기본 폭", min_value=384, max_value=1536, step=64, key="sd_width")
        height = st.number_input("기본 높이", min_value=384, max_value=2048, step=64, key="sd_height")
        seed = st.number_input("Seed (-1 = 랜덤)", min_value=-1, max_value=2147483647, step=1, key="sd_seed")
        batch_size = st.slider("한 번에 생성", 1, 4, key="sd_batch")
    with c3:
        checkpoint = _available_select(
            "체크포인트",
            checkpoints,
            "sd_checkpoint",
            "",
            help="비우면 현재 WebUI 체크포인트를 사용합니다. 선택해도 전역 모델을 바꾸지 않고 해당 요청에만 적용합니다.",
        )
        if checkpoint:
            st.caption("요청 단위 override_settings 사용 · 생성 후 기존 WebUI 체크포인트 복원")
        else:
            st.caption("현재 WebUI 체크포인트 사용")

    st.divider()
    st.markdown("#### Hires.fix")
    h1, h2, h3 = st.columns(3)
    with h1:
        enable_hr = st.checkbox("Hires.fix 사용", key="sd_hr")
        hr_scale = st.slider("Hires 배율", 1.0, 2.0, step=0.1, key="sd_hr_scale", disabled=not enable_hr)
    with h2:
        hr_upscaler = _available_select("업스케일러", available_upscalers, "sd_hr_upscaler", "R-ESRGAN 4x+")
        hr_second_pass_steps = st.slider("2차 Steps", 0, 40, key="sd_hr_steps", disabled=not enable_hr)
    with h3:
        denoising_strength = st.slider("Denoising", 0.0, 1.0, step=0.01, key="sd_denoise", disabled=not enable_hr)
        final_w = int(round(int(width) * float(hr_scale))) if enable_hr else int(width)
        final_h = int(round(int(height) * float(hr_scale))) if enable_hr else int(height)
        final_mp = (final_w * final_h) / 1_000_000
        st.metric("예상 최종 해상도", f"{final_w}×{final_h}", f"{final_mp:.1f} MP")
        if final_mp >= 4.0:
            st.warning("고해상도 설정입니다. GPU VRAM이 부족하면 Hires 배율 또는 기본 해상도를 낮추세요.")

    st.divider()
    st.markdown("#### ADetailer 얼굴 보정")
    a1, a2, a3, a4 = st.columns(4)
    with a1:
        adetailer_enabled = st.checkbox(
            "ADetailer 사용",
            key="sd_adetailer_enabled",
            disabled=not bool(caps.get("adetailer_available")),
        )
    with a2:
        adetailer_model = st.text_input("모델", key="sd_adetailer_model", disabled=not adetailer_enabled)
    with a3:
        adetailer_confidence = st.slider("Detection confidence", 0.05, 0.95, step=0.05, key="sd_ad_confidence", disabled=not adetailer_enabled)
    with a4:
        adetailer_denoising = st.slider("ADetailer denoising", 0.0, 1.0, step=0.01, key="sd_ad_denoise", disabled=not adetailer_enabled)
    if not caps.get("adetailer_available"):
        st.caption("WebUI의 `/scripts`에서 ADetailer가 감지되지 않았습니다. 확장 설치 전에는 얼굴 보정 payload를 자동으로 제외합니다.")

    with st.expander("✍️ 직접 프롬프트 추가", expanded=False):
        st.caption("구조화된 옵션으로 표현하기 어려운 소품·장소·연출만 추가하세요. 기본 실사·해부학 품질 프롬프트는 AutoSellerAI가 유지합니다.")
        custom_positive = st.text_area("추가 Positive Prompt", max_chars=1200, key="sd_custom_positive")
        custom_negative = st.text_area("추가 Negative Prompt", max_chars=1200, key="sd_custom_negative")

# Ensure values used outside advanced tab are initialized even on the first run.
for key, value in {
    "sd_steps": int(PRESETS[preset]["steps"]),
    "sd_cfg": float(PRESETS[preset]["cfg_scale"]),
    "sd_width": int(PRESETS[preset]["width"]),
    "sd_height": int(PRESETS[preset]["height"]),
    "sd_seed": -1,
    "sd_batch": 1,
    "sd_hr": bool(PRESETS[preset]["hires"]),
    "sd_hr_scale": 1.5,
    "sd_hr_upscaler": ([x for x in caps.get("upscalers", []) if x] or ["R-ESRGAN 4x+"])[0],
    "sd_hr_steps": 10,
    "sd_denoise": 0.32,
    "sd_adetailer_enabled": bool(caps.get("adetailer_available")),
    "sd_adetailer_model": "face_yolov8n.pt",
    "sd_ad_confidence": 0.30,
    "sd_ad_denoise": 0.32,
    "sd_checkpoint": "",
    "sd_sampler": ([x for x in caps.get("samplers", []) if x] or ["DPM++ 2M"])[0],
    "sd_scheduler": ([x for x in caps.get("schedulers", []) if x] or ["Karras"])[0],
    "sd_custom_positive": "",
    "sd_custom_negative": "",
}.items():
    _ensure_state(key, value)

# Tabs execute in a single script pass, so the variables above are available here.
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
    custom_positive=str(st.session_state.get("sd_custom_positive", "")),
    custom_negative=str(st.session_state.get("sd_custom_negative", "")),
    width=int(st.session_state["sd_width"]),
    height=int(st.session_state["sd_height"]),
    steps=int(st.session_state["sd_steps"]),
    cfg_scale=float(st.session_state["sd_cfg"]),
    sampler_name=str(st.session_state["sd_sampler"]),
    scheduler=str(st.session_state["sd_scheduler"]),
    seed=int(st.session_state["sd_seed"]),
    batch_size=int(st.session_state["sd_batch"]),
    enable_hr=bool(st.session_state["sd_hr"]),
    hr_scale=float(st.session_state["sd_hr_scale"]),
    hr_upscaler=str(st.session_state["sd_hr_upscaler"]),
    hr_second_pass_steps=int(st.session_state["sd_hr_steps"]),
    denoising_strength=float(st.session_state["sd_denoise"]),
    adetailer_enabled=bool(st.session_state["sd_adetailer_enabled"]),
    adetailer_model=str(st.session_state["sd_adetailer_model"]).strip() or "face_yolov8n.pt",
    adetailer_confidence=float(st.session_state["sd_ad_confidence"]),
    adetailer_denoising_strength=float(st.session_state["sd_ad_denoise"]),
    checkpoint=str(st.session_state["sd_checkpoint"]),
)

bundle = build_prompt(request)
selected_upscaler = choose_upscaler(request.hr_upscaler, caps.get("upscalers", [])) if request.enable_hr else None
payload_preview = build_txt2img_payload(
    request,
    adetailer_available=bool(caps.get("adetailer_available")),
    selected_upscaler=selected_upscaler,
)

# -----------------------------------------------------------------------------
# Prompt / payload inspection
# -----------------------------------------------------------------------------
with tab_prompt:
    st.markdown("#### 현재 설정 요약")
    st.markdown(
        f'<div class="sd-summary">{bundle.subject_summary}<br>🎭 {request.mood} · {request.personality} &nbsp; | &nbsp; 📷 {request.camera} · {request.lighting} · {request.depth_of_field}<br>⚙️ {request.sampler_name} / {request.scheduler} · Steps {request.steps} · CFG {request.cfg_scale} · Seed {request.seed}</div>',
        unsafe_allow_html=True,
    )
    if request.enable_hr and selected_upscaler and selected_upscaler != request.hr_upscaler:
        st.warning(f"선택한 업스케일러 `{request.hr_upscaler}` 대신 WebUI에서 감지된 `{selected_upscaler}`를 사용할 예정입니다.")
    if request.adetailer_enabled and not caps.get("adetailer_available"):
        st.warning("ADetailer를 요청했지만 WebUI에서 감지되지 않아 실제 API payload에서는 자동 제외됩니다.")

    p1, p2 = st.columns(2)
    with p1:
        st.text_area("Positive Prompt", value=bundle.positive, height=310, disabled=True)
        st.download_button(
            "Positive Prompt 저장",
            data=bundle.positive.encode("utf-8"),
            file_name="autoseller-positive-prompt.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with p2:
        st.text_area("Negative Prompt", value=bundle.negative, height=310, disabled=True)
        st.download_button(
            "Negative Prompt 저장",
            data=bundle.negative.encode("utf-8"),
            file_name="autoseller-negative-prompt.txt",
            mime="text/plain",
            use_container_width=True,
        )

    with st.expander("최종 /sdapi/v1/txt2img JSON Payload", expanded=False):
        st.code(json.dumps(payload_preview, ensure_ascii=False, indent=2), language="json")
        st.download_button(
            "Payload JSON 저장",
            data=json.dumps(payload_preview, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="autoseller-sd-txt2img-payload.json",
            mime="application/json",
            use_container_width=True,
        )

# -----------------------------------------------------------------------------
# Generation action
# -----------------------------------------------------------------------------
st.markdown("### ✨ 이미지 생성")
final_w = int(round(request.width * request.hr_scale)) if request.enable_hr else request.width
final_h = int(round(request.height * request.hr_scale)) if request.enable_hr else request.height
summary1, summary2, summary3, summary4 = st.columns(4)
summary1.metric("기본 해상도", f"{request.width}×{request.height}")
summary2.metric("예상 최종", f"{final_w}×{final_h}")
summary3.metric("생성 장수", f"{request.batch_size}장")
summary4.metric("Seed", "랜덤" if request.seed == -1 else str(request.seed))

if not runtime_ready:
    st.warning("WebUI와 image-worker가 모두 정상이어야 생성 버튼이 활성화됩니다. 위의 생성 환경에서 상태를 먼저 확인하세요.")

action1, action2, action3 = st.columns([3.2, 1.2, 1.2])
with action1:
    if st.button("✨ Stable Diffusion 이미지 생성", type="primary", use_container_width=True, disabled=not runtime_ready):
        try:
            row = create_generation(request)
            st.session_state["sd_last_generation_id"] = row.id
            _queue_status.clear()
            st.success(f"생성 작업 #{row.id}을 image-worker에 등록했습니다. 아래 실시간 진행 상태가 자동 갱신됩니다.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
with action2:
    if st.button("🎲 Seed만 랜덤", use_container_width=True):
        st.session_state["sd_seed"] = -1
        st.rerun()
with action3:
    if st.button("🔄 상태 새로고침", use_container_width=True):
        _capabilities.clear()
        _queue_status.clear()
        st.rerun()


recent_for_live = list_generations(12)
has_active = any(row.status in {"queued", "running"} for row in recent_for_live)
live_interval = "5s" if has_active else None


@st.fragment(run_every=live_interval)
def _render_live_generation() -> None:
    rows = list_generations(12)
    active = next((row for row in rows if row.status in {"running", "queued"}), None)
    latest = rows[0] if rows else None
    if not active:
        if latest and latest.status == "completed":
            st.success(f"최근 작업 #{latest.id} 완료 · 생성 이력 탭에서 결과를 확인할 수 있습니다.")
        elif latest and latest.status == "failed":
            st.error(f"최근 작업 #{latest.id} 실패 · 생성 이력에서 오류를 확인하세요.")
        else:
            st.caption("현재 실행 중인 이미지 생성 작업이 없습니다.")
        return

    data = generation_to_dict(active)
    q = get_image_queue_status()
    c1, c2, c3 = st.columns(3)
    c1.metric("현재 작업", f"#{active.id}")
    c2.metric("상태", "생성 중" if active.status == "running" else "대기 중")
    c3.metric("큐 대기", f"{q.get('queued', 0)}건")

    progress_value = 0.03 if active.status == "queued" else 0.10
    progress_label = "image-worker 할당 대기"
    if active.status == "running" and webui_ok:
        try:
            progress_data = StableDiffusionWebUIClient().progress()
            raw = float(progress_data.get("progress") or 0.0)
            progress_value = min(max(raw, 0.02), 1.0)
            eta = progress_data.get("eta_relative")
            progress_label = f"Stable Diffusion 생성 중 · {progress_value * 100:.0f}%"
            if eta is not None:
                try:
                    progress_label += f" · 예상 {float(eta):.0f}초"
                except Exception:
                    pass
        except Exception:
            progress_label = "Stable Diffusion 생성 중 · 진행률 API 확인 대기"
    st.progress(progress_value, text=progress_label)
    st.caption(data.get("subject_summary") or "")


_render_live_generation()

# -----------------------------------------------------------------------------
# History / gallery
# -----------------------------------------------------------------------------
with tab_history:
    st.markdown("#### 생성 결과와 재사용")
    f1, f2 = st.columns([2, 1])
    with f1:
        status_filter = st.selectbox("상태 필터", ["전체", "completed", "running", "queued", "failed"], key="sd_history_status")
    with f2:
        history_limit = st.selectbox("표시 개수", [12, 24, 60, 120], index=1, key="sd_history_limit")

    rows = list_generations(int(history_limit))
    if status_filter != "전체":
        rows = [row for row in rows if row.status == status_filter]

    if not rows:
        st.info("조건에 맞는 생성 이력이 없습니다.")

    for row in rows:
        data = generation_to_dict(row)
        status_icon = {"queued": "⏳", "running": "🎨", "completed": "✅", "failed": "❌"}.get(data["status"], "•")
        title = f"{status_icon} #{row.id} · {row.preset or '-'} · {row.subject_summary or '-'}"
        latest_completed = row.status == "completed" and row == rows[0]
        with st.expander(title, expanded=latest_completed):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("상태", row.status)
            c2.metric("생성 장수", len(data.get("image_paths") or []))
            c3.caption(f"요청: {row.created_at:%Y-%m-%d %H:%M:%S}")
            c4.caption(f"RQ: {row.rq_job_id or '-'}")

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

            request_data = data.get("request") or {}
            if request_data:
                r1, r2, r3 = st.columns(3)
                if r1.button("↩️ 설정 불러오기", key=f"load_sd_{row.id}", use_container_width=True):
                    _queue_form_load(request_data)
                    st.rerun()
                if r2.button("🔁 같은 Seed 재생성", key=f"same_sd_{row.id}", use_container_width=True, disabled=not runtime_ready):
                    try:
                        _rerun_history(data, random_seed=False)
                        _queue_status.clear()
                        st.success("같은 설정/Seed로 새 작업을 등록했습니다.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
                if r3.button("🎲 랜덤 Seed 재생성", key=f"random_sd_{row.id}", use_container_width=True, disabled=not runtime_ready):
                    try:
                        _rerun_history(data, random_seed=True)
                        _queue_status.clear()
                        st.success("같은 설정에 랜덤 Seed로 새 작업을 등록했습니다.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

            with st.expander("프롬프트 / 생성 메타데이터"):
                st.text_area("Positive Prompt", row.prompt, height=170, disabled=True, key=f"p_{row.id}")
                st.text_area("Negative Prompt", row.negative_prompt, height=135, disabled=True, key=f"n_{row.id}")
                info = data["response_info"]
                if info:
                    seed_value = _resolved_seed(data)
                    if seed_value is not None:
                        st.caption(f"실제 생성 Seed: {seed_value}")
                    st.json(info)
                if data["payload"]:
                    st.code(json.dumps(data["payload"], ensure_ascii=False, indent=2), language="json")
                metadata_export = {
                    "generation_id": row.id,
                    "request": data.get("request"),
                    "prompt": row.prompt,
                    "negative_prompt": row.negative_prompt,
                    "payload": data.get("payload"),
                    "response_info": data.get("response_info"),
                    "warnings": data.get("warnings"),
                }
                st.download_button(
                    "생성 메타데이터 JSON 저장",
                    data=json.dumps(metadata_export, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
                    file_name=f"sd-generation-{row.id}.json",
                    mime="application/json",
                    key=f"meta_sd_{row.id}",
                    use_container_width=True,
                )

st.markdown("---")
st.caption("AutoSellerAI · Stable Diffusion WebUI는 이미지 생성 엔진으로 사용하고, 설정·프롬프트·큐·결과 이력은 AutoSellerAI에서 통합 관리합니다.")
