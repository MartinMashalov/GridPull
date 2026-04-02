from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from app.services.sov.pipeline import _parse_json_content


class SovJsonParsingTests(unittest.TestCase):
    def test_parses_list_based_text_blocks(self) -> None:
        parsed = _parse_json_content(
            [
                {"type": "text", "text": '{"keep_indices": [1, 2, 4]}'},
            ]
        )

        self.assertEqual(parsed["keep_indices"], [1, 2, 4])

    def test_parses_code_fenced_json_with_trailing_commas(self) -> None:
        parsed = _parse_json_content(
            """Here is the extraction result:

```json
{"records": [{"Location Number": "100", "Building Value": "150000",}],}
```
"""
        )

        self.assertEqual(parsed["records"][0]["Location Number"], "100")
        self.assertEqual(parsed["records"][0]["Building Value"], "150000")

    def test_parses_json_object_embedded_in_extra_text(self) -> None:
        parsed = _parse_json_content(
            'Result: {"records": [{"Location Number": "200"}]} End of response.'
        )

        self.assertEqual(parsed["records"][0]["Location Number"], "200")


if __name__ == "__main__":
    unittest.main()
