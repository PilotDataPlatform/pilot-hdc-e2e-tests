# Copyright (C) 2022-Present Indoc Systems
#
# Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE,
# Version 3.0 (the "License") available at https://www.gnu.org/licenses/agpl-3.0.en.html.
# You may not use this file except in compliance with the License.

import pytest
from mimesis import Generic
from mimesis.locales import Locale


class Fake(Generic):
    pass


@pytest.fixture(scope='session')
def fake() -> Fake:
    return Fake(locale=Locale.EN)
