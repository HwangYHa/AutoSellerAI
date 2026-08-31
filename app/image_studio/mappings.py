"""Korean UI labels -> model-agnostic Stable Diffusion prompt fragments.

The mapping layer deliberately uses descriptive photographic language instead of
checkpoint-specific trigger words.  This keeps the same AutoSellerAI UI usable
across SD 1.5, SDXL and compatible photoreal checkpoints.

Design rules
------------
* Adult-only age choices.
* Body controls describe visual proportions/silhouette, not guaranteed metric
  measurements.  Text-to-image models cannot reliably obey exact centimetres or
  three-size values.
* Prompt fragments stay short and composable.  Strong A1111 emphasis weights are
  left to custom/advanced prompts instead of being hard-coded into every option.
* Clothing options remain suitable for ordinary fashion / commerce / lifestyle
  image generation.
"""
from __future__ import annotations

from typing import Mapping


GENDER_MAP: Mapping[str, str] = {
    "여성": "adult Korean woman",
    "남성": "adult Korean man",
}

AGE_MAP: Mapping[str, str] = {
    "20대 초반": "adult in their early twenties",
    "20대 중반": "adult in their mid twenties",
    "20대 후반": "adult in their late twenties",
    "30대 초반": "adult in their early thirties",
    "30대 중반": "adult in their mid thirties",
    "30대 후반": "adult in their late thirties",
    "40대 초반": "adult in their early forties",
    "40대 후반": "adult in their late forties",
    "50대": "adult in their fifties",
    "60대": "adult in their sixties",
}

HAIR_STYLE_MAP: Mapping[str, str] = {
    "자연스러운 단발": "natural short bob haircut",
    "턱선 단발": "chin-length bob haircut",
    "귀밑 단발": "short ear-length bob haircut",
    "C컬 단발": "short bob with soft inward C-curls",
    "S컬 단발": "short bob with gentle S-waves",
    "중단발": "medium-length lob haircut",
    "중단발 C컬": "medium lob with soft inward curls",
    "중단발 웨이브": "medium lob with relaxed waves",
    "긴 생머리": "long straight hair",
    "긴 웨이브": "long soft wavy hair",
    "굵은 웨이브": "long hair with large loose waves",
    "잔잔한 웨이브": "long hair with subtle fine waves",
    "레이어드컷": "soft layered haircut",
    "긴 레이어드컷": "long layered haircut with natural movement",
    "허쉬컷": "soft textured hush cut",
    "샤기컷": "lightly textured shag haircut",
    "포니테일": "neat natural ponytail",
    "하이 포니테일": "clean high ponytail",
    "로우 포니테일": "soft low ponytail",
    "반묶음": "natural half-up hairstyle",
    "로우번": "clean low bun hairstyle",
    "하이번": "tidy high bun hairstyle",
    "땋은 머리": "neat single braid hairstyle",
    "양갈래 땋기": "two neat adult braided sections",
    "숏컷": "clean short haircut",
    "픽시컷": "soft modern pixie haircut",
    "가르마 헤어": "neat side-parted hair",
    "센터파트": "clean center-parted hairstyle",
    "쉼표 머리": "soft comma hairstyle",
    "댄디컷": "clean modern dandy haircut",
}

HAIR_COLOR_MAP: Mapping[str, str] = {
    "검정": "natural black hair",
    "소프트 블랙": "soft natural black hair",
    "다크브라운": "dark brown hair",
    "초코브라운": "chocolate brown hair",
    "브라운": "natural brown hair",
    "밀크브라운": "soft milk brown hair",
    "애쉬브라운": "soft ash brown hair",
    "카키브라운": "subtle khaki brown hair",
    "밝은 브라운": "light warm brown hair",
    "오렌지브라운": "muted orange-brown hair",
    "레드브라운": "subtle red-brown hair",
    "와인브라운": "deep wine-brown hair",
    "애쉬그레이": "muted ash gray hair",
    "다크그레이": "dark charcoal gray hair",
    "블론드": "natural warm blonde hair",
    "플래티넘 블론드": "cool platinum blonde hair",
}

FACE_SHAPE_MAP: Mapping[str, str] = {
    "계란형": "balanced oval face",
    "갸름한형": "slender softly tapered face",
    "둥근형": "soft round face",
    "각진형": "subtly defined angular face",
    "하트형": "soft heart-shaped face",
    "긴 얼굴형": "gently elongated face",
    "작고 균형형": "small balanced face proportions",
    "부드러운 사각형": "soft square face with rounded jaw corners",
    "V라인형": "softly tapered V-shaped jawline",
    "광대 균형형": "balanced cheekbone structure",
}

EYE_STYLE_MAP: Mapping[str, str] = {
    "자연스러운 눈매": "natural balanced eyes",
    "또렷한 눈매": "clear defined eyes",
    "부드러운 눈매": "soft gentle eyes",
    "고양이상": "slightly upturned cat-like eyes",
    "강아지상": "warm softly rounded eyes",
    "긴 눈매": "gently elongated eye shape",
    "둥근 눈매": "naturally rounded eyes",
    "차분한 눈매": "calm relaxed eyes",
    "시크한 눈매": "subtly sharp sophisticated eyes",
    "웃는 눈매": "warm smiling eyes",
    "쌍꺼풀 또렷": "naturally defined double eyelids",
    "속쌍꺼풀": "subtle inner double eyelids",
    "무쌍 느낌": "natural monolid appearance",
    "눈꼬리 살짝 아래": "slightly downturned gentle eyes",
}

NOSE_STYLE_MAP: Mapping[str, str] = {
    "자연스러운 코": "natural proportional nose",
    "오똑한 코": "clean defined nose bridge",
    "부드러운 코선": "soft natural nose profile",
    "작고 단정한 코": "small neat proportional nose",
    "직선형 콧대": "straight natural nose bridge",
    "살짝 높은 콧대": "moderately elevated natural nose bridge",
    "둥근 코끝": "soft rounded natural nose tip",
    "날렵한 코끝": "subtly refined natural nose tip",
}

LIP_STYLE_MAP: Mapping[str, str] = {
    "자연스러운 입술": "natural proportional lips",
    "도톰한 입술": "soft naturally full lips",
    "얇고 정돈된 입술": "neat subtly thin lips",
    "윗입술 얇고 아랫입술 도톰": "subtle upper lip with naturally fuller lower lip",
    "입꼬리 살짝 올라감": "subtly upturned lip corners",
    "작고 단정한 입술": "small neat natural lips",
    "선명한 입술선": "clean naturally defined lip contour",
    "부드러운 입술선": "soft natural lip contour",
}

SKIN_TONE_MAP: Mapping[str, str] = {
    "밝은 뉴트럴": "light neutral Korean skin tone",
    "밝은 쿨": "light cool-neutral Korean skin tone",
    "밝은 웜": "light warm Korean skin tone",
    "내추럴": "natural Korean skin tone",
    "뉴트럴 베이지": "neutral beige Korean skin tone",
    "웜 베이지": "warm beige Korean skin tone",
    "건강한 웜": "warm healthy Korean skin tone",
    "살짝 태닝": "lightly sun-kissed Korean skin tone",
    "건강한 태닝": "naturally sun-kissed healthy skin tone",
    "맑은 내추럴": "clear natural skin tone with realistic texture",
}

EXPRESSION_MAP: Mapping[str, str] = {
    "무표정/차분": "calm relaxed expression",
    "은은한 미소": "subtle natural smile",
    "밝은 미소": "bright friendly smile",
    "활짝 웃기": "open cheerful natural smile",
    "자신감 있는 표정": "confident composed expression",
    "장난스러운 표정": "playful friendly expression",
    "살짝 수줍은 미소": "subtle shy natural smile",
    "편안한 표정": "comfortable relaxed facial expression",
    "지적인 표정": "calm thoughtful intelligent expression",
    "시크한 표정": "cool restrained sophisticated expression",
    "놀란 듯한 자연스러운 표정": "mild naturally surprised expression",
    "호기심 있는 표정": "curious attentive expression",
    "따뜻하게 웃기": "warm affectionate natural smile",
    "카메라 밖을 보며 미소": "soft smile while looking slightly off camera",
    "입 다문 미소": "gentle closed-mouth smile",
    "자연스러운 대화 표정": "natural conversational expression",
}

BODY_FRAME_MAP: Mapping[str, str] = {
    "매우 슬림": "very slim naturally proportioned adult physique",
    "아담한 체형": "petite naturally proportioned adult body",
    "슬림": "slim naturally proportioned adult body",
    "슬림 균형형": "slim balanced adult body proportions",
    "슬림 곡선형": "slim adult silhouette with gentle natural curves",
    "균형형": "balanced natural adult body proportions",
    "자연스러운 볼륨형": "naturally curvy balanced adult silhouette",
    "부드러운 곡선형": "softly curved realistic adult silhouette",
    "탄탄한 체형": "toned healthy adult physique",
    "애슬레틱": "fit athletic adult physique with natural proportions",
    "러너형": "lean endurance-athlete adult physique",
    "필라테스형": "lean toned adult physique with balanced posture",
    "근육이 살짝 보이는 체형": "subtly muscular toned adult physique",
    "넓은 골격 균형형": "broader framed balanced adult physique",
    "마른 근육형": "lean muscular adult physique",
    "건강한 보통 체형": "healthy average adult physique with natural proportions",
}

HEIGHT_MAP: Mapping[str, str] = {
    "매우 아담한 인상": "distinctly petite height impression",
    "아담한 인상": "petite height impression",
    "평균적인 인상": "average height impression",
    "큰 키 인상": "tall elegant height impression",
    "매우 큰 키 인상": "distinctly tall fashion-model height impression",
}

SHOULDER_MAP: Mapping[str, str] = {
    "좁고 부드러운 어깨": "soft narrow shoulder line",
    "살짝 좁은 어깨": "slightly narrow natural shoulders",
    "균형 잡힌 어깨": "balanced shoulder proportions",
    "곧은 어깨": "straight clean shoulder line",
    "곧고 탄탄한 어깨": "straight toned shoulder line",
    "살짝 넓은 어깨": "slightly broad balanced shoulders",
    "운동형 넓은 어깨": "athletic broad shoulder line with realistic proportions",
}

WAIST_HIP_MAP: Mapping[str, str] = {
    "일자형": "straight natural waist and hip silhouette",
    "슬림 일자형": "slim straight waist and hip silhouette",
    "균형형": "balanced natural waist and hip proportions",
    "허리 살짝 강조": "subtly defined natural waistline",
    "곡선형": "gently curved natural waist and hip silhouette",
    "모래시계형 자연곡선": "balanced natural hourglass silhouette",
    "골반 살짝 넓음": "slightly wider natural hip proportions",
    "운동형 골반라인": "toned athletic waist and hip line",
    "부드러운 하체 곡선": "soft realistic lower-body curves",
}

CHEST_PROPORTION_MAP: Mapping[str, str] = {
    "슬림한 상체": "slender upper-body proportions",
    "자연스러운 비율": "natural proportional torso",
    "균형 잡힌 상체": "balanced realistic upper-body proportions",
    "자연스러운 볼륨감": "naturally fuller but realistic upper-body proportions",
    "운동형 상체": "toned athletic upper-body proportions",
    "넓은 흉곽 균형형": "broader ribcage with balanced realistic torso proportions",
    "상체 길어 보임": "slightly elongated balanced torso proportions",
}

OUTFIT_MAP: Mapping[str, str] = {
    "데일리 캐주얼": "wearing a tasteful everyday casual outfit",
    "티셔츠 + 데님": "wearing a clean fitted T-shirt with classic denim jeans",
    "셔츠 + 데님": "wearing a crisp casual shirt with denim jeans",
    "블라우스 + 데님": "wearing a refined blouse with clean denim jeans",
    "캐주얼 니트": "wearing a soft knit top with clean casual bottoms",
    "니트 + 슬랙스": "wearing a refined knit top with tailored slacks",
    "니트 + 데님": "wearing a soft knit top with classic denim jeans",
    "가디건 룩": "wearing a tasteful cardigan layered over a simple inner top",
    "오피스룩": "wearing a polished office blouse and tailored slacks",
    "포멀 셔츠룩": "wearing a crisp formal shirt with tailored trousers",
    "미니멀 셋업": "wearing a minimalist coordinated outfit",
    "세미정장": "wearing refined modern business-casual tailoring",
    "클래식 수트": "wearing a well-tailored classic suit",
    "세련된 원피스": "wearing an elegant contemporary dress",
    "미디 원피스": "wearing a tasteful modern midi dress",
    "셔츠 원피스": "wearing a clean modern shirt dress",
    "니트 원피스": "wearing a refined knit dress",
    "플레어 원피스": "wearing an elegant softly flared dress",
    "롱 스커트 룩": "wearing a tasteful long skirt with a coordinated top",
    "미디 스커트 룩": "wearing a refined midi skirt with a coordinated top",
    "와이드 팬츠 룩": "wearing modern wide-leg trousers with a clean top",
    "슬랙스 룩": "wearing tailored slacks with a polished casual top",
    "스트릿 캐주얼": "wearing modern tasteful streetwear",
    "오버핏 스트릿": "wearing clean oversized streetwear with balanced styling",
    "미니멀 스트릿": "wearing understated minimalist streetwear",
    "스포티 캐주얼": "wearing clean modern athleisure",
    "러닝웨어": "wearing tasteful modern running apparel",
    "테니스 스타일": "wearing clean tennis-inspired sportswear",
    "골프웨어": "wearing refined modern golf apparel",
    "여름 데일리룩": "wearing a light tasteful summer outfit",
    "린넨 여름룩": "wearing breathable refined linen summer clothing",
    "겨울 데일리룩": "wearing layered tasteful winter casual clothing",
    "코트 룩": "wearing a refined long coat over coordinated clothing",
    "트렌치코트 룩": "wearing a classic modern trench coat outfit",
    "패딩 캐주얼": "wearing clean practical padded outerwear with casual styling",
    "남성 미니멀룩": "wearing a clean minimalist menswear outfit",
    "남성 오피스룩": "wearing a refined shirt and tailored trousers",
    "남성 댄디룩": "wearing polished modern dandy-style menswear",
}

OUTFIT_COLOR_MAP: Mapping[str, str] = {
    "자동/자연스럽게": "harmonious neutral clothing colors",
    "올블랙": "monochrome black outfit palette",
    "블랙": "predominantly black outfit",
    "오프화이트": "soft off-white outfit palette",
    "화이트": "predominantly white outfit",
    "아이보리": "soft ivory color palette",
    "아이보리/베이지": "ivory and beige color palette",
    "베이지": "clean beige color palette",
    "브라운": "warm brown color palette",
    "카멜": "warm camel color palette",
    "그레이": "clean gray color palette",
    "차콜": "deep charcoal color palette",
    "네이비": "refined navy color palette",
    "블루": "clean balanced blue color palette",
    "연청": "light denim blue color palette",
    "카키": "muted khaki color palette",
    "올리브": "muted olive color palette",
    "버건디": "deep burgundy color palette",
    "파스텔": "soft tasteful pastel color palette",
    "모노톤": "balanced monochrome neutral palette",
}

MOOD_MAP: Mapping[str, str] = {
    "자연스러움": "natural effortless atmosphere",
    "청순/맑음": "clean fresh gentle atmosphere",
    "세련됨": "refined stylish atmosphere",
    "도회적": "urban sophisticated atmosphere",
    "귀여움": "bright charming approachable atmosphere",
    "럭셔리": "understated luxurious elegant atmosphere",
    "시크": "cool chic composed atmosphere",
    "따뜻함": "warm cozy approachable atmosphere",
    "미니멀": "clean minimalist understated atmosphere",
    "감성적": "soft emotional lifestyle atmosphere",
    "활기찬": "bright lively energetic atmosphere",
    "편안한": "relaxed comfortable everyday atmosphere",
    "프로페셔널": "polished professional atmosphere",
    "지적인": "calm intelligent refined atmosphere",
    "로맨틱": "soft tasteful romantic atmosphere",
    "빈티지": "subtle tasteful vintage atmosphere",
    "모던": "clean modern contemporary atmosphere",
    "프리미엄": "premium editorial lifestyle atmosphere",
    "트렌디": "current fashion-forward social atmosphere",
    "건강한": "healthy fresh active atmosphere",
}

PERSONALITY_MAP: Mapping[str, str] = {
    "밝고 친근함": "friendly open body language and warm presence",
    "차분하고 지적": "calm intelligent composed presence",
    "자신감 있음": "confident poised body language",
    "사랑스럽고 부드러움": "gentle approachable body language",
    "활발하고 에너지 있음": "energetic upbeat natural body language",
    "시크하고 절제됨": "restrained chic confident presence",
    "다정하고 편안함": "kind relaxed approachable presence",
    "프로페셔널함": "professional assured composed presence",
    "호기심 많고 생기있음": "curious lively attentive presence",
    "차분하고 따뜻함": "calm warm reassuring presence",
    "독립적이고 당당함": "independent self-assured presence",
    "유쾌하고 장난기 있음": "cheerful playful natural presence",
    "섬세하고 감성적": "sensitive thoughtful gentle presence",
    "운동 좋아하는 활기참": "active healthy energetic presence",
    "도도하고 세련됨": "reserved polished sophisticated presence",
    "편안한 친구 느낌": "easygoing familiar friendly presence",
}

POSE_MAP: Mapping[str, str] = {
    "자연스럽게 서기": "natural relaxed standing pose",
    "카메라 바라보기": "looking naturally toward the camera",
    "살짝 측면": "subtle three-quarter body angle",
    "완전 측면": "clean natural side-profile body angle",
    "걷는 순간": "natural candid walking moment",
    "천천히 걷기": "slow relaxed walking pose",
    "의자에 앉기": "natural seated pose with relaxed posture",
    "소파에 편하게 앉기": "relaxed seated pose on a sofa with natural posture",
    "테이블에 앉기": "natural seated pose at a table",
    "벽에 살짝 기대기": "casually leaning against a wall",
    "한 손 주머니": "one hand naturally resting in a pocket",
    "팔짱 가볍게": "light relaxed crossed-arm pose",
    "손을 자연스럽게 모으기": "hands gently and naturally held together",
    "머리카락 정리하기": "naturally adjusting hair with one hand",
    "커피잔 들기": "naturally holding a coffee cup with anatomically correct hands",
    "스마트폰 보기": "naturally looking at a smartphone held with realistic hands",
    "스마트폰 들고 카메라 보기": "holding a smartphone naturally while looking toward the camera",
    "상품을 들고 있기": "naturally holding the featured product with anatomically correct hands",
    "쇼핑백 들기": "naturally holding a shopping bag with realistic hands",
    "창밖 바라보기": "naturally looking out a nearby window",
}

SHOT_MAP: Mapping[str, str] = {
    "얼굴 초근접": "tight beauty close-up, face clearly framed without cropping key facial features",
    "얼굴 클로즈업": "close-up portrait, face and shoulders clearly framed",
    "가슴 위": "chest-up portrait with complete head and shoulders visible",
    "상반신": "upper-body portrait, torso clearly visible",
    "허리 위": "waist-up portrait with natural arm framing",
    "허벅지 위": "three-quarter portrait framed above the knees",
    "무릎 위": "knee-up portrait with balanced fashion composition",
    "전신": "full-body fashion photograph, entire body and feet visible",
    "전신 + 여백": "full-body photograph with comfortable environmental space around the subject",
    "환경 인물": "environmental portrait showing the person and surrounding location clearly",
}

BACKGROUND_MAP: Mapping[str, str] = {
    "화이트 스튜디오": "clean white photography studio background",
    "그레이 스튜디오": "clean neutral gray photography studio background",
    "베이지 스튜디오": "warm minimal beige photography studio background",
    "컬러 페이퍼 스튜디오": "clean contemporary seamless paper studio backdrop",
    "감성 카페": "tasteful contemporary cafe interior",
    "대형 카페": "spacious modern cafe interior with clean architectural details",
    "베이커리 카페": "warm contemporary bakery cafe interior",
    "미니멀 갤러리": "minimal modern art gallery interior",
    "미술관 로비": "refined contemporary museum lobby",
    "모던 오피스": "modern refined office interior",
    "회의실": "clean modern conference room interior",
    "코워킹 스페이스": "bright modern coworking-space interior",
    "도심 스트릿": "clean contemporary Korean urban street",
    "골목 스트릿": "tasteful quiet Korean urban side street",
    "상업지구": "modern Korean commercial district streetscape",
    "쇼핑몰 내부": "clean upscale shopping mall interior",
    "편안한 집": "tasteful cozy modern apartment interior",
    "거실": "clean modern apartment living room",
    "주방": "bright contemporary home kitchen",
    "침실": "tasteful tidy modern bedroom interior",
    "호텔 라운지": "understated upscale hotel lounge",
    "호텔 로비": "modern upscale hotel lobby",
    "루프탑": "clean contemporary rooftop terrace",
    "한강/공원": "clean urban riverside park setting",
    "도심 공원": "green modern city park setting",
    "해변": "bright natural beach setting",
    "바닷가 산책로": "clean coastal promenade setting",
    "야간 도심": "modern Korean city street at night with realistic ambient lights",
}

LIGHTING_MAP: Mapping[str, str] = {
    "부드러운 자연광": "soft diffused natural daylight, realistic skin illumination",
    "창가 자연광": "soft window daylight with realistic directional shadows",
    "정면 창가광": "soft frontal window daylight with natural facial illumination",
    "측면 창가광": "soft side window daylight with dimensional realistic shadows",
    "밝은 스튜디오": "clean softbox studio lighting with balanced exposure",
    "뷰티 스튜디오": "large soft beauty lighting with gentle realistic facial shadows",
    "패션 스튜디오": "controlled fashion studio lighting with crisp realistic fabric detail",
    "골든아워": "warm golden-hour natural light with controlled highlights",
    "해질녘": "soft sunset ambient light with natural warm tones",
    "흐린날 소프트광": "soft overcast daylight with even skin tones",
    "맑은 낮": "clear balanced daytime sunlight with controlled contrast",
    "그늘 자연광": "soft open-shade daylight with even realistic skin tones",
    "시네마틱": "controlled cinematic key light with realistic fill light",
    "저녁 실내 웜톤": "warm indoor evening light with realistic practical illumination",
    "야간 네온": "controlled urban neon ambient lighting with realistic skin exposure",
    "플래시 스냅": "tasteful direct-camera flash lifestyle photography with controlled highlights",
}

DOF_MAP: Mapping[str, str] = {
    "배경까지 선명": "deep depth of field, subject and background both clearly resolved",
    "넓은 심도": "wide depth of field with clearly readable environment",
    "자연스러운 심도": "natural moderate depth of field, subject clearly focused",
    "살짝 분리": "subtle subject separation while keeping the background recognizable",
    "인물 중심": "gentle subject separation with a recognizable background",
    "강한 인물 분리": "pronounced subject separation with soft but identifiable background shapes",
}

CAMERA_MAP: Mapping[str, str] = {
    "자연스러운 스마트폰 사진": "high-end smartphone lifestyle photography, natural perspective",
    "스마트폰 인물모드 느낌": "premium smartphone portrait photography with realistic computational rendering",
    "24mm 넓은 환경컷": "24mm environmental photography with controlled wide-angle distortion",
    "28mm 라이프스타일": "28mm lifestyle photography with natural environmental context",
    "35mm 환경 인물": "35mm environmental portrait photography, natural perspective",
    "40mm 다큐 느낌": "40mm documentary lifestyle photography with natural perspective",
    "50mm 자연 인물": "50mm portrait photography, realistic perspective",
    "58mm 클래식 인물": "58mm classic portrait photography with natural facial perspective",
    "70mm 패션": "70mm fashion portrait photography with compressed natural perspective",
    "85mm 패션 인물": "85mm fashion portrait photography, flattering realistic perspective",
    "105mm 뷰티": "105mm beauty portrait photography with clean flattering perspective",
    "광고 카탈로그": "commercial catalog photography with neutral accurate perspective and crisp detail",
}

PRESETS = {
    "실사 인플루언서": {
        "shot": "상반신",
        "background": "감성 카페",
        "lighting": "창가 자연광",
        "camera": "50mm 자연 인물",
        "dof": "자연스러운 심도",
        "steps": 30,
        "cfg_scale": 6.0,
        "width": 768,
        "height": 1152,
        "hires": True,
    },
    "쇼핑몰 모델컷": {
        "shot": "전신",
        "background": "화이트 스튜디오",
        "lighting": "밝은 스튜디오",
        "camera": "광고 카탈로그",
        "dof": "배경까지 선명",
        "steps": 32,
        "cfg_scale": 6.0,
        "width": 768,
        "height": 1152,
        "hires": True,
    },
    "Threads/SNS 세로컷": {
        "shot": "허벅지 위",
        "background": "도심 스트릿",
        "lighting": "부드러운 자연광",
        "camera": "35mm 환경 인물",
        "dof": "자연스러운 심도",
        "steps": 28,
        "cfg_scale": 5.5,
        "width": 768,
        "height": 1152,
        "hires": True,
    },
    "감성 프로필": {
        "shot": "얼굴 클로즈업",
        "background": "미니멀 갤러리",
        "lighting": "창가 자연광",
        "camera": "85mm 패션 인물",
        "dof": "인물 중심",
        "steps": 30,
        "cfg_scale": 5.5,
        "width": 832,
        "height": 1216,
        "hires": True,
    },
    "오피스 프로필": {
        "shot": "상반신",
        "background": "모던 오피스",
        "lighting": "밝은 스튜디오",
        "camera": "50mm 자연 인물",
        "dof": "배경까지 선명",
        "steps": 30,
        "cfg_scale": 6.0,
        "width": 768,
        "height": 1152,
        "hires": True,
    },
    "K-패션 룩북": {
        "shot": "전신 + 여백",
        "background": "그레이 스튜디오",
        "lighting": "패션 스튜디오",
        "camera": "70mm 패션",
        "dof": "넓은 심도",
        "steps": 32,
        "cfg_scale": 5.8,
        "width": 832,
        "height": 1216,
        "hires": True,
    },
    "뷰티 클로즈업": {
        "shot": "얼굴 초근접",
        "background": "베이지 스튜디오",
        "lighting": "뷰티 스튜디오",
        "camera": "105mm 뷰티",
        "dof": "인물 중심",
        "steps": 34,
        "cfg_scale": 5.5,
        "width": 896,
        "height": 1152,
        "hires": True,
    },
    "야외 골든아워": {
        "shot": "허리 위",
        "background": "한강/공원",
        "lighting": "골든아워",
        "camera": "50mm 자연 인물",
        "dof": "살짝 분리",
        "steps": 30,
        "cfg_scale": 5.5,
        "width": 768,
        "height": 1152,
        "hires": True,
    },
    "럭셔리 라이프스타일": {
        "shot": "허벅지 위",
        "background": "호텔 라운지",
        "lighting": "측면 창가광",
        "camera": "85mm 패션 인물",
        "dof": "살짝 분리",
        "steps": 32,
        "cfg_scale": 5.8,
        "width": 832,
        "height": 1216,
        "hires": True,
    },
    "남성 데일리": {
        "shot": "상반신",
        "background": "대형 카페",
        "lighting": "부드러운 자연광",
        "camera": "50mm 자연 인물",
        "dof": "자연스러운 심도",
        "steps": 30,
        "cfg_scale": 5.8,
        "width": 768,
        "height": 1152,
        "hires": True,
    },
}

MAPPING_GROUPS: Mapping[str, Mapping[str, str]] = {
    "gender": GENDER_MAP,
    "age": AGE_MAP,
    "hair_style": HAIR_STYLE_MAP,
    "hair_color": HAIR_COLOR_MAP,
    "face_shape": FACE_SHAPE_MAP,
    "eye_style": EYE_STYLE_MAP,
    "nose_style": NOSE_STYLE_MAP,
    "lip_style": LIP_STYLE_MAP,
    "skin_tone": SKIN_TONE_MAP,
    "expression": EXPRESSION_MAP,
    "body_frame": BODY_FRAME_MAP,
    "height_impression": HEIGHT_MAP,
    "shoulder": SHOULDER_MAP,
    "waist_hip": WAIST_HIP_MAP,
    "chest_proportion": CHEST_PROPORTION_MAP,
    "outfit": OUTFIT_MAP,
    "outfit_color": OUTFIT_COLOR_MAP,
    "mood": MOOD_MAP,
    "personality": PERSONALITY_MAP,
    "pose": POSE_MAP,
    "shot": SHOT_MAP,
    "background": BACKGROUND_MAP,
    "lighting": LIGHTING_MAP,
    "depth_of_field": DOF_MAP,
    "camera": CAMERA_MAP,
}


def option_keys(mapping: Mapping[str, str]) -> list[str]:
    return list(mapping.keys())


def mapping_statistics() -> dict[str, object]:
    by_group = {name: len(mapping) for name, mapping in MAPPING_GROUPS.items()}
    return {
        "groups": len(MAPPING_GROUPS),
        "total_options": sum(by_group.values()),
        "by_group": by_group,
        "presets": len(PRESETS),
    }


__all__ = [name for name in globals() if name.endswith("_MAP")] + [
    "PRESETS",
    "MAPPING_GROUPS",
    "option_keys",
    "mapping_statistics",
]
