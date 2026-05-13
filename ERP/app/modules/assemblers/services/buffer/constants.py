from __future__ import annotations

import re

PRODUCTION_DONE_STATUS = "завершено"
NOT_SENT_STATUS = "не передано"
NO_MATERIAL_STATUS = "немає"
DEFAULT_EMPTY_VALUE = "—"
ORDER_NUMBER_PATTERN = re.compile(r"\d{3,}")
