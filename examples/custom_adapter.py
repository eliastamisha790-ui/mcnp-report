"""自定义模型适配器示例。

该文件会作为可信 Python 代码执行。生产环境请只加载自己审核过的适配器。
"""


def generate(request: dict, settings: dict) -> dict:
    facts = request.get("facts", {})
    return {
        "provider": "example-adapter",
        "status": "ok",
        "overview": "示例适配器已收到本地结构化事实。",
        "findings": [
            {
                "title": "运行状态",
                "interpretation": "请根据事实引用复核运行结束状态。",
                "severity": "info",
                "fact_ids": ["run.normal_termination"] if "run.normal_termination" in facts else [],
            }
        ],
    }

