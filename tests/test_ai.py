import json
from pathlib import Path

import pytest

from mcnp_report.ai import generate_ai
from mcnp_report.config import AIProfile
from mcnp_report.errors import AIProviderError
from mcnp_report.parser import parse_output


def _sample_result():
    path = Path(r"D:\mcnpproject\1.out")
    if not path.is_file(): pytest.skip("external sample unavailable")
    return parse_output(path)


def test_adapter_success(tmp_path):
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        "def generate(request, settings):\n"
        " return {'overview':'NPS 10000000，F4 相对误差 0.0035。','findings':[{'title':'统计','interpretation':'F4 未通过 1 项检查。','severity':'warning','fact_ids':['run.nps','tally.4.relative_error','tally.4.missed_checks']}]}\n",
        encoding="utf-8",
    )
    result = _sample_result()
    try:
        ai = generate_ai(result, AIProfile("test", provider="adapter", adapter_path=str(adapter)), "required")
        assert ai.status == "ok" and ai.provider == "adapter"
    finally: result.close()


def test_numeric_hallucination_is_blocked(tmp_path):
    adapter = tmp_path / "bad.py"
    adapter.write_text("def generate(request, settings):\n return {'overview':'结果为 99999999。','findings':[]}\n", encoding="utf-8")
    result = _sample_result()
    try:
        with pytest.raises(AIProviderError):
            generate_ai(result, AIProfile("test", provider="adapter", adapter_path=str(adapter)), "required")
        fallback = generate_ai(result, AIProfile("test", provider="adapter", adapter_path=str(adapter)), "auto")
        assert fallback.status == "fallback" and fallback.error
    finally: result.close()


def test_provider_timeout_required_and_auto(monkeypatch):
    import mcnp_report.ai as ai_module
    def fail(profile, request):
        raise AIProviderError("timeout")
    monkeypatch.setattr(ai_module, "_openai_compatible", fail)
    profile = AIProfile("test", base_url="https://invalid.example/v1", model="model")
    result = _sample_result()
    try:
        with pytest.raises(AIProviderError):
            generate_ai(result, profile, "required")
        fallback = generate_ai(result, profile, "auto")
        assert fallback.status == "fallback" and "timeout" in fallback.error
        summary = result.as_summary_dict()
        assert "source_path" in summary["metadata"]
        assert all("path" not in fact_id for fact_id in summary["facts"])
    finally: result.close()


def test_openai_compatible_extra_body(monkeypatch):
    import mcnp_report.ai as ai_module

    captured = {}

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self):
            return json.dumps({"choices": [{"message": {"content": '{"overview":"运行正常。","findings":[]}'}}]}).encode()

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setenv("TEST_DEEPSEEK_KEY", "secret")
    monkeypatch.setattr(ai_module, "urlopen", fake_urlopen)
    profile = AIProfile(
        "deepseek",
        base_url="https://api.deepseek.com",
        endpoint="chat_completions",
        model="deepseek-flash",
        api_key_env="TEST_DEEPSEEK_KEY",
        extra_body={"thinking": {"type": "disabled"}},
    )
    result = _sample_result()
    try:
        ai = generate_ai(result, profile, "required")
        assert ai.status == "ok"
        assert captured["body"]["thinking"] == {"type": "disabled"}
    finally:
        result.close()
