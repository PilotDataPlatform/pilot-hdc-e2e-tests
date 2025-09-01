# Copyright (C) 2022-Present Indoc Systems
#
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE,
# Version 3.0 (the "License") available at https://www.gnu.org/licenses/agpl-3.0.en.html.
# You may not use this file except in compliance with the License.

import datetime as dt
import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser
from playwright.sync_api import BrowserContext
from playwright.sync_api import Page
from playwright.sync_api import ViewportSize
from playwright.sync_api import expect
from pytest import TempPathFactory


class Contexts:
    def __init__(self, browser: Browser, browser_context_args: dict[str, Any], storage_state_dir: Path) -> None:
        self.browser = browser
        self.browser_context_args = browser_context_args
        self.storage_state_dir = storage_state_dir
        self.viewport = ViewportSize(width=1280, height=1024)

        self.users: dict[str, str] = {}
        self.contexts: dict[str, BrowserContext] = {}

    def add_user(self, username: str, password: str) -> None:
        self.users[username] = password

    def close(self) -> None:
        for context in self.contexts.values():
            context.close()
        self.contexts.clear()

    def login(self, username: str) -> Path:
        password = self.users[username]

        context = self.browser.new_context(**self.browser_context_args)
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
        context.close()

        return storage_state

    def get_page_for(self, username: str) -> Page:
        if username not in self.contexts:
            storage_state = self.login(username)
            self.contexts[username] = self.browser.new_context(
                **self.browser_context_args,
                storage_state=storage_state,
                viewport=self.viewport,
            )

        context = self.contexts[username]
        return context.new_page()


@pytest.fixture(scope='session')
def storage_state_dir(tmp_path_factory: TempPathFactory) -> Path:
    return tmp_path_factory.mktemp('storage_state')


@pytest.fixture(scope='session')
def contexts(
    admin_username: str,
    collaborator_username: str,
    browser: Browser,
    browser_context_args: dict[str, Any],
    storage_state_dir: Path,
) -> Generator[Contexts]:
    contexts = Contexts(browser, browser_context_args, storage_state_dir)

    contexts.add_user(admin_username, os.environ.get('E2E_TESTING_ADMIN_PASSWORD', ''))
    contexts.add_user(collaborator_username, os.environ.get('E2E_TESTING_COLLABORATOR_PASSWORD', ''))

    yield contexts

    contexts.close()


@pytest.fixture(scope='session')
def project_code() -> str:
    return os.environ.get('E2E_TESTING_PROJECT_CODE', 'e2etesting')


@pytest.fixture(scope='session')
def admin_username() -> str:
    return os.environ.get('E2E_TESTING_ADMIN_USERNAME', 'e2etestingadmin')


@pytest.fixture(scope='session')
def collaborator_username() -> str:
    return os.environ.get('E2E_TESTING_COLLABORATOR_USERNAME', 'e2etestingcollaborator')


@pytest.fixture
def admin_page(contexts: Contexts, admin_username: str) -> Generator[Page]:
    page = contexts.get_page_for(admin_username)
    yield page
    page.close()


@pytest.fixture
def collaborator_page(contexts: Contexts, collaborator_username: str) -> Generator[Page]:
    page = contexts.get_page_for(collaborator_username)
    yield page
    page.close()


@pytest.fixture()
def working_path() -> Path:
    return Path(dt.datetime.now(tz=dt.UTC).strftime('%Y/%m/%d'))
