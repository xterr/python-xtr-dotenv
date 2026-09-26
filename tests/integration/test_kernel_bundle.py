"""The DotenvBundle boots in a full kernel and exposes its config, parameters resolved."""

from __future__ import annotations

import pytest
from xtr_dependency_injection import Kernel

from xtr_dotenv.bundle import DotenvBundle, DotenvConfig

pytestmark = pytest.mark.anyio


async def test_kernel_exposes_dotenv_config() -> None:
    kernel = Kernel(
        "xtr_dotenv",
        env="test",
        bundles={DotenvBundle: {"all": True}},
        resources=(),
    )
    booted = await kernel.boot()
    try:
        config = await booted.container.get(DotenvConfig)
        assert config.path == str(kernel.project_dir / ".env")
        assert config.env_key == "APP_ENV"
        assert "test" in config.test_envs
    finally:
        await booted.shutdown()
