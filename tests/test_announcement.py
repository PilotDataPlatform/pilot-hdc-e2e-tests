# Copyright (C) 2022-Present Indoc Systems
#
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE,
# Version 3.0 (the "License") available at https://www.gnu.org/licenses/agpl-3.0.en.html.
# You may not use this file except in compliance with the License.

from playwright.sync_api import Page
from playwright.sync_api import expect

from tests.fixtures.fake import Fake


def test_announcement_creation(admin_page: Page, project_code: str, fake: Fake) -> None:
    """Test that an announcement can be created and is displayed correctly."""

    admin_page.goto(f'/project/{project_code}/announcement')

    announcement_text = fake.text.sentence()
    admin_page.get_by_role('textbox').fill(announcement_text)
    admin_page.get_by_role('button', name='Publish').click()

    expect(admin_page.get_by_role('heading').first).to_have_text(announcement_text)
