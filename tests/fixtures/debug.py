# Copyright (C) 2022-Present Indoc Systems
#
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE,
# Version 3.0 (the "License") available at https://www.gnu.org/licenses/agpl-3.0.en.html.
# You may not use this file except in compliance with the License.

import time as tm
from pathlib import Path

import pytest
from playwright.sync_api import Page


class Debug:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def capture_screenshot(self, page: Page) -> None:
        page.screenshot(path=self.output_dir / f'debug-screenshot-{int(tm.time())}.png')


@pytest.fixture
def debug(pytestconfig: pytest.Config) -> Debug:
    output_dir = Path(pytestconfig.getoption('--output')).absolute()
    return Debug(output_dir)
