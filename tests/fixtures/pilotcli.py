# Copyright (C) 2022-Present Indoc Systems
#
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE,
# Version 3.0 (the "License") available at https://www.gnu.org/licenses/agpl-3.0.en.html.
# You may not use this file except in compliance with the License.

import re
import shutil
from pathlib import Path
from typing import Self
from uuid import uuid4

import pytest
import requests
from playwright.sync_api import Page
from playwright.sync_api import expect
from pydantic import BaseModel
from pytest import TempPathFactory
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs


class Container(DockerContainer):
    def get_stdout(self) -> str:
        stdout, _ = self.get_logs()
        return stdout.decode()

    def wait_for_logs(self, text: str, timeout: int = 10000) -> str:
        wait_for_logs(self, text, timeout=timeout / 1000)
        return self.get_stdout()


class PilotCLI(BaseModel):
    work_dir: Path

    @property
    def config_file(self) -> Path:
        config_file = self.work_dir / 'config.ini'
        config_file.touch(0o600)
        return config_file

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
            working_dir='/app',
            env={
                'harbor_client_secret': str(uuid4()),
                'keycloak_device_client_id': 'cli',
                'base_url': 'https://api.hdc.humanbrainproject.eu/pilot/',
                'url_harbor': 'https://127.0.0.1',
                'url_bff': 'https://api.hdc.humanbrainproject.eu/pilot/cli',
                'url_keycloak': 'https://iam.hdc.humanbrainproject.eu/realms/hdc/protocol/openid-connect',
            },
            volumes=[
                (str(self.work_dir), '/app', 'rw'),
                (str(self.config_file), '/root/.pilotcli/config.ini', 'rw'),
            ],
            entrypoint='/app/pilotcli',
            command=command,
        )


@pytest.fixture(scope='session')
def pilotcli_binary(pilotcli_version_tag: str, tmp_path_factory: TempPathFactory) -> Path:
    work_dir = tmp_path_factory.mktemp(pilotcli_version_tag)
    binary_path = work_dir / 'pilotcli'
    response = requests.get(f'https://api.github.com/repos/PilotDataPlatform/cli/releases/tags/{pilotcli_version_tag}')
    binary_url = response.json()['assets'][0]['browser_download_url']
    with requests.get(binary_url, stream=True) as r:
        r.raise_for_status()
        with open(binary_path, 'wb') as f:
            f.write(r.content)
        binary_path.chmod(0o755)

    return binary_path


@pytest.fixture
def admin_pilotcli(pilotcli_binary: Path, tmp_path_factory: TempPathFactory) -> PilotCLI:
    work_dir = tmp_path_factory.mktemp('admin_pilotcli')
    work_binary = work_dir / 'pilotcli'
    shutil.copyfile(pilotcli_binary, work_binary)
    work_binary.chmod(0o755)
    return PilotCLI(work_dir=work_dir)
