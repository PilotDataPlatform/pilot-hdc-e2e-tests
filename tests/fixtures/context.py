# Copyright (C) 2022-Present Indoc Systems
#
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE,
# Version 3.0 (the "License") available at https://www.gnu.org/licenses/agpl-3.0.en.html.
# You may not use this file except in compliance with the License.

import datetime as dt
import os
from collections.abc import Generator
from pathlib import Path

import pytest
from playwright.sync_api import BrowserContext
from playwright.sync_api import Page
from playwright.sync_api import ViewportSize
from playwright.sync_api import expect
from pytest import TempPathFactory
from pytest_playwright import CreateContextCallback


class Contexts:
    def __init__(self, storage_state_dir: Path) -> None:
        self.storage_state_dir = storage_state_dir
        self.viewport = ViewportSize(width=1280, height=1024)

        self.users: dict[str, str] = {}
        self.states: dict[str, Path] = {}

    def add_user(self, username: str, password: str) -> None:
        self.users[username] = password

    def login(self, new_context: CreateContextCallback, username: str) -> Path:
        password = self.users[username]

        context = new_context(viewport=self.viewport)
        page = context.new_page()

        page.goto('/login')
        page.get_by_role('alert').get_by_role('button').click()  # Accept cookies

        page.locator('#auth_login_btn').click()
        page.locator('#login-username-button').click()
        page.locator('input[name="username"]').fill(username)
        page.locator('input[name="password"]').fill(password)
        page.locator('input[type="submit"]').click()
        expect(page.locator('#header_username')).to_contain_text(username)

        page.locator('span.ant-notification-notice-close-icon').click()  # Close release notes
        for element in page.locator('span', has_text="Don't show again").all():  # Close maintenance notices
            element.click()

        storage_state = self.storage_state_dir / f'{username}.json'
        context.storage_state(path=storage_state)
        page.close()

        return storage_state

    def get_context_for(self, new_context: CreateContextCallback, username: str) -> BrowserContext:
        if username not in self.states:
            self.states[username] = self.login(new_context, username)
        return new_context(storage_state=self.states[username], viewport=self.viewport)


@pytest.fixture(scope='session')
def storage_state_dir(tmp_path_factory: TempPathFactory) -> Path:
    return tmp_path_factory.mktemp('storage_state')


@pytest.fixture(scope='session')
def contexts(admin_username: str, collaborator_username: str, storage_state_dir: Path) -> Contexts:
    contexts = Contexts(storage_state_dir)
    contexts.add_user(admin_username, os.environ.get('E2E_TESTING_ADMIN_PASSWORD', ''))
    contexts.add_user(collaborator_username, os.environ.get('E2E_TESTING_COLLABORATOR_PASSWORD', ''))
    return contexts


@pytest.fixture(scope='session')
def project_code() -> str:
    return os.environ.get('E2E_TESTING_PROJECT_CODE', 'e2etesting')


@pytest.fixture(scope='session')
def pilotcli_version_tag() -> str:
    return os.environ.get('E2E_TESTING_PILOTCLI_VERSION_TAG', 'v2.2.7')


@pytest.fixture(scope='session')
def admin_username() -> str:
    return os.environ.get('E2E_TESTING_ADMIN_USERNAME', 'e2etestingadmin')


@pytest.fixture(scope='session')
def collaborator_username() -> str:
    return os.environ.get('E2E_TESTING_COLLABORATOR_USERNAME', 'e2etestingcollaborator')


@pytest.fixture
def admin_page(contexts: Contexts, new_context: CreateContextCallback, admin_username: str) -> Generator[Page]:
    with contexts.get_context_for(new_context, admin_username) as context:
        yield context.new_page()


@pytest.fixture
def collaborator_page(
    contexts: Contexts, new_context: CreateContextCallback, collaborator_username: str
) -> Generator[Page]:
    with contexts.get_context_for(new_context, collaborator_username) as context:
        yield context.new_page()


@pytest.fixture()
def working_path() -> Path:
    return Path(dt.datetime.now(tz=dt.UTC).strftime('%Y/%m/%d'))
