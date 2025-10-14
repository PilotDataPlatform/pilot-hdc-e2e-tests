# Copyright (C) 2022-Present Indoc Systems
#
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE,
# Version 3.0 (the "License") available at https://www.gnu.org/licenses/agpl-3.0.en.html.
# You may not use this file except in compliance with the License.

from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import expect

from tests.fixtures.dataset_explorer import Dataset
from tests.fixtures.dataset_explorer import DatasetExplorer
from tests.fixtures.fake import Fake
from tests.fixtures.file_explorer import File
from tests.fixtures.file_explorer import FileExplorer
from tests.fixtures.file_explorer import Files


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
    admin_file_explorer.create_folders_and_upload_files_and_add_to_dataset(
        full_working_path, Files([file]), dataset.code
    )
    admin_dataset_explorer.open(dataset.code).wait_for_import_completion([file.name])

    explorer_tree = admin_page.locator('div.ant-tree-list-holder-inner')
    expect(explorer_tree).to_contain_text(file.name)


def test_add_folder_with_files_to_dataset(
    admin_dataset_explorer: DatasetExplorer,
    admin_file_explorer: FileExplorer,
    admin_page: Page,
    project_code: str,
    working_path: Path,
    tmp_path: Path,
    fake: Fake,
) -> None:
    """Test that a folder with files can be added to a dataset and is displayed in the dataset explorer."""

    dataset = Dataset.generate(project_code=project_code)
    admin_dataset_explorer.create_dataset(dataset)

    full_working_path = working_path / 'folders-for-dataset'
    admin_file_explorer.create_folders_in_greenroom_and_core(full_working_path)

    folder_name = fake.folder_name()
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
    admin_dataset_explorer.open(dataset.code).wait_for_import_completion([folder_name])

    explorer_tree = admin_page.locator('div.ant-tree-list-holder-inner')
    expect(explorer_tree).to_contain_text(folder_name)

    admin_page.locator('div.ant-tree-treenode').filter(has_text=folder_name).locator('span.ant-tree-switcher').click()
    expect(explorer_tree).to_contain_text(file_1.name)
    expect(explorer_tree).to_contain_text(file_2.name)


def test_new_folder_and_file_move_in_dataset(
    admin_dataset_explorer: DatasetExplorer,
    admin_file_explorer: FileExplorer,
    admin_page: Page,
    project_code: str,
    working_path: Path,
    fake: Fake,
) -> None:
    """Test that a new folder can be created in a dataset and a file can be moved into that folder."""

    dataset = Dataset.generate(project_code=project_code)
    admin_dataset_explorer.create_dataset(dataset)

    full_working_path = working_path / 'files-for-dataset'
    files = Files.generate(2)
    admin_file_explorer.create_folders_and_upload_files_and_add_to_dataset(full_working_path, files, dataset.code)
    admin_dataset_explorer.open(dataset.code).wait_for_import_completion(files.names)

    file_to_move = files[0]
    dataset_folder_name = fake.folder_name()
    admin_dataset_explorer.create_folder(dataset_folder_name)
    admin_dataset_explorer.move_to_folder([file_to_move.name], dataset_folder_name)
    admin_dataset_explorer.wait_for_move_completion([file_to_move.name])

    explorer_tree = admin_page.locator('div.ant-tree-list-holder-inner')
    expect(explorer_tree).not_to_contain_text(file_to_move.name)

    admin_page.locator('div.ant-tree-treenode').filter(has_text=dataset_folder_name).locator(
        'span.ant-tree-switcher'
    ).click()
    expect(explorer_tree).to_contain_text(file_to_move.name)


def test_dataset_release_and_download(
    admin_dataset_explorer: DatasetExplorer,
    admin_file_explorer: FileExplorer,
    admin_page: Page,
    project_code: str,
    working_path: Path,
    fake: Fake,
) -> None:
    """Test that a new version of a dataset can be released and then downloaded."""

    dataset = Dataset.generate(project_code=project_code)
    admin_dataset_explorer.create_dataset(dataset)

    full_working_path = working_path / 'files-for-dataset'
    file = File.generate()
    admin_file_explorer.create_folders_and_upload_files_and_add_to_dataset(
        full_working_path, Files([file]), dataset.code
    )
    admin_dataset_explorer.open(dataset.code).wait_for_import_completion([file.name])

    admin_page.get_by_role('button', name='Release New Version').click()
    admin_page.get_by_role('radio', name='Major Release').check()
    admin_page.locator('#notes').fill('v1.0')
    admin_page.get_by_role('button', name='Submit').click()

    versions_button = admin_page.locator('div.ant-page-header-heading').get_by_text('Versions', exact=True)
    versions_button.click()

    dialog = admin_page.get_by_role('dialog')
    download_button = dialog.get_by_role('button', name='Download')
    for _ in admin_dataset_explorer.wait_with_retries(lambda: download_button.is_visible()):
        dialog.get_by_role('button', name='Close').click()
        versions_button.click()

    with admin_page.expect_download() as download_info:
        download_button.click()

    received_files = list(admin_file_explorer.extract_files(download_info.value.path()))

    assert len(received_files) == 2  # 2nd file here is default_essential.schema.json
    assert file.hash in {f.hash for f in received_files}
