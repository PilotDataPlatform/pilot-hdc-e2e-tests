# Copyright (C) 2022-Present Indoc Systems
#
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE,
# Version 3.0 (the "License") available at https://www.gnu.org/licenses/agpl-3.0.en.html.
# You may not use this file except in compliance with the License.

import hashlib
import io
import os
import re
import zipfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated
from typing import Self

import pytest
from annotated_types import Len
from playwright.sync_api import Download
from playwright.sync_api import FilePayload
from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import Response
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect
from pydantic import BaseModel

from tests.fixtures.fake import Fake


class FileAttribute(BaseModel):
    name: str
    values: Annotated[list[tuple[str, str]], Len(min_length=1)]


class File(BaseModel):
    name: str
    content: bytes
    hash: str
    tags: list[str] = []
    attribute: FileAttribute | None = None

    @classmethod
    def generate(cls, *, size_kb: int = 256, name: str | None = None, tags_number: int = 0) -> Self:
        content = os.urandom(size_kb * 1024)
        file_hash = hashlib.sha1(content).hexdigest()
        if name is None:
            name = f'e2e-test-{file_hash[:10]}.bin'
        file_tags = [f'tag-{os.urandom(3).hex()}' for _ in range(tags_number)]

        return cls(name=name, content=content, hash=file_hash, tags=file_tags)

    def save_to_folder(self, folder: Path) -> Path:
        file_path = folder / self.name
        with open(file_path, 'wb') as f:
            f.write(self.content)
        return file_path


class FileExplorer:
    def __init__(self, page: Page) -> None:
        self.page = page

    def open_project(self, project_code: str) -> Self:
        self.page.goto(f'/project/{project_code}/data')
        return self

    def download(self, names: list[str]) -> Download:
        for name in names:
            self.locate_row(name).get_by_role('checkbox').check()

        with self.page.expect_download() as download_info:
            self.page.get_by_role('button', name='cloud-download Download', exact=True).click()

        return download_info.value

    def download_and_get_content(self, names: list[str]) -> bytes:
        download = self.download(names)
        with open(download.path(), 'rb') as f:
            return f.read()

    def download_and_get_hash(self, names: list[str]) -> str:
        file_content = self.download_and_get_content(names)
        return hashlib.sha1(file_content).hexdigest()

    def download_and_extract_files(self, names: list[str]) -> Generator[File]:
        file_content = self.download_and_get_content(names)

        with zipfile.ZipFile(io.BytesIO(file_content)) as zf:
            for fileinfo in zf.infolist():
                if fileinfo.is_dir():
                    continue
                with zf.open(fileinfo.filename) as file:
                    file_content = file.read()
                    file_hash = hashlib.sha1(file_content).hexdigest()
                    yield File(name=fileinfo.filename, content=file_content, hash=file_hash)

    def navigate_to(self, folder_path: Path, *, create_missing_folders: bool = False) -> Self:
        for folder in folder_path.parts:
            try:
                row = self.locate_folder(folder)
            except PlaywrightTimeoutError:
                if not create_missing_folders:
                    raise
                self.create_folder(folder)
                row = self.locate_folder(folder)
            row.get_by_text(folder, exact=True).click()
            expect(self.page.get_by_role('navigation').get_by_role('listitem').last).to_have_text(
                folder, use_inner_text=True
            )
        return self

    def create_folder(self, folder_name: str) -> None:
        self.page.get_by_role('button', name='plus New Folder', exact=True).click()

        dialog = self.page.get_by_role('dialog')
        dialog.locator('input').fill(folder_name)
        dialog.get_by_role('button', name='Create').click()

    def locate_folder(self, name: str) -> Locator:
        return self.locate_row(name, 'folder')

    def locate_file(self, name: str) -> Locator:
        return self.locate_row(name, 'file')

    def locate_row(self, name: str, type_: str | None = None) -> Locator:
        row = self.page.locator('tr.ant-table-row').filter(has=self.page.locator('td:nth-child(4)', has_text=name))
        if type_:
            row = row.filter(has=self.page.get_by_label(type_))
        row.wait_for(state='visible', timeout=10000)
        return row

    def upload_file(self, file: File) -> None:
        self.page.get_by_role('button', name='upload Upload', exact=True).click()

        dialog = self.page.get_by_role('dialog')

        file_input = dialog.locator('#form_in_modal_file')
        file_input.set_input_files(
            FilePayload(name=file.name, mimeType='application/octet-stream', buffer=file.content)
        )

        tags_input = dialog.locator('#form_in_modal_tags')
        for tag in file.tags:
            tags_input.fill(tag)
            tags_input.press('Enter')
            tags_input.press('Escape')

        if file.attribute:
            dialog.locator('#manifest').click()
            self.page.locator('.ant-select-dropdown').get_by_title(file.attribute.name, exact=True).click()
            file_attribute_form = dialog.locator('#manifest-form')
            for attribute_key, attribute_value in file.attribute.values:
                value_input = file_attribute_form.locator(f'#{attribute_key}')
                dropdown_id = value_input.get_attribute('aria-controls')
                if dropdown_id is None:
                    value_input.fill(attribute_value)
                    continue

                value_input.click()
                file_attribute_form.get_by_title(attribute_value).click()

        self.page.get_by_role('button', name='cloud-upload Upload', exact=True).click()

    def upload_folder(self, folder_path: Path) -> None:
        self.page.get_by_role('button', name='upload Upload', exact=True).click()

        dialog = self.page.get_by_role('dialog')

        folder_input = dialog.locator('#form_in_modal_folder')
        folder_input.set_input_files(folder_path)

        self.page.get_by_role('button', name='cloud-upload Upload', exact=True).click()

    @contextmanager
    def wait_until_uploaded(self, names: list[str], wait_for_refresh: bool = True) -> Generator[None]:
        files_to_upload = set(names)

        def check_response(response: Response) -> bool:
            if response.url.endswith('pilot/upload/gr/v1/files') and response.request.method == 'POST':
                filename = response.request.post_data_json['resumable_filename']
                if filename in files_to_upload:
                    files_to_upload.remove(filename)

            if files_to_upload:
                return False

            if not wait_for_refresh:
                return True

            return 'v1/files/meta?' in response.url

        with self.page.expect_response(check_response):
            yield


def test_file_upload_and_download(admin_page: Page, project_code: str, working_path: Path) -> None:
    """Test that a file can be uploaded and then downloaded successfully."""

    file_explorer = FileExplorer(admin_page)
    file_explorer.open_project(project_code).navigate_to(working_path / 'file-upload', create_missing_folders=True)

    file = File.generate()
    with file_explorer.wait_until_uploaded([file.name]):
        file_explorer.upload_file(file)

    received_file_hash = file_explorer.download_and_get_hash([file.name])

    assert received_file_hash == file.hash


def test_file_upload_with_tags(admin_page: Page, project_code: str, working_path: Path) -> None:
    """Test that a file can be uploaded with tags and those tags are correctly displayed."""

    file_explorer = FileExplorer(admin_page)
    file_explorer.open_project(project_code).navigate_to(working_path / 'file-upload', create_missing_folders=True)

    file = File.generate(tags_number=3)
    with file_explorer.wait_until_uploaded([file.name]):
        file_explorer.upload_file(file)

    file_explorer.locate_file(file.name).get_by_label('more').hover()
    admin_page.get_by_role('menuitem', name='Properties').click()
    admin_page.get_by_label('Expand').click()

    received_tags = admin_page.locator('#rawTable-sidePanel span.ant-tag').all_inner_texts()

    assert set(file.tags) == set(received_tags)


def test_file_upload_with_attributes(admin_page: Page, project_code: str, working_path: Path, fake: Fake) -> None:
    """Test that a file can be uploaded with specific attributes and those attributes are correctly displayed.

    This test assumes that the project has a file attribute schema named 'Research' with fields 'Country' and 'Comment'.
    """

    file_explorer = FileExplorer(admin_page)
    file_explorer.open_project(project_code).navigate_to(working_path / 'file-upload', create_missing_folders=True)

    country = fake.choice(['Europe', 'NorthAmerica', 'SouthAmerica', 'Asia', 'Africa'])
    comment = fake.text.quote()
    file = File.generate()
    file.attribute = FileAttribute(name='Research', values=[('Country', country), ('Comment', comment)])
    with file_explorer.wait_until_uploaded([file.name]):
        file_explorer.upload_file(file)

    file_explorer.locate_file(file.name).get_by_label('more').hover()
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


def test_folder_upload_and_download(admin_page: Page, project_code: str, working_path: Path, tmp_path: Path) -> None:
    """Test that a folder can be uploaded and then downloaded successfully."""

    file_explorer = FileExplorer(admin_page)
    file_explorer.open_project(project_code).navigate_to(working_path / 'folder-upload', create_missing_folders=True)

    folder_name = f'e2e-test-{os.urandom(5).hex()}'
    folder_path = tmp_path / folder_name
    folder_path.mkdir()

    file_1 = File.generate()
    file_1.save_to_folder(folder_path)
    file_2 = File.generate()
    file_2.save_to_folder(folder_path)

    with file_explorer.wait_until_uploaded([file_1.name, file_2.name]):
        file_explorer.upload_folder(folder_path)

    received_files = list(file_explorer.download_and_extract_files([folder_name]))

    assert len(received_files) == 2
    assert {file_1.hash, file_2.hash} == {f.hash for f in received_files}


@pytest.mark.skip(reason='Resumable upload has a bug that needs to be fixed')
def test_file_resumable_upload_and_download(admin_page: Page, project_code: str, working_path: Path) -> None:
    """Test that an interrupted file upload can be resumed and then successfully downloaded."""

    file_explorer = FileExplorer(admin_page)
    file_explorer.open_project(project_code).navigate_to(
        working_path / 'file-resume-upload', create_missing_folders=True
    )

    file = File.generate(size_kb=4096)
    with admin_page.expect_response(
        lambda r: r.url.endswith(f'project/{project_code}/files') and r.request.method == 'POST'
    ):
        file_explorer.upload_file(file)

    admin_page.reload()

    admin_page.locator('span.ant-badge-status').click()
    first_file_status_line = admin_page.get_by_role('heading', name=re.compile(r'Re-upload file')).first

    with file_explorer.wait_until_uploaded([file.name], wait_for_refresh=False):
        first_file_status_line.locator('input[type="file"]').set_input_files(
            FilePayload(name=file.name, mimeType='application/octet-stream', buffer=file.content)
        )

    file_explorer.navigate_to(working_path / 'file-resume-upload')

    received_file_hash = file_explorer.download_and_get_hash([file.name])

    assert received_file_hash == file.hash
