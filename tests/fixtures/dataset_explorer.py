# Copyright (C) 2022-Present Indoc Systems
#
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE,
# Version 3.0 (the "License") available at https://www.gnu.org/licenses/agpl-3.0.en.html.
# You may not use this file except in compliance with the License.

import os
from typing import Annotated
from typing import Self

import pytest
from annotated_types import Len
from playwright.sync_api import Page
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

    def open_dataset(self, dataset_code: str) -> Self:
        with self.page.expect_response(lambda r: r.url.endswith('/files')):
            self.page.goto(f'/dataset/{dataset_code}/data')
        return self


@pytest.fixture
def admin_dataset_explorer(admin_page: Page, project_code: str) -> DatasetExplorer:
    return DatasetExplorer(admin_page, project_code)
