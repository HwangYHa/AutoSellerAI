"""Small resilient client for the AUTOMATIC1111 Stable Diffusion WebUI API."""
from __future__ import annotations

import os
from typing import Any, Callable

import httpx

from app.image_studio.schemas import WebUICapabilities


class StableDiffusionWebUIError(RuntimeError):
    pass


class StableDiffusionWebUIClient:
    def __init__(self, base_url: str | None = None, timeout_seconds: float | None = None):
        self.base_url = (base_url or os.getenv("SD_WEBUI_URL", "http://127.0.0.1:7860")).rstrip("/")
        self.timeout_seconds = float(timeout_seconds or os.getenv("SD_WEBUI_TIMEOUT_SECONDS", "900"))
        username = os.getenv("SD_WEBUI_USERNAME", "").strip()
        password = os.getenv("SD_WEBUI_PASSWORD", "")
        self.auth = (username, password) if username else None

    def _request(self, method: str, path: str, *, timeout: float | None = None, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(auth=self.auth, follow_redirects=True, timeout=timeout or self.timeout_seconds) as client:
                response = client.request(method, url, **kwargs)
                response.raise_for_status()
        except httpx.ConnectError as exc:
            raise StableDiffusionWebUIError(
                f"Stable Diffusion WebUI에 연결할 수 없습니다: {self.base_url}. "
                "WebUI를 --api 옵션으로 실행했는지 확인하세요. Docker에서 AutoSellerAI를 실행 중이면 "
                "SD_WEBUI_URL은 보통 http://host.docker.internal:7860 이어야 합니다."
            ) from exc
        except httpx.TimeoutException as exc:
            raise StableDiffusionWebUIError("Stable Diffusion 이미지 생성 요청이 제한 시간을 초과했습니다.") from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:800]
            raise StableDiffusionWebUIError(
                f"Stable Diffusion WebUI API 오류 HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise StableDiffusionWebUIError(f"Stable Diffusion WebUI 통신 오류: {exc}") from exc

        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise StableDiffusionWebUIError("Stable Diffusion WebUI가 JSON이 아닌 응답을 반환했습니다.") from exc

    def options(self) -> dict[str, Any]:
        data = self._request("GET", "/sdapi/v1/options", timeout=20)
        return data if isinstance(data, dict) else {}

    def samplers(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/sdapi/v1/samplers", timeout=20)
        return data if isinstance(data, list) else []

    def schedulers(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/sdapi/v1/schedulers", timeout=20)
        return data if isinstance(data, list) else []

    def upscalers(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/sdapi/v1/upscalers", timeout=20)
        return data if isinstance(data, list) else []

    def latent_upscale_modes(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/sdapi/v1/latent-upscale-modes", timeout=20)
        return data if isinstance(data, list) else []

    def checkpoints(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/sdapi/v1/sd-models", timeout=30)
        return data if isinstance(data, list) else []

    def scripts(self) -> dict[str, list[str]]:
        data = self._request("GET", "/sdapi/v1/scripts", timeout=20)
        if not isinstance(data, dict):
            return {"txt2img": [], "img2img": []}
        return {
            "txt2img": [str(x) for x in data.get("txt2img", [])],
            "img2img": [str(x) for x in data.get("img2img", [])],
        }

    def progress(self) -> dict[str, Any]:
        data = self._request("GET", "/sdapi/v1/progress?skip_current_image=true", timeout=20)
        return data if isinstance(data, dict) else {}

    def interrupt(self) -> dict[str, Any]:
        data = self._request("POST", "/sdapi/v1/interrupt", timeout=20)
        return data if isinstance(data, dict) else {}

    def txt2img(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._request("POST", "/sdapi/v1/txt2img", json=payload)
        if not isinstance(data, dict) or not isinstance(data.get("images"), list):
            raise StableDiffusionWebUIError("txt2img 응답에 images 배열이 없습니다.")
        return data

    @staticmethod
    def _optional(fetcher: Callable[[], Any], fallback: Any) -> Any:
        try:
            return fetcher()
        except StableDiffusionWebUIError:
            # A1111 versions differ slightly in discovery endpoints.  Generation
            # should remain usable when an optional catalog endpoint is absent.
            return fallback

    def capabilities(self) -> WebUICapabilities:
        try:
            # /options is the minimum viable health check.  If this fails there is
            # no usable A1111 API behind the configured URL.
            options = self.options()
            samplers = self._optional(self.samplers, [])
            schedulers = self._optional(self.schedulers, [])
            upscalers = self._optional(self.upscalers, [])
            latent_modes = self._optional(self.latent_upscale_modes, [])
            checkpoints = self._optional(self.checkpoints, [])
            scripts = self._optional(self.scripts, {"txt2img": [], "img2img": []})
            script_names = scripts.get("txt2img", []) if isinstance(scripts, dict) else []
            adetailer = any("adetailer" in name.lower() or "after detailer" in name.lower() for name in script_names)

            upscaler_names = [str(x.get("name") or "") for x in upscalers if isinstance(x, dict)]
            for row in latent_modes:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name") or row.get("mode") or "")
                if name and name not in upscaler_names:
                    upscaler_names.append(name)

            return WebUICapabilities(
                ok=True,
                base_url=self.base_url,
                model=str(options.get("sd_model_checkpoint") or ""),
                samplers=[str(x.get("name") or x.get("label") or "") for x in samplers if isinstance(x, dict)],
                schedulers=[str(x.get("name") or x.get("label") or "") for x in schedulers if isinstance(x, dict)],
                upscalers=upscaler_names,
                txt2img_scripts=script_names,
                checkpoints=[str(x.get("title") or x.get("model_name") or x.get("filename") or "") for x in checkpoints if isinstance(x, dict)],
                adetailer_available=adetailer,
            )
        except Exception as exc:
            return WebUICapabilities(ok=False, base_url=self.base_url, error=str(exc))


def choose_upscaler(requested: str, available: list[str]) -> str | None:
    clean = [x for x in available if x and x.lower() != "none"]
    if not clean:
        return None
    if requested in clean:
        return requested
    lowered = {x.lower(): x for x in clean}
    for candidate in ("R-ESRGAN 4x+", "R-ESRGAN 4x+ Anime6B", "Latent (antialiased)", "Latent", "Lanczos"):
        match = lowered.get(candidate.lower())
        if match:
            return match
    return clean[0]


__all__ = [
    "StableDiffusionWebUIClient",
    "StableDiffusionWebUIError",
    "choose_upscaler",
]
