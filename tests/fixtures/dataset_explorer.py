# Copyright (C) 2022-Present Indoc Systems
#
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE,
# Version 3.0 (the "License") available at https://www.gnu.org/licenses/agpl-3.0.en.html.
# You may not use this file except in compliance with the License.

import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Annotated
from typing import Self

import pytest
from annotated_types import Len
from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect
from pydantic import BaseModel


class Dataset(BaseModel):
    code: str
    project_code: str
    title: str
    authors: Annotated[list[str], Len(min_length=1)]
    description: str

    @classmethod
    def generate(cls, *, project_code: str, title: str | None = None, code: str | None = None) -> Self:
        unique_id = os.urandom(10).hex()

        if title is None:
            title = f'E2E Test {unique_id}'

        if code is None:
            code = f'e2etest{unique_id}'

        authors = ['E2E Test1', 'E2E Test2']
        description = 'E2E Test Dataset Description'

        return cls(code=code, project_code=project_code, title=title, authors=authors, description=description)


class DatasetExplorer:
    def __init__(self, page: Page, project_code: str) -> None:
        self.page = page
        self.project_code = project_code

    def open(self, dataset_code: str) -> Self:
        url = f'/dataset/{dataset_code}/data'
        if not self.page.url.endswith(url):
            with self.wait_until_refreshed():
                self.page.goto(url)
        return self

    def toggle_dataset_status_popover(self, is_open: bool) -> Self:
        file_panel = self.page.locator('[class*=DatasetFilePanel_file_panel]')
        if ('ant-popover-open' in file_panel.get_attribute('class')) != is_open:
            file_panel.click()
        return self

    def open_dataset_status_popover(self, tab: str = 'Import') -> Self:
        self.toggle_dataset_status_popover(True)
        self.page.get_by_role('tab', name=tab).click()
        return self

    def close_dataset_status_popover(self) -> Self:
        return self.toggle_dataset_status_popover(False)

    def create_dataset(self, dataset: Dataset) -> Self:
        self.page.goto('/datasets')

        self.page.get_by_role('button', name='Create New').click()

        self.page.get_by_label('Title').fill(dataset.title)
        self.page.get_by_label('Dataset Code').fill(dataset.code)
        self.page.get_by_label('Dataset Description').fill(dataset.description)

        self.page.get_by_label('Project Code').click()
        self.page.locator('div.ant-select-dropdown').get_by_title(self.project_code).click()

        authors_input = self.page.get_by_label('Authors')
        authors_input.focus()
        for author in dataset.authors:
            authors_input.fill(author)
            authors_input.press('Enter')
            authors_input.press('Escape')

        with self.page.expect_response(lambda r: r.url.endswith('v1/datasets/') and r.request.method == 'POST'):
            self.page.get_by_role('button', name='Create').click()

        return self

    def create_folder(self, folder_name: str) -> Self:
        self.page.get_by_role('button', name='plus New Folder', exact=True).click()

        dialog = self.page.get_by_role('dialog')
        dialog.locator('input').fill(folder_name)
        dialog.get_by_role('button', name='Create').click()

        explorer_tree = self.page.locator('div.ant-tree-list-holder-inner')
        expect(explorer_tree).to_contain_text(folder_name)

        return self

    def create_release(self, notes: str = 'v1.0') -> Self:
        self.page.get_by_role('button', name='Release New Version').click()
        self.page.get_by_role('radio', name='Major Release').check()
        self.page.locator('#notes').fill(notes)
        self.page.get_by_role('button', name='Submit').click()
        return self

    def locate_row(self, name: str) -> Locator:
        return (
            self.page.get_by_role('tree')
            .locator('div.ant-tree-treenode')
            .filter(has=self.page.locator('span.node-name'), has_text=name)
        )

    def move_to_folder(self, names: list[str], folder_name: str) -> Self:
        for name in names:
            self.locate_row(name).locator('span.ant-tree-checkbox').click()

        self.page.get_by_role('button', name='swap Move to', exact=True).click()

        dialog = self.page.get_by_role('dialog')
        dialog.locator('span.ant-tree-switcher').click()
        dialog.locator('span.ant-tree-title').filter(has_text=folder_name).click()
        dialog.get_by_role('button', name='Move to').click()

        return self

    def wait_for_action_completion(self, tab: str, names: list[str], timeout: int = 10000) -> Self:
        self.open_dataset_status_popover(tab)
        for name in names:
            expect(self.page.get_by_role('tabpanel')).to_contain_text(f'{name} - Succeed', timeout=timeout)
        self.page.get_by_role('menuitem', name='Home').click()
        with self.wait_until_refreshed():
            self.page.get_by_role('menuitem', name='Explorer').click()
        return self

    def wait_for_import_completion(self, names: list[str]) -> Self:
        return self.wait_for_action_completion('Import', names)

    def wait_for_move_completion(self, names: list[str]) -> Self:
        return self.wait_for_action_completion('Move', names)

    @contextmanager
    def wait_until_refreshed(self) -> Generator[None]:
        with self.page.expect_response(lambda r: r.url.endswith('/files')):
            yield


@pytest.fixture
def admin_dataset_explorer(admin_page: Page, project_code: str) -> DatasetExplorer:
    return DatasetExplorer(admin_page, project_code)
