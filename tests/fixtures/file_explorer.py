# Copyright (C) 2022-Present Indoc Systems
#
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE,
# Version 3.0 (the "License") available at https://www.gnu.org/licenses/agpl-3.0.en.html.
# You may not use this file except in compliance with the License.

import hashlib
import io
import os
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
from pydantic import RootModel


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
    def generate(cls, *, size_kb: int = 64, name: str | None = None, tags_number: int = 0) -> Self:
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


class Files(RootModel[Annotated[list[File], Len(min_length=1)]]):
    def __getitem__(self, item: int) -> File:
        return self.root[item]

    @property
    def tags(self) -> list[str]:
        return self[0].tags

    @property
    def attribute(self) -> FileAttribute | None:
        return self[0].attribute

    @property
    def names(self) -> list[str]:
        return [file.name for file in self.root]

    @property
    def payloads(self) -> list[FilePayload]:
        return [
            FilePayload(name=file.name, mimeType='application/octet-stream', buffer=file.content) for file in self.root
        ]

    @classmethod
    def generate(cls, number: int) -> Self:
        return cls([File.generate() for _ in range(number)])


class FileExplorer:
    def __init__(self, page: Page, project_code: str) -> None:
        self.page = page
        self.project_code = project_code

    def open(self) -> Self:
        url = f'/project/{self.project_code}/data'
        if not self.page.url.endswith(url):
            with self.wait_until_refreshed():
                self.page.goto(url)
        return self

    def toggle_file_status_popover(self, is_open: bool) -> Self:
        menuitem = self.page.get_by_role('menuitem').filter(has=self.page.locator('span.ant-badge-status'))
        if (menuitem.locator('div.ant-popover-open').count() == 1) != is_open:
            menuitem.click()
        return self

    def open_file_status_popover(self) -> Self:
        return self.toggle_file_status_popover(True)

    def close_file_status_popover(self) -> Self:
        return self.toggle_file_status_popover(False)

    def download(self, names: list[str]) -> Download:
        self.close_file_status_popover()

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

    def copy_to_core(self, names: list[str], core_folder_path: Path) -> Self:
        for name in names:
            self.locate_row(name).get_by_role('checkbox').check()

        self.page.get_by_role('button', name='copy Copy To Core', exact=True).click()
        self.page.get_by_role('button', name='Copy to Core', exact=True).click()

        dialog = self.page.get_by_role('dialog')
        dialog.get_by_role('button', name='Select Destination').click()

        dialog.locator('div.ant-tree-treenode').filter(has=self.page.get_by_role('img', name='user')).click()
        self.select_path_in_dialog_tree(dialog, core_folder_path)
        dialog.get_by_role('button', name='Select').click()

        code = dialog.locator('b').inner_text()
        dialog.locator('input').fill(code)

        dialog.get_by_role('button', name='Confirm').click()
        dialog.get_by_text('Close').click()

        return self

    def add_to_dataset(self, names: list[str], dataset_code: str) -> Self:
        for name in names:
            self.locate_row(name).get_by_role('checkbox').check()

        self.page.get_by_role('button', name='ellipsis').hover()
        self.page.locator('div.ant-dropdown').get_by_role('button', name='Add to Datasets').click()
        self.page.locator('div.file_explorer_header_bar').get_by_role('button', name='Add to Datasets').click()

        dialog = self.page.get_by_role('dialog')
        dialog.locator('div.ant-select').filter(
            has=self.page.get_by_role('combobox'), has_text='Select Dataset'
        ).click()
        self.page.locator('div.ant-select-dropdown').get_by_title(dataset_code).click()

        with self.page.expect_response(lambda r: r.url.endswith('/files') and r.request.method == 'PUT'):
            dialog.get_by_role('button', name='Add to Dataset').click()

        return self

    def maximize_page_size(self) -> Self:
        active_tab = self.page.locator('div.ant-tabs-tabpane-active')
        if active_tab.locator('li.ant-pagination-item').count() > 1:
            active_tab.locator('li.ant-pagination-options div.ant-select').click()
            with self.wait_until_refreshed():
                active_tab.locator('div.ant-select-dropdown div.ant-select-item').last.click()
        return self

    def navigate_to(self, folder_path: Path) -> Self:
        for folder in folder_path.parts:
            self.maximize_page_size()
            self.locate_folder(folder).get_by_text(folder, exact=True).click()
            expect(self.page.get_by_role('navigation').get_by_role('listitem').last).to_have_text(
                folder, use_inner_text=True
            )
        return self

    def create_folders_and_navigate_to(self, folder_path: Path) -> Self:
        self.open()
        for folder in folder_path.parts:
            self.maximize_page_size()
            try:
                row = self.locate_folder(folder)
                row.wait_for(timeout=2000)
            except PlaywrightTimeoutError:
                self.create_folder(folder)
                row = self.locate_folder(folder)
            row.get_by_text(folder, exact=True).click()
            expect(self.page.get_by_role('navigation').get_by_role('listitem').last).to_have_text(
                folder, use_inner_text=True
            )
        return self

    def create_folders_and_upload_file_to(self, file: File, folder_path: Path) -> Self:
        self.create_folders_and_navigate_to(folder_path)
        return self.upload_file_and_wait_until_uploaded(file)

    def create_folders_in_greenroom_and_core(self, folder_path: Path) -> Self:
        self.create_folders_and_navigate_to(folder_path).switch_to_core()
        self.create_folders_and_navigate_to(folder_path).switch_to_green_room()
        return self

    def wait_for_stable_count(
        self, locator: Locator, interval: int = 350, timeout: int = 5000, max_stable_rounds: int = 5
    ) -> Self:
        previous_count = -1
        stable_rounds = 0
        elapsed_time = 0

        while elapsed_time < timeout and stable_rounds < max_stable_rounds:
            current_count = locator.count()
            if current_count == previous_count:
                stable_rounds += 1
            else:
                stable_rounds = 0
                previous_count = current_count

            self.page.wait_for_timeout(interval)
            elapsed_time += interval

        return self

    def switch_to_tab(self, class_name: str, tab_title: str) -> Self:
        self.page.get_by_role('tree').locator(f':scope.{class_name}').get_by_title('Home').click()
        expect(self.page.locator('div.ant-spin-blur')).to_have_count(0)
        expect(self.page.get_by_role('tab', selected=True)).to_have_text(tab_title)
        return self

    def close_current_tab(self) -> Self:
        with self.wait_until_refreshed():
            self.page.locator('div.ant-tabs-tab').filter(has=self.page.get_by_role('tab', selected=True)).get_by_label(
                'remove'
            ).click()
        return self

    def switch_to_core(self) -> Self:
        return self.switch_to_tab('core', 'Core - Home')

    def switch_to_green_room(self) -> Self:
        return self.switch_to_tab('green_room', 'Green Room - Home')

    def navigate_back(self) -> Self:
        self.page.get_by_role('navigation').get_by_role('listitem').nth(-2).locator('span.ant-breadcrumb-link').click()
        return self

    def create_folder(self, folder_name: str) -> Self:
        self.page.get_by_role('button', name='plus New Folder', exact=True).click()

        dialog = self.page.get_by_role('dialog')
        dialog.locator('input').fill(folder_name)
        dialog.get_by_role('button', name='Create').click()

        active_tab = self.page.locator('div.ant-tabs-tabpane-active div.ant-table')
        expect(active_tab).to_contain_text(folder_name)

        return self

    def locate_folder(self, name: str) -> Locator:
        return self.locate_row(name, 'folder')

    def locate_file(self, name: str) -> Locator:
        return self.locate_row(name, 'file')

    def locate_row(self, name: str, type_: str | None = None) -> Locator:
        row = (
            self.page.get_by_role('tabpanel')
            .locator('tr.ant-table-row')
            .filter(has=self.page.locator('td:nth-child(4)', has_text=name))
        )
        if type_:
            row = row.filter(has=self.page.get_by_label(type_))
        return row

    def get_file_tags(self, file_name: str) -> list[str]:
        self.locate_file(file_name).get_by_label('more').hover()
        self.page.get_by_role('menuitem', name='Properties').click()
        self.page.get_by_label('Expand').click()
        received_tags = self.page.locator('#rawTable-sidePanel span.ant-tag').all_inner_texts()
        return received_tags

    def upload_file(self, file: File) -> Self:
        return self.upload_files(Files([file]))

    def upload_files(self, files: Files) -> Self:
        self.page.get_by_role('button', name='upload Upload', exact=True).click()

        dialog = self.page.get_by_role('dialog')

        file_input = dialog.locator('#form_in_modal_file')
        file_input.set_input_files(files.payloads)

        tags_input = dialog.locator('#form_in_modal_tags')
        tags_input.focus()
        for tag in files.tags:
            tags_input.fill(tag)
            tags_input.press('Enter')
            tags_input.press('Escape')

        if files.attribute:
            dialog.locator('#manifest').click()
            self.page.locator('.ant-select-dropdown').get_by_title(files.attribute.name, exact=True).click()
            file_attribute_form = dialog.locator('#manifest-form')
            for attribute_key, attribute_value in files.attribute.values:
                value_input = file_attribute_form.locator(f'#{attribute_key}')
                dropdown_id = value_input.get_attribute('aria-controls')
                if dropdown_id is None:
                    value_input.fill(attribute_value)
                    continue

                value_input.click()
                file_attribute_form.get_by_title(attribute_value).click()

        self.page.get_by_role('button', name='cloud-upload Upload', exact=True).click()

        return self

    def upload_file_and_wait_until_uploaded(self, file: File) -> Self:
        with self.wait_until_uploaded([file.name]):
            self.upload_file(file)
        return self

    def upload_files_and_wait_until_uploaded(self, files: Files) -> Self:
        with self.wait_until_uploaded(files.names):
            self.upload_files(files)
        return self

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

    @contextmanager
    def wait_until_refreshed(self) -> Generator[None]:
        with self.page.expect_response(lambda r: 'v1/files/meta?' in r.url and 'order_by=created_time' in r.url):
            yield

    def select_path_in_dialog_tree(self, dialog: Locator, folder_path: Path, start_level: int = 3) -> Self:
        path_parts = list(folder_path.parts)
        while path_parts:
            available_folders = dialog.locator('div.ant-tree-treenode').filter(
                has=self.page.locator('span.ant-tree-indent-unit')
            )
            self.wait_for_stable_count(available_folders)

            folders = {}
            for folder in available_folders.all():
                if folder.locator('span.ant-tree-indent-unit').count() == start_level:
                    folder_name = folder.locator('span.ant-tree-title').inner_text()
                    folders[folder_name] = folder

            try:
                folders[path_parts[0]].click()
                path_parts.pop(0)
                start_level += 1
            except KeyError:
                folders['...'].click()

        return self


@pytest.fixture
def admin_file_explorer(admin_page: Page, project_code: str) -> FileExplorer:
    return FileExplorer(admin_page, project_code)
