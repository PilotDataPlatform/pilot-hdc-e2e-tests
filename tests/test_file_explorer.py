# Copyright (C) 2022-Present Indoc Systems
#
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE,
# Version 3.0 (the "License") available at https://www.gnu.org/licenses/agpl-3.0.en.html.
# You may not use this file except in compliance with the License.

import re
from pathlib import Path

import pytest
from playwright.sync_api import FilePayload
from playwright.sync_api import Page
from playwright.sync_api import expect

from tests.fixtures.fake import Fake
from tests.fixtures.file_explorer import File
from tests.fixtures.file_explorer import FileAttribute
from tests.fixtures.file_explorer import FileExplorer


def test_file_upload_and_download(admin_file_explorer: FileExplorer, working_path: Path) -> None:
    """Test that a file can be uploaded and then downloaded successfully."""

    file = File.generate()
    admin_file_explorer.create_folders_and_upload_file_to(file, working_path / 'file-upload')

    received_file_hash = admin_file_explorer.download_and_get_hash([file.name])

    assert received_file_hash == file.hash


def test_file_upload_with_tags(admin_file_explorer: FileExplorer, working_path: Path) -> None:
    """Test that a file can be uploaded with tags and those tags are correctly displayed."""

    file = File.generate(tags_number=3)
    admin_file_explorer.create_folders_and_upload_file_to(file, working_path / 'file-upload')

    received_tags = admin_file_explorer.get_file_tags(file.name)

    assert set(file.tags) == set(received_tags)


def test_file_upload_with_attributes(
    admin_file_explorer: FileExplorer, admin_page: Page, working_path: Path, fake: Fake
) -> None:
    """Test that a file can be uploaded with specific attributes and those attributes are correctly displayed.

    This test assumes that the project has a file attribute schema named 'Research' with fields 'Country' and 'Comment'.
    """

    country = fake.choice(['Europe', 'NorthAmerica', 'SouthAmerica', 'Asia', 'Africa'])
    comment = fake.text.quote()
    file = File.generate()
    file.attribute = FileAttribute(name='Research', values=[('Country', country), ('Comment', comment)])
    admin_file_explorer.create_folders_and_upload_file_to(file, working_path / 'file-upload')

    admin_file_explorer.locate_file(file.name).get_by_label('more').hover()
    admin_page.get_by_role('menuitem', name='Properties').click()
    admin_page.get_by_role('button', name='General').click()
    admin_page.get_by_role('button', name='File Attributes').click()

    expect(admin_page.get_by_role('heading', name='Research')).to_be_visible()
    expect(admin_page.locator('.ant-collapse-item-active span.ant-descriptions-item-label')).to_contain_text(
        ['Country', 'Comment']
    )
    expect(admin_page.locator('.ant-collapse-item-active span.ant-descriptions-item-content > span')).to_contain_text(
        [country, comment]
    )


def test_folder_upload_and_download(
    admin_file_explorer: FileExplorer, working_path: Path, tmp_path: Path, fake: Fake
) -> None:
    """Test that a folder can be uploaded and then downloaded successfully."""

    admin_file_explorer.create_folders_and_navigate_to(working_path / 'folder-upload')

    folder_name = fake.folder_name()
    folder_path = tmp_path / folder_name
    folder_path.mkdir()

    file_1 = File.generate()
    file_1.save_to_folder(folder_path)
    file_2 = File.generate()
    file_2.save_to_folder(folder_path)

    with admin_file_explorer.wait_until_uploaded_and_available([file_1.name, file_2.name]):
        admin_file_explorer.upload_folder(folder_path)

    received_files = list(admin_file_explorer.download_and_extract_files([folder_name]))

    assert len(received_files) == 2
    assert {file_1.hash, file_2.hash} == {f.hash for f in received_files}


@pytest.mark.skip(reason='Resumable upload has a bug that needs to be fixed')
def test_file_resumable_upload_and_download(
    admin_file_explorer: FileExplorer, admin_page: Page, project_code: str, working_path: Path
) -> None:
    """Test that an interrupted file upload can be resumed and then successfully downloaded."""

    admin_file_explorer.create_folders_and_navigate_to(working_path / 'file-resume-upload')

    file = File.generate(size_kb=4096)
    with admin_page.expect_response(
        lambda r: r.url.endswith(f'project/{project_code}/files') and r.request.method == 'POST'
    ):
        admin_file_explorer.upload_file(file)

    admin_page.reload()

    admin_file_explorer.open_file_status_popover()
    first_file_status_line = admin_page.get_by_role('heading', name=re.compile(r'Re-upload file')).first

    with admin_file_explorer.wait_until_uploaded([file.name]):
        first_file_status_line.locator('input[type="file"]').set_input_files(
            FilePayload(name=file.name, mimeType='application/octet-stream', buffer=file.content)
        )

    admin_file_explorer.navigate_to(working_path / 'file-resume-upload')

    received_file_hash = admin_file_explorer.download_and_get_hash([file.name])

    assert received_file_hash == file.hash


def test_file_with_tags_copy_to_core_zone(admin_file_explorer: FileExplorer, working_path: Path) -> None:
    """Test that a file uploaded with tags is copied to the Core zone together with the tags."""

    full_working_path = working_path / 'file-copy-to-core'
    admin_file_explorer.create_folders_in_greenroom_and_core(full_working_path)

    file = File.generate(tags_number=3)
    admin_file_explorer.upload_file_and_wait_until_uploaded(file)

    admin_file_explorer.copy_to_core([file.name], full_working_path).switch_to_core()

    received_tags = admin_file_explorer.get_file_tags(file.name)

    assert set(file.tags) == set(received_tags)
