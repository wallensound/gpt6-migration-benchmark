import pytest

from harness import config

VARS = ["BENCH_PROVIDER", "BENCH_PROVIDER_GPT_5_6_SOL", "BENCH_MODEL_ID_GPT_5_6_SOL", "BENCH_MODEL_ID_GPT_6_LUNA",
        "AZURE_OPENAI_BASE_URL", "OPENAI_BASE_URL", "BEDROCK_OPENAI_BASE_URL"]


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda: None)
    for v in VARS:
        monkeypatch.delenv(v, raising=False)
    return monkeypatch


def test_default_is_openai(clean_env):
    m = config.model_cfg("gpt-6-luna")
    assert m["provider"] == "openai" and m["model_id"] == "gpt-6-luna"
    assert config.provider_cfg("openai")["base_url"] == "https://api.openai.com/v1"


def test_global_and_per_model_overrides(clean_env):
    clean_env.setenv("BENCH_PROVIDER", "bedrock")
    clean_env.setenv("BENCH_PROVIDER_GPT_5_6_SOL", "azure")
    clean_env.setenv("BENCH_MODEL_ID_GPT_5_6_SOL", "my-deployment")
    assert config.model_cfg("gpt-6-luna")["model_id"] == "global.openai.gpt-6-luna"
    src = config.model_cfg("gpt-5.6-sol")
    assert src["provider"] == "azure" and src["model_id"] == "my-deployment"


def test_azure_needs_a_base_url(clean_env):
    with pytest.raises(RuntimeError, match="AZURE_OPENAI_BASE_URL"):
        config.provider_cfg("azure")
    clean_env.setenv("AZURE_OPENAI_BASE_URL", "https://example.openai.azure.com/openai/v1/")
    assert config.provider_cfg("azure")["base_url"] == "https://example.openai.azure.com/openai/v1"


def test_unknown_provider(clean_env):
    clean_env.setenv("BENCH_PROVIDER", "nope")
    with pytest.raises(KeyError):
        config.model_cfg("gpt-6-luna")
