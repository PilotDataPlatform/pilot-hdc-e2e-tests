# Copyright (C) 2022-Present Indoc Systems
#
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE,
# Version 3.0 (the "License") available at https://www.gnu.org/licenses/agpl-3.0.en.html.
# You may not use this file except in compliance with the License.

from playwright.sync_api import Page

from tests.fixtures.pilotcli import PilotCLI


def test_project_list(admin_pilotcli: PilotCLI, admin_page: Page, project_code: str) -> None:
    """Test that the project code is in the project list command result."""

    admin_pilotcli.login(admin_page)

    with admin_pilotcli.run('project list') as container:
        stdout = container.wait_for_logs('Project Code')

        assert project_code in stdout
