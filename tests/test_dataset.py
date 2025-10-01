# Copyright (C) 2022-Present Indoc Systems
#
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE,
# Version 3.0 (the "License") available at https://www.gnu.org/licenses/agpl-3.0.en.html.
# You may not use this file except in compliance with the License.

import os
from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import expect

from tests.fixtures.dataset_explorer import Dataset
from tests.fixtures.dataset_explorer import DatasetExplorer
from tests.fixtures.file_explorer import File
from tests.fixtures.file_explorer import FileExplorer


def test_dataset_creation(admin_dataset_explorer: DatasetExplorer, admin_page: Page, project_code: str) -> None:
    """Test that a dataset can be created and is displayed in listing."""

    dataset = Dataset.generate(project_code=project_code)
    admin_dataset_explorer.create_dataset(dataset)

    expect(admin_page.locator('ul.ant-list-items a').first).to_have_text(dataset.title)


def test_add_file_to_dataset(
    admin_dataset_explorer: DatasetExplorer,
    admin_file_explorer: FileExplorer,
    admin_page: Page,
    project_code: str,
    working_path: Path,
) -> None:
    """Test that a file can be added to a dataset and is displayed in the dataset explorer."""

    dataset = Dataset.generate(project_code=project_code)
    admin_dataset_explorer.create_dataset(dataset)

    full_working_path = working_path / 'files-for-dataset'
    file = File.generate()
    admin_file_explorer.create_folders_and_upload_file_to(file, full_working_path).switch_to_core()
    admin_file_explorer.create_folders_and_navigate_to(full_working_path).switch_to_green_room()
    admin_file_explorer.copy_to_core([file.name], full_working_path).switch_to_core()
    admin_file_explorer.add_to_dataset([file.name], dataset.code)
    admin_dataset_explorer.wait_for_import_completion(dataset.code, [file.name])

    explorer_tree = admin_page.locator('div.ant-tree-list-holder-inner')
    expect(explorer_tree).to_contain_text(file.name)


def test_add_folder_with_files_to_dataset(
    admin_dataset_explorer: DatasetExplorer,
    admin_file_explorer: FileExplorer,
    admin_page: Page,
    project_code: str,
    working_path: Path,
    tmp_path: Path,
) -> None:
    dataset = Dataset.generate(project_code=project_code)
    admin_dataset_explorer.create_dataset(dataset)

    full_working_path = working_path / 'folders-for-dataset'
    admin_file_explorer.create_folders_in_greenroom_and_core(full_working_path)

    folder_name = f'e2e-test-{os.urandom(5).hex()}'
    folder_path = tmp_path / folder_name
    folder_path.mkdir()

    file_1 = File.generate()
    file_1.save_to_folder(folder_path)
    file_2 = File.generate()
    file_2.save_to_folder(folder_path)

    with admin_file_explorer.wait_until_uploaded([file_1.name, file_2.name]):
        admin_file_explorer.upload_folder(folder_path)

    admin_file_explorer.copy_to_core([folder_name], full_working_path).switch_to_core()
    admin_file_explorer.add_to_dataset([folder_name], dataset.code)
    admin_dataset_explorer.wait_for_import_completion(dataset.code, [folder_name])

    explorer_tree = admin_page.locator('div.ant-tree-list-holder-inner')
    expect(explorer_tree).to_contain_text(folder_name)

    admin_page.locator('div.ant-tree-treenode').filter(has_text=folder_name).locator('span.ant-tree-switcher').click()
    expect(explorer_tree).to_contain_text(file_1.name)
    expect(explorer_tree).to_contain_text(file_2.name)
