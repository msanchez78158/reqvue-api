import asyncio
import json
import unittest
from unittest.mock import Mock, patch

# These JSON/CORS tests do not exercise PDF conversion. Isolate its optional
# layout-model imports while keeping the real API, extractor, and schemas.
pdf_conversion = patch.dict("sys.modules", {"pymupdf4llm": Mock()})
pdf_conversion.start()
unittest.addModuleCleanup(pdf_conversion.stop)
import main
from models import RFQBrief


async def request(method, path, chunks=(), headers=()):
    """Exercise the ASGI app with separate body chunks and no Content-Length."""
    messages = [
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ] or [{"type": "http.request", "body": b"", "more_body": False}]
    received = []
    sent = []

    async def receive():
        received.append(True)
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": "http", "path": path,
        "raw_path": path.encode(), "query_string": b"", "root_path": "",
        "headers": list(headers), "server": ("testserver", 80),
        "client": ("127.0.0.1", 12345),
    }
    await main.app(scope, receive, send)
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return start["status"], dict(start["headers"]), body, len(received)


class ParseTests(unittest.TestCase):
    def setUp(self):
        main.JOB_STORE.clear()

    def tearDown(self):
        main.JOB_STORE.clear()

    def call(self, method, path, chunks=(), headers=()):
        return asyncio.run(request(method, path, chunks, headers))

    def post_json(self, chunks, headers=()):
        return self.call("POST", "/parse", chunks, ((b"content-type", b"application/json"), *headers))

    def test_json_round_trip_uses_mocked_extractor(self):
        with patch.object(main, "extract_rfq_brief", return_value=RFQBrief(estimator_summary="Fictional brief")) as extract:
            status, _, body, _ = self.post_json([b'{"text":"Fictional RFQ"}'])
        self.assertEqual(status, 200)
        submitted = json.loads(body)
        self.assertEqual(submitted["status"], "processing")
        extract.assert_called_once_with(document_name="submitted_text", document_text="Fictional RFQ")
        status, _, body, _ = self.call("GET", "/status/" + submitted["job_id"])
        completed = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(completed["status"], "complete")
        self.assertEqual(completed["result"]["estimator_summary"], "Fictional brief")
        self.assertIsNone(completed["result"]["pages_processed"])
        self.assertEqual(len(completed["result"]), 17)

    def test_json_at_and_below_limit_is_accepted(self):
        for length in (63, 64):
            with self.subTest(length=length), patch.object(main, "MAX_UPLOAD_BYTES", 64), patch.object(main, "process_document") as process:
                body = b'{"text":"' + b"x" * (length - len(b'{"text":""}')) + b'"}'
                chunks = [body[index:index + 7] for index in range(0, len(body), 7)]
                status, _, _, _ = self.post_json(chunks)
                self.assertEqual(status, 200)
                process.assert_called_once()

    def test_oversized_chunked_json_stops_before_extraction(self):
        chunks = [b'{"text":"' + b"x" * 11] + [b"x" * 20] * 5 + [b'"}']
        with patch.object(main, "MAX_UPLOAD_BYTES", 64), patch.object(main, "process_document") as process:
            status, _, body, consumed = self.post_json(chunks)
        self.assertEqual(status, 413)
        self.assertLess(consumed, len(chunks))
        self.assertIn("limit", json.loads(body)["detail"])
        process.assert_not_called()
        self.assertEqual(main.JOB_STORE, {})

    def test_false_content_length_cannot_bypass_actual_body_limit(self):
        with patch.object(main, "MAX_UPLOAD_BYTES", 16), patch.object(main, "process_document") as process:
            status, _, _, _ = self.post_json([b'{"text":"' + b"x" * 20 + b'"}'], [(b"content-length", b"1")])
        self.assertEqual(status, 413)
        process.assert_not_called()

    def test_json_limit_counts_utf8_bytes_and_other_fields(self):
        bodies = ['{"text":"éééééééééé"}'.encode(), b'{"text":"ok","extra":"' + b"x" * 20 + b'"}']
        for body in bodies:
            with self.subTest(size=len(body)), patch.object(main, "MAX_UPLOAD_BYTES", 24), patch.object(main, "process_document") as process:
                status, _, _, _ = self.post_json([body])
                self.assertEqual(status, 413)
                process.assert_not_called()

    def test_invalid_or_missing_text_is_rejected(self):
        bodies = [b'{', b'\xff', b'[]', b'{}', b'{"text":null}', b'{"text":42}', b'{"text":[]}', b'{"text":""}', b'{"text":"   "}']
        for body in bodies:
            with self.subTest(body=body), patch.object(main, "process_document") as process:
                status, _, _, _ = self.post_json([body])
                self.assertEqual(status, 400)
                process.assert_not_called()
                self.assertEqual(main.JOB_STORE, {})

    def test_wrong_content_type_is_rejected(self):
        status, _, _, _ = self.call("POST", "/parse", [b"Fictional RFQ"], [(b"content-type", b"text/plain")])
        self.assertEqual(status, 400)

    def test_cors_allows_only_named_origins(self):
        for origin in ("https://redomaworks.com", "https://www.redomaworks.com"):
            with self.subTest(origin=origin):
                status, headers, _, _ = self.call("OPTIONS", "/parse", headers=[
                    (b"origin", origin.encode()), (b"access-control-request-method", b"POST"),
                ])
                self.assertEqual(status, 200)
                self.assertEqual(headers[b"access-control-allow-origin"], origin.encode())
        for origin in ("https://untrusted.example", "http://redomaworks.com", "http://localhost:3000"):
            with self.subTest(origin=origin):
                status, headers, _, _ = self.call("OPTIONS", "/parse", headers=[
                    (b"origin", origin.encode()), (b"access-control-request-method", b"POST"),
                ])
                self.assertEqual(status, 400)
                self.assertNotIn(b"access-control-allow-origin", headers)


if __name__ == "__main__":
    unittest.main()
