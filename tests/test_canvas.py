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


def test_file_upload_and_download_events_listed_in_recent_file_stream(
    admin_file_explorer: FileExplorer, admin_page: Page, project_code: str, working_path: Path
) -> None:
    """Test that file upload and download events are listed in the recent file activity stream."""

    file = File.generate()
    admin_file_explorer.create_folders_and_upload_file_to(file, working_path / 'file-activity-stream')
    admin_file_explorer.download([file.name])

    with admin_page.expect_response(lambda r: '/users?' in r.url):
        admin_page.goto(f'/project/{project_code}/canvas')

    with admin_page.expect_response(lambda r: 'v1/project/activity-logs/' in r.url):
        admin_page.get_by_text('Advanced Search', exact=True).click()

    for action, event in [('Upload', 'uploaded'), ('Download', 'downloaded')]:
        admin_page.locator('div.ant-select').filter(has=admin_page.get_by_role('combobox', name='Type')).click()
        admin_page.locator('div.ant-select-dropdown').get_by_title(action).click()
        admin_page.get_by_role('button', name='Search').click()
        expect(admin_page.get_by_text(f'{event} {file.name} at')).to_have_count(1)
