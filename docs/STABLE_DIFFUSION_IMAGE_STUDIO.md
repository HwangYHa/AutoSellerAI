# AutoSellerAI Stable Diffusion AI 인물 이미지 스튜디오

## 목적

AUTOMATIC1111 Stable Diffusion WebUI의 복잡한 프롬프트/샘플러/Hires.fix/ADetailer 설정을 AutoSellerAI의 선택형 UI와 Seller OS REST API로 감싸서, 운영자가 얼굴·헤어·체형·의상·분위기·촬영 조건만 선택하면 일관된 API payload를 생성하도록 합니다.

## 1. Stable Diffusion WebUI 준비

WebUI의 REST API가 활성화되어야 합니다.

Windows의 `webui-user.bat`를 사용하는 경우 설치 환경에 맞게 `COMMANDLINE_ARGS`에 다음 옵션을 포함합니다.

```bat
set COMMANDLINE_ARGS=--api --listen --port 7860
```

`--listen`은 WebUI를 다른 인터페이스에서도 받을 수 있게 하므로 방화벽에서 공용 네트워크 접근을 열지 않는 것을 권장합니다. API 인증을 사용할 경우 WebUI의 `--api-auth user:password`와 AutoSellerAI의 `SD_WEBUI_USERNAME`, `SD_WEBUI_PASSWORD`를 함께 설정합니다.

브라우저에서 WebUI를 확인한 뒤 API 확인은 다음 경로를 사용합니다.

```text
http://127.0.0.1:7860/docs
http://127.0.0.1:7860/sdapi/v1/options
```

## 2. AutoSellerAI 환경변수

로컬 Python에서 AutoSellerAI를 직접 실행하는 경우:

```env
SD_WEBUI_URL=http://127.0.0.1:7860
```

Docker Compose를 사용하는 기본 구성에서는 컨테이너의 `127.0.0.1`이 Windows 호스트가 아니므로 다음 주소를 사용합니다.

```env
SD_WEBUI_DOCKER_URL=http://host.docker.internal:7860
SD_WEBUI_TIMEOUT_SECONDS=900
SD_IMAGE_OUTPUT_DIR=data/generated/stable_diffusion
```

Docker Compose는 `SD_WEBUI_DOCKER_URL`을 컨테이너 내부 `SD_WEBUI_URL`로 주입합니다.

Seller OS API를 local 외 환경에서 노출할 경우 `SELLER_API_TOKEN`을 반드시 설정합니다. 이미지 스튜디오 REST API는 기존 Seller OS `/api/v3` 라우터 아래에 마운트되어 동일한 Bearer 인증 정책을 상속합니다.

## 3. 실행

```powershell
docker compose down
docker compose up -d --build --force-recreate
```

상태 확인:

```powershell
docker compose ps
docker compose logs --tail=100 autoseller
docker compose logs --tail=100 seller-api
docker compose logs --tail=100 image-worker
```

Streamlit 메뉴의 **AI 인물 이미지 스튜디오**로 이동합니다.

Seller API Swagger 문서는 다음에서 확인할 수 있습니다.

```text
http://127.0.0.1:8001/docs
```

## 4. 생성 흐름

1. UI 또는 REST API에서 프리셋과 얼굴/헤어/체형/의상/촬영 값을 선택합니다.
2. AutoSellerAI가 구조화된 Positive/Negative prompt를 만듭니다.
3. Seller API는 WebUI와 `image-worker` 준비 상태를 확인합니다.
4. 요청을 SQLite `ai_image_generations`에 `queued`로 기록합니다.
5. Redis의 `image` 큐에 RQ 작업을 등록합니다.
6. `image-worker`가 WebUI의 모델/샘플러/업스케일러/스크립트를 확인합니다.
7. ADetailer가 실제 감지된 경우에만 `alwayson_scripts.ADetailer`를 주입합니다.
8. WebUI `/sdapi/v1/txt2img`를 호출합니다.
9. base64 결과를 PNG로 검증한 뒤 공유 `data/generated/stable_diffusion/YYYYMMDD` 폴더에 저장합니다.
10. DB에 payload, 생성 정보, 경고, 이미지 경로를 저장하고 상태를 `completed`로 변경합니다.

HTTP 요청 자체에서는 GPU 생성을 기다리지 않습니다. 생성 요청은 `202 Accepted`로 즉시 반환되고 이후 상태 조회 API로 추적합니다.

## 5. 품질 설계 원칙

- 인물은 성인 연령대만 선택할 수 있습니다.
- 신체는 과도한 숫자형 3-size보다 자연스러운 체형/어깨/허리·골반/상체 비율을 사용합니다. 텍스트 기반 diffusion 모델은 정확한 신체 치수를 보장하지 못하기 때문입니다.
- 피부는 `plastic skin`, `waxy skin`, `excessive beauty filter`를 네거티브로 억제합니다.
- 손은 five fingers / malformed hands / extra fingers를 양·음 프롬프트 양쪽에서 보강합니다.
- 전신 구도는 `cropped legs`, `missing feet`를 추가로 억제합니다.
- 배경까지 선명 모드에서는 `bokeh`, `extreme shallow depth of field`, `blurred background`를 네거티브에 추가합니다.
- 체크포인트 변경은 글로벌 `/options` 변경 대신 요청별 `override_settings.sd_model_checkpoint`를 사용합니다.
- ADetailer가 없는데 무조건 payload를 보내지 않습니다. A1111은 존재하지 않는 always-on script를 요청하면 오류를 반환할 수 있기 때문입니다.

## 6. 동일 인물 유지에 대한 주의

Seed 고정은 구도와 특성을 어느 정도 반복할 수 있지만, 여러 장에서 완전히 동일한 가상 인물 신원을 유지하는 기능은 아닙니다. 장기적인 가상 인플루언서 운영에서 동일 얼굴이 핵심이면 다음 단계로 LoRA 또는 reference-image/IP-Adapter 계층을 별도 추가하는 것이 좋습니다.

## 7. AutoSellerAI REST API

기본 주소:

```text
http://127.0.0.1:8001/api/v3/image-studio
```

`SELLER_API_TOKEN`이 설정된 경우 모든 `/api/v3` 요청에 다음 헤더를 추가합니다.

```text
Authorization: Bearer <SELLER_API_TOKEN>
```

### 런타임 / 카탈로그

```text
GET /health
GET /catalog
GET /progress
```

- `/health`: WebUI 연결, Redis image queue, worker 수, active generation, WebUI progress를 한 번에 반환합니다.
- `/catalog`: UI 선택값과 현재 WebUI checkpoint/sampler/scheduler/upscaler/ADetailer capability를 반환합니다.
- `/progress`: AUTOMATIC1111 `/sdapi/v1/progress`를 안전하게 프록시합니다.

### 프롬프트와 Payload 미리보기

```text
POST /preview
```

`HumanImageRequest` JSON을 보내면 GPU 작업을 만들지 않고 Positive/Negative Prompt, 실제 `txt2img` payload, 예상 최종 해상도를 반환합니다. WebUI가 꺼져 있어도 구조화 프롬프트 미리보기는 동작하며 capability 관련 경고만 포함합니다.

### 생성

```text
POST /generations
```

WebUI와 image-worker가 모두 정상일 때만 `202 Accepted`로 큐 등록합니다. 준비되지 않은 경우 `503`을 반환해 실패 작업이 DB에 누적되지 않게 합니다.

### 조회

```text
GET /generations?limit=50&status=completed
GET /generations/{generation_id}
GET /generations/{generation_id}/images/{image_index}
```

REST 응답에는 컨테이너 내부 `image_paths`를 노출하지 않습니다. 생성 결과는 검증된 이미지 다운로드 URL만 반환하며, 다운로드 API도 `SD_IMAGE_OUTPUT_DIR` 바깥 경로를 거부합니다.

### 재생성

```text
POST /generations/{generation_id}/retry
```

Body:

```json
{"seed_mode":"random"}
```

또는 실제 생성 결과의 seed를 다시 사용하려면:

```json
{"seed_mode":"same"}
```

### 취소

```text
POST /generations/{generation_id}/cancel
```

- 아직 RQ 큐에 있는 작업은 RQ에서 직접 취소합니다.
- 이미 GPU에서 생성 중인 작업은 상태를 `cancel_requested`로 바꾸고 AUTOMATIC1111 `/sdapi/v1/interrupt`를 호출합니다.
- worker는 취소 상태를 인식해 최종 상태를 `cancelled`로 정리하며 단순 `failed`로 덮어쓰지 않습니다.

`image` 큐는 단일 GPU-facing worker를 기본으로 설계했기 때문에 실행 중 작업의 WebUI interrupt가 어떤 generation에 대응하는지 명확하게 유지됩니다.
