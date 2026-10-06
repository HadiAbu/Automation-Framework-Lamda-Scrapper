from __future__ import annotations

import pytest

from testbed.ports import ReportSink

SINK_KEY: pytest.StashKey[ReportSink] = pytest.StashKey()
