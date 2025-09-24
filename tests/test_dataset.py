# Copyright (C) 2022-Present Indoc Systems
#
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE,
# Version 3.0 (the "License") available at https://www.gnu.org/licenses/agpl-3.0.en.html.
# You may not use this file except in compliance with the License.

from playwright.sync_api import Page
from playwright.sync_api import expect

from tests.fixtures.dataset_explorer import Dataset
from tests.fixtures.dataset_explorer import DatasetExplorer


def test_dataset_creation(admin_dataset_explorer: DatasetExplorer, admin_page: Page, project_code: str) -> None:
    """Test that a dataset can be created and is displayed in listing."""

    dataset = Dataset.generate(project_code=project_code)
    admin_dataset_explorer.create_dataset(dataset)

    expect(admin_page.locator('ul.ant-list-items a').first).to_have_text(dataset.title)
