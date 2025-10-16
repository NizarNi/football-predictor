import unittest

from flask import Flask

from football_predictor.app_utils import make_ok, make_error


class TestAppUtils(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def test_make_ok_returns_wrapped_payload_by_default(self):
        payload = {"value": 42}

        with self.app.test_request_context("/api/new-endpoint"):
            response, status_code = make_ok(payload)

        self.assertEqual(status_code, 200)
        self.assertEqual(response.mimetype, "application/json")
        self.assertEqual(
            response.get_json(),
            {"status": "ok", "message": "success", "data": payload},
        )

    def test_make_ok_unwraps_legacy_paths(self):
        payload = {"matches": []}

        with self.app.test_request_context("/upcoming"):
            response, status_code = make_ok(payload)

        self.assertEqual(status_code, 200)
        self.assertEqual(response.mimetype, "application/json")
        self.assertEqual(response.get_json(), payload)

    def test_make_error_returns_wrapped_payload_by_default(self):
        with self.app.test_request_context("/api/new-endpoint"):
            response, status_code = make_error(
                "Something went wrong", message="Failure", status_code=503
            )

        self.assertEqual(status_code, 503)
        self.assertEqual(response.mimetype, "application/json")
        self.assertEqual(
            response.get_json(),
            {
                "status": "error",
                "message": "Failure",
                "error": "Something went wrong",
            },
        )

    def test_make_error_unwraps_for_legacy_prefix(self):
        with self.app.test_request_context("/match/123/xg"):
            response, status_code = make_error(
                "Not found", message="Match not found", status_code=404
            )

        self.assertEqual(status_code, 404)
        self.assertEqual(response.mimetype, "application/json")
        self.assertEqual(
            response.get_json(),
            {"error": "Not found", "message": "Match not found", "ok": False},
        )


if __name__ == "__main__":
    unittest.main()
