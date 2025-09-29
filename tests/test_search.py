# Copyright (C) 2022-Present Indoc Systems
#
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE,
# Version 3.0 (the "License") available at https://www.gnu.org/licenses/agpl-3.0.en.html.
# You may not use this file except in compliance with the License.

from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import expect

from tests.fixtures.file_explorer import File
from tests.fixtures.file_explorer import FileExplorer


def test_search_uploaded_file_by_exact_name(
    admin_file_explorer: FileExplorer, admin_page: Page, project_code: str, working_path: Path
) -> None:
    """Test that uploaded file can be found by its name."""

    file = File.generate()
    admin_file_explorer.create_folders_and_upload_file_to(file, working_path / 'file-search')

    admin_page.get_by_role('menuitem', name='Search').click()

    admin_page.locator('div.ant-select').filter(has=admin_page.get_by_role('combobox')).click()
    admin_page.locator('div.ant-select-dropdown').get_by_title('File/Folder Name').click()

    admin_page.locator('div.ant-select').filter(has=admin_page.get_by_role('combobox', name='Condition')).click()
    admin_page.locator('div.ant-select-dropdown').get_by_title('Equals').click()

    admin_page.locator('#fileNameKeyword').fill(file.name)
    admin_page.get_by_role('button', name='search').click()

    expect(admin_page.locator('span.file-name-val').get_by_text(file.name)).to_have_count(1)
