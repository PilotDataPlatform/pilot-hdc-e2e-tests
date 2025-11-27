# Copyright (C) 2022-Present Indoc Systems
#
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE,
# Version 3.0 (the "License") available at https://www.gnu.org/licenses/agpl-3.0.en.html.
# You may not use this file except in compliance with the License.

import re
import shutil
import time as tm
from pathlib import Path
from typing import Self
from urllib.parse import urlparse
from uuid import uuid4

import pytest
import requests
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect
from pydantic import BaseModel
from pytest import TempPathFactory
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy
from testcontainers.core.waiting_utils import wait_for_logs


class Container(DockerContainer):
    def get_stdout(self) -> str:
        stdout, _ = self.get_logs()
        return stdout.decode()

    def wait_until_stopped(self, *, timeout: int = 10000) -> str:
        wrapped = self.get_wrapped_container()

        start_time = tm.monotonic()
        while (tm.monotonic() - start_time) * 1000 < timeout:
            wrapped.reload()
            if wrapped.status == 'exited':
                return self.get_stdout()
            tm.sleep(0.5)

        raise PlaywrightTimeoutError(f'Container did not stop within {timeout} milliseconds.')

    def wait_for_logs(self, text: str, timeout: int = 10000) -> str:
        wait_for_logs(self, LogMessageWaitStrategy(text), timeout=timeout / 1000)
        return self.get_stdout()


class PilotCLI(BaseModel):
    work_dir: Path
    work_dir_container: Path = Path('/app')
    base_url: str

    @property
    def config_file(self) -> Path:
        config_file = self.work_dir / 'config.ini'
        config_file.touch(0o600)
        return config_file

    @property
    def env(self) -> dict[str, str]:
        domain = urlparse(self.base_url)
        return {
            'harbor_client_secret': str(uuid4()),
            'keycloak_device_client_id': 'cli',
            'base_url': f'https://api.{domain.netloc}/pilot/',
            'url_harbor': 'https://127.0.0.1',
            'url_bff': f'https://api.{domain.netloc}/pilot/cli',
            'url_keycloak': f'https://iam.{domain.netloc}/realms/hdc/protocol/openid-connect',
        }

    def login(self, page: Page) -> Self:
        with self.run('user login') as container:
            stdout = container.wait_for_logs('Waiting validation finish')
            match = re.search(r'https://\S+', stdout)
            if not match:
                raise ValueError('Login url not found')

            login_url = match.group(0)
            page.goto(login_url)
            page.locator('#kc-login').click()
            expect(page.get_by_role('heading')).to_have_text('Device Login Successful')

            container.wait_for_logs('Welcome to the Command Line Tool!')

        return self

    def run(self, command: str) -> Container:
        return Container(
            image='ubuntu:noble',
            platform='linux/amd64',
            working_dir=str(self.work_dir_container),
            env=self.env,
            volumes=[
                (str(self.work_dir), str(self.work_dir_container), 'rw'),
                (str(self.config_file), '/root/.pilotcli/config.ini', 'rw'),
            ],
            entrypoint=str(self.work_dir_container / 'pilotcli'),
            command=command,
        )


@pytest.fixture(scope='session')
def pilotcli_binary(pilotcli_version_tag: str, tmp_path_factory: TempPathFactory) -> Path:
    work_dir = tmp_path_factory.mktemp(pilotcli_version_tag)
    binary_path = work_dir / 'pilotcli'
    response = requests.get(
        f'https://api.github.com/repos/PilotDataPlatform/pilot-hdc-cli/releases/tags/{pilotcli_version_tag}'
    )
    response.raise_for_status()
    binary_url = response.json()['assets'][0]['browser_download_url']
    with requests.get(binary_url, stream=True) as r:
        r.raise_for_status()
        with open(binary_path, 'wb') as f:
            f.write(r.content)
        binary_path.chmod(0o755)

    return binary_path


@pytest.fixture
def admin_pilotcli(pilotcli_binary: Path, tmp_path_factory: TempPathFactory, base_url: str) -> PilotCLI:
    work_dir = tmp_path_factory.mktemp('admin_pilotcli')
    work_binary = work_dir / 'pilotcli'
    shutil.copyfile(pilotcli_binary, work_binary)
    work_binary.chmod(0o755)
    return PilotCLI(work_dir=work_dir, base_url=base_url)
