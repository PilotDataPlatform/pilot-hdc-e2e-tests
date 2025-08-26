# Copyright (C) 2022-Present Indoc Systems
#
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE,
# Version 3.0 (the "License") available at https://www.gnu.org/licenses/agpl-3.0.en.html.
# You may not use this file except in compliance with the License.

import hashlib
import os
import re
from pathlib import Path
from typing import Self

from playwright.sync_api import Download
from playwright.sync_api import FilePayload
from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect
from pydantic import BaseModel


class File(BaseModel):
    name: str
    content: bytes
    hash: str
    tags: list[str] = []

    @classmethod
    def generate(cls, *, size_mb: int = 1, name: str | None = None, tags_number: int = 0) -> Self:
        content = os.urandom(size_mb * 1024 * 1024)
        file_hash = hashlib.sha1(content).hexdigest()
        if name is None:
            name = f'e2e-test-{file_hash[:10]}.bin'
        file_tags = [f'tag-{os.urandom(3).hex()}' for _ in range(tags_number)]

        return cls(name=name, content=content, hash=file_hash, tags=file_tags)


class FileExplorer:
    def __init__(self, page: Page) -> None:
        self.page = page

    def open_project(self, project_code: str) -> None:
        self.page.goto(f'/project/{project_code}/data')

    def download(self, names: list[str]) -> Download:
        for name in names:
            self.locate_row(name).get_by_role('checkbox').check()

        with self.page.expect_download() as download_info:
            self.page.get_by_role('button', name='cloud-download Download', exact=True).click()

        return download_info.value

    def download_and_get_hash(self, names: list[str]) -> str:
        download = self.download(names)
        with open(download.path(), 'rb') as f:
            received_file_content = f.read()

        return hashlib.sha1(received_file_content).hexdigest()

    def navigate_to(self, folder_path: Path, *, create_missing_folders: bool = False) -> None:
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

        self.page.get_by_role('button', name='cloud-upload Upload', exact=True).click()


def test_file_upload_and_download(admin_page: Page, project_code: str, working_path: Path) -> None:
    """Test that a file can be uploaded and then downloaded successfully."""

    file_explorer = FileExplorer(admin_page)
    file_explorer.open_project(project_code)
    file_explorer.navigate_to(working_path / 'file-upload', create_missing_folders=True)

    file = File.generate()
    file_explorer.upload_file(file)

    received_file_hash = file_explorer.download_and_get_hash([file.name])

    assert received_file_hash == file.hash


def test_file_upload_with_tags(admin_page: Page, project_code: str, working_path: Path) -> None:
    """Test that a file can be uploaded with tags and those tags are correctly displayed."""

    file_explorer = FileExplorer(admin_page)
    file_explorer.open_project(project_code)
    file_explorer.navigate_to(working_path / 'file-upload', create_missing_folders=True)

    file = File.generate(tags_number=3)
    file_explorer.upload_file(file)

    file_explorer.locate_file(file.name).get_by_label('more').hover()
    admin_page.get_by_role('menuitem', name='Properties').click()
    admin_page.get_by_label('Expand').click()

    received_tags = admin_page.locator('#rawTable-sidePanel span.ant-tag').all_inner_texts()

    assert set(file.tags) == set(received_tags)


def test_file_resumable_upload_and_download(admin_page: Page, project_code: str, working_path: Path) -> None:
    """Test that an interrupted file upload can be resumed and then successfully downloaded."""

    file_explorer = FileExplorer(admin_page)
    file_explorer.open_project(project_code)
    file_explorer.navigate_to(working_path / 'file-resume-upload', create_missing_folders=True)

    admin_page.locator('a.ant-notification-notice-close').click()

    file = File.generate(size_mb=10)
    file_explorer.upload_file(file)

    first_file_status_line = admin_page.get_by_role('heading').first

    expect(first_file_status_line).to_have_text(re.compile(r'Waiting'))
    admin_page.reload()

    admin_page.locator('span.ant-badge-status').click()
    expect(first_file_status_line).to_have_text(re.compile(r'Re-upload file'))

    first_file_status_line.locator('input[type="file"]').set_input_files(
        FilePayload(name=file.name, mimeType='application/octet-stream', buffer=file.content)
    )
    expect(first_file_status_line).to_have_text(re.compile(r'Uploaded'))

    file_explorer.navigate_to(working_path / 'file-resume-upload')

    received_file_hash = file_explorer.download_and_get_hash([file.name])

    assert received_file_hash == file.hash
