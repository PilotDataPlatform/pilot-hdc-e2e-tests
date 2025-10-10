# Copyright (C) 2022-Present Indoc Systems
#
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE,
# Version 3.0 (the "License") available at https://www.gnu.org/licenses/agpl-3.0.en.html.
# You may not use this file except in compliance with the License.
from pathlib import Path

from playwright.sync_api import Page

from tests.fixtures.file_explorer import File
from tests.fixtures.file_explorer import FileExplorer
from tests.fixtures.pilotcli import PilotCLI


def test_project_list(admin_pilotcli: PilotCLI, admin_page: Page, project_code: str) -> None:
    """Test that the project code is in the project list command result."""

    admin_pilotcli.login(admin_page)

    with admin_pilotcli.run('project list') as container:
        stdout = container.wait_for_logs('Project Code')

        assert project_code in stdout


def test_file_is_successfully_downloaded_from_core_zone(
    admin_pilotcli: PilotCLI,
    admin_file_explorer: FileExplorer,
    working_path: Path,
    project_code: str,
    admin_username: str,
) -> None:
    """Test that a file can be downloaded from core zone using pilotcli."""

    full_working_path = working_path / 'pilotcli-download'
    admin_file_explorer.create_folders_in_greenroom_and_core(full_working_path)

    file = File.generate()
    admin_file_explorer.upload_file_and_wait_until_uploaded(file)

    admin_file_explorer.clear_file_status_popover_session_history()
    admin_file_explorer.copy_to_core([file.name], full_working_path)
    admin_file_explorer.wait_for_copy_to_core_completion([file.name])

    admin_pilotcli.login(admin_file_explorer.page)

    source_file_path = f'{project_code}/{admin_username}' / full_working_path / file.name
    destination_file_path = admin_pilotcli.work_dir / file.name

    with admin_pilotcli.run(
        f'file sync --zone core {source_file_path} {admin_pilotcli.work_dir_container}'
    ) as container:
        stdout = container.wait_until_stopped()

        assert 'File has been downloaded successfully' in stdout
        assert file.content == destination_file_path.read_bytes()


def test_file_cannot_be_downloaded_from_greenroom_zone(
    admin_pilotcli: PilotCLI,
    admin_file_explorer: FileExplorer,
    working_path: Path,
    project_code: str,
    admin_username: str,
) -> None:
    """Test that a file cannot be downloaded from greenroom zone using pilotcli."""

    full_working_path = working_path / 'pilotcli-download'
    admin_file_explorer.create_folders_and_navigate_to(full_working_path)

    file = File.generate()
    admin_file_explorer.upload_file_and_wait_until_uploaded(file)

    admin_pilotcli.login(admin_file_explorer.page)

    source_file_path = f'{project_code}/{admin_username}' / full_working_path / file.name
    destination_file_path = admin_pilotcli.work_dir / file.name

    with admin_pilotcli.run(
        f'file sync --zone greenroom {source_file_path} {admin_pilotcli.work_dir_container}'
    ) as container:
        stdout = container.wait_until_stopped()

        assert 'The data zone is invalid. Please verify the data location and try again.' in stdout
        assert not destination_file_path.exists()
