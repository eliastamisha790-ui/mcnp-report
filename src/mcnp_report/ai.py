from __future__ import annotations

from dataclasses import asdict
import importlib.util
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import AIProfile
from .errors import AIProviderError, ConfigurationError
from .models import AIFinding, AIRequest, AIResult, ParseResult


SEVERITIES = {"info", "warning", "critical"}


def local_result(result: ParseResult, error: str = "") -> AIResult:
    metadata = result.metadata
    tally = result.tally_summaries[0] if result.tally_summaries else None
    state = "正常结束" if metadata.normal_termination else "未确认正常结束"
    if tally and tally.total is not None:
        overview = (
            f"本次 MCNP 固定源计算{state}，共运行 {metadata.nps or 0:,} 个粒子历史。"
            f"F{tally.tally_id} 总值为 {tally.total:.6E}，相对误差为 {tally.relative_error:.4f}。"
        )
    else:
        overview = f"本次 MCNP 计算{state}，未提取到完整 tally 总值。"
    findings: list[AIFinding] = []
    if tally:
        if tally.missed_checks:
            findings.append(AIFinding("统计检查", f"TFC 未通过 {tally.missed_checks} 项检查，建议重点复核未通过项及 FOM 趋势。", "warning", [f"tally.{tally.tally_id}.missed_checks"]))
        if tally.high_error_bins:
            findings.append(AIFinding("高相对误差分箱", f"有 {tally.high_error_bins} 个分箱的相对误差超过 0.10，该部分结果需谨慎使用。", "warning", [f"tally.{tally.tally_id}.high_error_bins"]))
        if tally.zero_bins:
            findings.append(AIFinding("零计数分箱", f"有 {tally.zero_bins} 个零值分箱，应结合源项、截断和分箱设置判断其是否合理。", "info", [f"tally.{tally.tally_id}.zero_bins"]))
    return AIResult("local-rules", "fallback" if error else "local", overview, findings, error)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIProviderError(f"AI 返回不是有效 JSON：{exc}") from exc
    if not isinstance(value, dict):
        raise AIProviderError("AI 返回必须是 JSON 对象。")
    return value


def _validate(payload: dict[str, Any], request: AIRequest, provider: str) -> AIResult:
    facts = request.facts
    overview = str(payload.get("overview", "")).strip()
    findings_raw = payload.get("findings", [])
    if not overview or not isinstance(findings_raw, list):
        raise AIProviderError("AI 返回缺少 overview 或 findings。")
    findings: list[AIFinding] = []
    referenced_text = overview
    for item in findings_raw[:12]:
        if not isinstance(item, dict):
            raise AIProviderError("AI findings 格式错误。")
        ids = [str(v) for v in item.get("fact_ids", [])]
        if any(v not in facts for v in ids):
            raise AIProviderError("AI 引用了不存在的事实 ID。")
        severity = str(item.get("severity", "info")).lower()
        if severity not in SEVERITIES:
            raise AIProviderError(f"AI 严重级别无效：{severity}")
        finding = AIFinding(str(item.get("title", "未命名发现")), str(item.get("interpretation", "")), severity, ids)
        findings.append(finding); referenced_text += " " + finding.interpretation

    allowed_numbers: set[float] = {0.0, 1.0, 10.0, 0.1}
    for value in facts.values():
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value is not None:
            allowed_numbers.add(float(value))
    for token in re.findall(r"(?<![\w.])[+-]?(?:\d+\.\d+|\d{3,})(?:[Ee][+-]?\d+)?", referenced_text):
        number = float(token)
        if not any(abs(number - allowed) <= max(1e-10, abs(allowed) * 1e-5) for allowed in allowed_numbers):
            raise AIProviderError(f"AI 输出包含未经事实支持的数字：{token}")
    return AIResult(provider, "ok", overview, findings)


def _adapter(profile: AIProfile, request: AIRequest) -> dict[str, Any]:
    path = Path(profile.adapter_path).expanduser().resolve()
    if not path.is_file():
        raise ConfigurationError(f"自定义适配器不存在：{path}")
    spec = importlib.util.spec_from_file_location("mcnp_report_external_adapter", path)
    if spec is None or spec.loader is None:
        raise ConfigurationError(f"无法加载自定义适配器：{path}")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    if not callable(getattr(module, "generate", None)):
        raise ConfigurationError("自定义适配器必须定义 generate(request, settings)。")
    payload = module.generate(asdict(request), asdict(profile))
    if not isinstance(payload, dict):
        raise AIProviderError("自定义适配器必须返回 dict。")
    return payload


def _openai_compatible(profile: AIProfile, ai_request: AIRequest) -> dict[str, Any]:
    if not profile.base_url or not profile.model:
        raise ConfigurationError("AI profile 必须配置 base_url 和 model。")
    api_key = os.environ.get(profile.api_key_env, "")
    if not api_key:
        raise ConfigurationError(f"未设置 API 密钥环境变量：{profile.api_key_env}")
    system = (
        "你是 MCNP 核计算结果审核助手。只能根据 facts 解释，不得补充任何未提供数字。"
        "返回 JSON：{overview:string, findings:[{title,interpretation,severity:info|warning|critical,fact_ids:[string]}]}。"
    )
    responses_endpoint = profile.endpoint == "responses" or profile.endpoint.rstrip("/").endswith("/responses")
    if profile.endpoint.startswith(("http://", "https://")):
        url = profile.endpoint
    elif profile.endpoint == "responses":
        url = profile.base_url.rstrip("/") + "/responses"
    elif profile.endpoint == "chat_completions":
        url = profile.base_url.rstrip("/") + "/chat/completions"
    else:
        url = profile.base_url.rstrip("/") + "/" + profile.endpoint.lstrip("/")
    if responses_endpoint:
        body = {"model": profile.model, "instructions": system, "input": json.dumps(asdict(ai_request), ensure_ascii=False), "max_output_tokens": profile.max_output_tokens, "temperature": profile.temperature}
    else:
        body = {"model": profile.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(asdict(ai_request), ensure_ascii=False)}], "max_tokens": profile.max_output_tokens, "temperature": profile.temperature}
        if profile.json_mode: body["response_format"] = {"type": "json_object"}
    body.update(profile.extra_body)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", **profile.extra_headers}
    try:
        with urlopen(Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"), timeout=profile.timeout_seconds) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise AIProviderError(f"AI HTTP {exc.code}：{exc.reason}") from exc
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise AIProviderError(f"AI 请求失败：{exc}") from exc
    try:
        if responses_endpoint:
            text = raw.get("output_text") or raw["output"][0]["content"][0]["text"]
        else:
            text = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AIProviderError("AI 响应结构异常。") from exc
    return _extract_json(text)


def generate_ai(result: ParseResult, profile: AIProfile | None, mode: str) -> AIResult:
    if mode == "off":
        return local_result(result)
    if profile is None:
        error = "未配置 AI profile。"
        if mode == "required": raise AIProviderError(error)
        return local_result(result, error)
    request = AIRequest(result.facts())
    try:
        if profile.provider == "adapter":
            payload = _adapter(profile, request)
        elif profile.provider == "openai-compatible":
            payload = _openai_compatible(profile, request)
        else:
            raise ConfigurationError(f"不支持的 AI provider：{profile.provider}")
        return _validate(payload, request, profile.provider)
    except (AIProviderError, ConfigurationError, Exception) as exc:
        if mode == "required":
            raise AIProviderError(str(exc)) from exc
        return local_result(result, str(exc))
