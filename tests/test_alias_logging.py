import logging
import unittest

from football_predictor.name_resolver import alias_logging_context, resolve_team_name


class AliasLoggingTests(unittest.TestCase):
    def test_alias_summary_and_debug_records(self):
        with self.assertLogs("football_predictor.name_resolver", level="DEBUG") as capture:
            with alias_logging_context():
                resolve_team_name("Manchester Utd", provider="fbref")
                resolve_team_name("Man United", provider=None)
                resolve_team_name("Manchester Utd", provider="fbref")  # duplicate mapping

        debug_logs = [
            record.getMessage()
            for record in capture.records
            if record.levelno == logging.DEBUG and "alias" in record.getMessage()
        ]
        info_logs = [
            record.getMessage()
            for record in capture.records
            if record.levelno == logging.INFO and "alias_normalizer" in record.getMessage()
        ]

        self.assertEqual(len(info_logs), 1)
        summary = info_logs[0]
        self.assertIn("applied 2 unique mappings", summary)
        self.assertIn("providers: _, fbref", summary)
        self.assertEqual(len(debug_logs), 3)
        self.assertTrue(any("provider=fbref" in msg for msg in debug_logs))


if __name__ == "__main__":
    unittest.main()
