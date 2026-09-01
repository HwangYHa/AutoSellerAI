"""Extended operator-supplied body-profile reference table.

This module preserves descriptive reference data separately from generation prompts.
It is not a medical/health recommendation and numeric values are not exact image
constraints. Clothing/bust notes are used only for operator reference and optional
fully clothed fashion composition guidance.
"""
from __future__ import annotations

from typing import Any, Mapping


BODY_PROFILE_EXTENDED_REFERENCE: Mapping[str, Mapping[str, Any]] = {
    "매우 슬림": {
        "overall_impression": "가녀리고 보호본능을 자극하는 매우 슬림한 인상",
        "height": "160~168cm", "weight": "43~46kg", "bmi": "16.5~17.5", "body_fat": "17~19% 느낌",
        "shoulder": "좁고 둥근 편", "ribcage": "매우 좁음 (petite)", "underbust": "65cm",
        "bust_volume": "아주 작음", "bust_projection": "거의 없음",
        "upper_lower_volume": "윗볼륨·아랫볼륨 모두 적음", "natural_shape": "평면에 가까운 완만한 형태",
        "waist_curve": "굴곡이 적고 일자형", "whr": "약 0.80", "leg_ratio": "약 45%",
        "muscle_abdomen": "근육량이 매우 적고 납작한 복부 인상", "clothed_impression": "여리여리한 핏, 오버핏에 유리",
        "sd_realism": "매우 높음 / 쉬움", "volume_class": "작은 볼륨", "bra_example": "70A",
        "ribcage_ratio": "흉곽 실루엣이 상체 볼륨보다 먼저 보이는 편", "side_projection": "미세한 경사각",
        "upper_chest_drape": "윗가슴 뼈대가 드러날 수 있고 처짐이 거의 없는 인상",
        "tshirt_fit": "옷 주름이 상체를 타고 비교적 곧게 내려가는 인상",
        "knit_fit": "여리여리한 어깨선이 강조되는 인상",
        "dress_fit": "깊이 파인 디자인은 상체 공간이 남아 보일 수 있음",
        "visual_emphasis_factors": "밝은 색 상의, 크롭 기장 등은 상대적으로 상체 볼륨이 커 보일 수 있음",
        "sd_phrase_reference": "flat chest, subtle bust curve, petite upper body",
    },
    "슬림": {
        "overall_impression": "깔끔하고 옷태가 잘 받는 슬림한 인상",
        "height": "162~168cm", "weight": "47~50kg", "bmi": "17.5~18.5", "body_fat": "20~22% 느낌",
        "shoulder": "직각에 가까운 보통 폭", "ribcage": "좁음 (narrow)", "underbust": "65~70cm",
        "bust_volume": "작음~보통", "bust_projection": "미세한 자연 곡선",
        "upper_lower_volume": "아랫볼륨 중심", "natural_shape": "미세한 원추형",
        "waist_curve": "부드러운 곡선", "whr": "약 0.75", "leg_ratio": "약 46%",
        "muscle_abdomen": "근육량이 적고 군살이 적은 평면 실루엣", "clothed_impression": "핏감이 가장 깔끔한 편",
        "sd_realism": "매우 높음 / 쉬움", "volume_class": "작은~중간 볼륨", "bra_example": "70B",
        "ribcage_ratio": "상체 볼륨과 흉곽이 비교적 일직선에 가깝게 떨어지는 인상", "side_projection": "얕은 포물선",
        "upper_chest_drape": "윗부분은 비교적 평평하고 아랫부분에 자연스러운 둥근 볼륨",
        "tshirt_fit": "작은 곡선을 만든 뒤 복부 쪽으로 자연스럽게 떨어지는 핏",
        "knit_fit": "깔끔하고 슬림한 인상",
        "dress_fit": "몸에 맞는 원피스가 단정하게 어울리는 인상",
        "visual_emphasis_factors": "몸에 붙는 골지 니트 등은 자연스러운 볼륨을 강조할 수 있음",
        "sd_phrase_reference": "natural small bust, gentle bust curve, modest upper-body contour",
    },
    "슬림 글래머": {
        "overall_impression": "허리가 얇고 굴곡 대비가 뚜렷한 슬림한 성인 체형",
        "height": "162~167cm", "weight": "49~53kg", "bmi": "18.5~19.5", "body_fat": "22~24% 느낌",
        "shoulder": "보통, 골반과 균형", "ribcage": "좁음 (narrow)", "underbust": "70cm",
        "bust_volume": "보통~큰 편", "bust_projection": "앞·옆으로 비교적 뚜렷한 자연 돌출",
        "upper_lower_volume": "윗볼륨이 봉긋한 편", "natural_shape": "둥근 형태를 유지하되 과장하지 않음",
        "waist_curve": "허리 대비가 매우 뚜렷함", "whr": "약 0.68~0.70", "leg_ratio": "약 46%",
        "muscle_abdomen": "보통, 부드러운 평면", "clothed_impression": "허리는 남고 상체는 타이트해질 수 있는 핏",
        "sd_realism": "중간 / 프롬프트 세밀함 요구", "volume_class": "중간 볼륨", "bra_example": "70C",
        "ribcage_ratio": "흉곽 바깥으로 상체 실루엣이 자연스럽게 보이는 편", "side_projection": "둥글게 이어지는 곡선",
        "upper_chest_drape": "윗부분부터 부드럽게 이어지는 물방울형 인상",
        "tshirt_fit": "상체 부위에서 원단이 살짝 떠 자연스러운 그림자가 생길 수 있음",
        "knit_fit": "허리 대비와 여성스러운 선이 비교적 뚜렷하게 보임",
        "dress_fit": "허리선이 잡힌 원피스에서 상·하체 대비가 잘 드러남",
        "visual_emphasis_factors": "허리선을 조이는 의상은 체형 대비를 더 크게 보이게 할 수 있음",
        "sd_phrase_reference": "moderate bust volume, natural projection, balanced bust-to-frame, narrow waist contrast",
    },
    "균형형": {
        "overall_impression": "단정하고 전체 비율이 좋은 균형형 성인 체형",
        "height": "164~170cm", "weight": "51~55kg", "bmi": "19.0~20.5", "body_fat": "23~25% 느낌",
        "shoulder": "보통~약간 넓음", "ribcage": "보통 (moderate)", "underbust": "70~75cm",
        "bust_volume": "보통", "bust_projection": "자연스럽고 완만한 곡선",
        "upper_lower_volume": "아랫볼륨 중심의 자연스러운 분포", "natural_shape": "자연스러운 물방울형 인상",
        "waist_curve": "부드럽고 자연스러운 굴곡", "whr": "약 0.73~0.75", "leg_ratio": "약 47%",
        "muscle_abdomen": "보통, 자연스러운 라인", "clothed_impression": "기성복이 비교적 안정적으로 잘 맞는 체형",
        "sd_realism": "매우 높음 / 가장 쉬움", "volume_class": "중간~큰 볼륨 참고", "bra_example": "70D",
        "ribcage_ratio": "흉곽 대비 자연스럽고 명확한 상체 볼륨감", "side_projection": "무게감이 과하지 않은 자연 곡선",
        "upper_chest_drape": "윗부분 볼륨이 있으면서 미세한 자연 중력감",
        "tshirt_fit": "프린팅이나 원단이 상체 곡선을 따라 입체적으로 보일 수 있음",
        "knit_fit": "상체가 부각되며 균형 잡힌 볼륨감이 보이는 인상",
        "dress_fit": "랩·허리선 원피스에서 자연스러운 상체·허리 곡선이 드러남",
        "visual_emphasis_factors": "U/V 형태의 넥라인은 상체 곡선을 상대적으로 강조할 수 있음",
        "sd_phrase_reference": "prominent but balanced upper-body volume, curved torso, realistic clothing drape",
    },
    "볼륨형": {
        "overall_impression": "굴곡이 크고 부드럽고 성숙한 인상의 성인 체형",
        "height": "160~166cm", "weight": "54~59kg", "bmi": "20.5~22.0", "body_fat": "26~29% 느낌",
        "shoulder": "보통", "ribcage": "넓은 편 (broad)", "underbust": "75~80cm",
        "bust_volume": "큼", "bust_projection": "중력과 원단 드레이프가 느껴지는 자연 곡선",
        "upper_lower_volume": "윗·아랫볼륨 모두 큰 편", "natural_shape": "약간의 자연스러운 중력감을 가진 종형 인상",
        "waist_curve": "둥글고 풍만한 굴곡", "whr": "약 0.70~0.72", "leg_ratio": "약 45%",
        "muscle_abdomen": "보통, 약간 부드러운 복부 라인", "clothed_impression": "상의가 짧게 들리거나 전체 상체가 부해 보일 수 있음",
        "sd_realism": "중간 / 과장되기 쉬움", "volume_class": "큰 볼륨", "bra_example": "70E",
        "ribcage_ratio": "흉곽을 넓게 덮는 강한 상체 존재감", "side_projection": "명확하지만 현실적인 단차와 곡선",
        "upper_chest_drape": "윗부분 볼륨과 자연스러운 중력감이 함께 나타나는 인상",
        "tshirt_fit": "원단 전체가 상체 곡선을 따라 부해 보일 수 있음",
        "knit_fit": "상체가 지나치게 강조될 수 있어 프롬프트에서 과장 억제 필요",
        "dress_fit": "좁은 넥라인은 상체가 답답해 보일 수 있는 인상",
        "visual_emphasis_factors": "허리 대비가 커질수록 상체 볼륨이 더 크게 보일 수 있음",
        "sd_phrase_reference": "full natural upper-body curve, realistic gravity, fuller curvy torso, non-exaggerated anatomy",
    },
    "운동형": {
        "overall_impression": "탄탄하고 건강한 운동형 성인 체형",
        "height": "163~170cm", "weight": "52~57kg", "bmi": "19.5~21.0", "body_fat": "18~20% 느낌",
        "shoulder": "직각에 가깝고 약간 넓은 어깨", "ribcage": "보통~넓음 (toned)", "underbust": "70~75cm",
        "bust_volume": "보통, 근육이 받쳐주는 운동형 상체", "bust_projection": "탄탄하게 위로 받쳐진 자연 곡선",
        "upper_lower_volume": "윗부분이 단단한 운동형 인상", "natural_shape": "퍼지지 않고 탄탄하게 모인 상체 실루엣",
        "waist_curve": "선명한 코어와 자연스러운 허리선", "whr": "약 0.73", "leg_ratio": "약 46%",
        "muscle_abdomen": "높은 근육량, 탄탄한 코어와 자연스러운 복부 선", "clothed_impression": "크롭·레깅스·애슬레저 핏에 유리",
        "sd_realism": "높음 / 근육 묘사 과장 주의", "volume_class": "운동형 보통 볼륨", "bra_example": "",
        "ribcage_ratio": "운동형 흉곽과 상체 볼륨이 균형을 이루는 인상", "side_projection": "근육 지지감이 있는 탄탄한 곡선",
        "upper_chest_drape": "윗부분이 단단하고 중력감이 상대적으로 적은 인상",
        "tshirt_fit": "어깨·상체·코어의 탄탄한 라인이 원단에 드러날 수 있음",
        "knit_fit": "근육을 과장하지 않는 선에서 탄탄한 실루엣이 보이는 인상",
        "dress_fit": "허리선과 어깨선이 구조적으로 또렷한 핏",
        "visual_emphasis_factors": "크롭·스포티 의상은 코어와 어깨선을 강조할 수 있음",
        "sd_phrase_reference": "fit athletic feminine silhouette, toned shoulders, defined core, realistic moderate muscle definition",
    },
}


def extended_reference(profile: str) -> dict[str, Any]:
    return dict(BODY_PROFILE_EXTENDED_REFERENCE.get(profile, {}))


__all__ = ["BODY_PROFILE_EXTENDED_REFERENCE", "extended_reference"]
