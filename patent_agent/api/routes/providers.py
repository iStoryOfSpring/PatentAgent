"""Provider profile and LLM activation routes."""

from fastapi import APIRouter, Depends, HTTPException

from models.provider_profile import ProviderProfileCreate, ProviderProfileUpdate
from patent_agent.api.dependencies import get_container
from patent_agent.api.schemas import LLMConfigRequest, ProviderSecretRequest
from patent_agent.application.providers import (
    ProviderBusyError, ProviderInUseError, ProviderService,
)
from patent_agent.infrastructure import AppContainer


router = APIRouter(prefix="/api", tags=["providers"])


def _service(container: AppContainer) -> ProviderService:
    if container.provider_service is None:
        container.provider_service = ProviderService(container)
    return container.provider_service


def _secrets(req: ProviderSecretRequest) -> list[str]:
    return [req.api_key, *req.sensitive_headers.values()]


@router.get("/llm/profiles")
async def list_llm_profiles(container: AppContainer = Depends(get_container)):
    return await _service(container).list_profiles()


@router.post("/llm/profiles")
async def create_llm_profile(req: ProviderProfileCreate, container: AppContainer = Depends(get_container)):
    service = _service(container)
    try:
        return await service.create_profile(req)
    except Exception as exc:
        raise HTTPException(422, service.redacted_error(exc)) from exc


@router.patch("/llm/profiles/{profile_id}")
async def update_llm_profile(profile_id: str, req: ProviderProfileUpdate, container: AppContainer = Depends(get_container)):
    service = _service(container)
    try:
        return await service.update_profile(profile_id, req)
    except KeyError as exc:
        raise HTTPException(404, "供应商配置不存在") from exc
    except ProviderBusyError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(422, service.redacted_error(exc)) from exc


@router.delete("/llm/profiles/{profile_id}")
async def delete_llm_profile(profile_id: str, container: AppContainer = Depends(get_container)):
    try:
        return await _service(container).delete_profile(profile_id)
    except KeyError as exc:
        raise HTTPException(404, "供应商配置不存在") from exc
    except (ProviderBusyError, ProviderInUseError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/llm/profiles/{profile_id}/probe")
async def probe_llm_profile(
    profile_id: str, req: ProviderSecretRequest = ProviderSecretRequest(),
    container: AppContainer = Depends(get_container),
):
    service = _service(container)
    try:
        return await service.probe(profile_id, req)
    except KeyError as exc:
        raise HTTPException(404, "供应商配置不存在") from exc
    except Exception as exc:
        category = service.error_category(exc)
        service.record_probe_state(
            profile_id, "failed", error_category=category,
            stages=getattr(exc, "stages", {}),
        )
        raise HTTPException(502, {
            "message": "连接探测失败: " + service.redacted_error(exc, _secrets(req)),
            "category": category, "stages": getattr(exc, "stages", {}),
        }) from exc


@router.post("/llm/profiles/{profile_id}/models")
async def discover_llm_models(
    profile_id: str, req: ProviderSecretRequest = ProviderSecretRequest(),
    container: AppContainer = Depends(get_container),
):
    service = _service(container)
    try:
        return await service.discover_models(profile_id, req)
    except KeyError as exc:
        raise HTTPException(404, "供应商配置不存在") from exc
    except Exception as exc:
        raise HTTPException(
            502, "获取模型失败，可继续手工填写模型 ID。" + service.redacted_error(exc, _secrets(req)),
        ) from exc


@router.post("/llm/profiles/{profile_id}/activate")
async def activate_llm_profile(
    profile_id: str, req: ProviderSecretRequest = ProviderSecretRequest(),
    container: AppContainer = Depends(get_container),
):
    service = _service(container)
    try:
        return await service.activate(profile_id, req)
    except KeyError as exc:
        raise HTTPException(404, "供应商配置不存在") from exc
    except ProviderBusyError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        category = service.error_category(exc)
        service.record_probe_state(
            profile_id, "failed", error_category=category,
            stages=getattr(exc, "stages", {}),
        )
        raise HTTPException(502, {
            "message": "无法激活供应商: " + service.redacted_error(exc, _secrets(req)),
            "category": category, "stages": getattr(exc, "stages", {}),
        }) from exc


@router.post("/llm/disconnect")
async def disconnect_llm(container: AppContainer = Depends(get_container)):
    try:
        return await _service(container).disconnect()
    except ProviderBusyError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/agent/config")
async def agent_config(req: LLMConfigRequest, container: AppContainer = Depends(get_container)):
    service = _service(container)
    try:
        return await service.configure_legacy(req.provider, req.api_key, req.base_url, req.model)
    except ProviderBusyError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        status = 400 if "API key" in str(exc) or "Unknown provider" in str(exc) else 502
        raise HTTPException(status, service.redacted_error(exc, [req.api_key])) from exc
    except Exception as exc:
        raise HTTPException(502, "Failed to create agent: " + service.redacted_error(exc, [req.api_key])) from exc
