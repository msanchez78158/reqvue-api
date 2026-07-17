"""Post-deploy verification: run the two baseline RFQs through the deployed
/parse endpoint and check bid-critical fields against the REQVUE_STATUS.md
baseline (2026-07-08 jobs b1452aac / fca8fb64).

Usage: .venv/bin/python verify_deploy.py [base_url]
Exits nonzero if any document fails its checks.
"""

import json
import sys
import time
import urllib.request

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "https://reqvue-api-production.up.railway.app"
POLL_INTERVAL = 5
POLL_TIMEOUT = 300

# (pdf_path, {field: [needles]}) — each needle must appear in the field value.
# A needle that is itself a list means "any one of these" (dates come back in
# varying but equivalent formats at temperature 0: "07/09/2026" vs "2026-07-09").
CHECKS = [
    (
        "Testing/SPE8E426T1829.PDF",
        {
            "rfq_id_and_org": ["SPE8E4-26-T-1829"],
            "quote_due_date": [["JUN 29", "2026-06-29", "06/29/2026", "June 29"]],
            "part_number_rev": ["9535005962077"],
            "material_and_grade": ["itanium"],
            "dimensions_raw": ["0.025", "36.00", "96.00"],
            "finishing_secondary": ["MIL-STD"],
            "incoterms_fob": ["Origin"],
        },
    ),
    (
        "MODOT 0000000343SL_SUPPLIER.pdf",
        {
            "rfq_id_and_org": ["0000000343SL"],
            "quote_due_date": [["07/09/2026", "2026-07-09", "July 9, 2026"]],
            "delivery_deadline": [["September 29", "2026-09-29", "09/29/2026", "Sep 29"]],
            "qa_certs_required": ["OSHA"],
        },
    ),
]


def submit(pdf_path: str) -> str:
    boundary = "----reqvueverify"
    with open(pdf_path, "rb") as fh:
        pdf_bytes = fh.read()
    filename = pdf_path.split("/")[-1]
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode() + pdf_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{BASE_URL}/parse",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())["job_id"]


def poll(job_id: str) -> dict:
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        with urllib.request.urlopen(f"{BASE_URL}/status/{job_id}", timeout=30) as resp:
            payload = json.loads(resp.read())
        if payload["status"] == "complete":
            return payload["result"]
        if payload["status"] == "failed":
            raise RuntimeError(f"job {job_id} failed: {payload.get('error')}")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"job {job_id} still processing after {POLL_TIMEOUT}s")


def main() -> int:
    failures = 0
    for pdf_path, field_checks in CHECKS:
        print(f"\n=== {pdf_path} ===")
        job_id = submit(pdf_path)
        print(f"job {job_id} submitted, polling...")
        result = poll(job_id)

        populated = sum(1 for k, v in result.items() if v and k != "pages_processed")
        print(f"fields populated: {populated}/16")

        for field, needles in field_checks.items():
            value = str(result.get(field) or "")
            missing = [
                n for n in needles
                if not any(
                    alt.lower() in value.lower()
                    for alt in (n if isinstance(n, list) else [n])
                )
            ]
            if missing:
                failures += 1
                print(f"  FAIL {field}: missing {missing} in {value!r}")
            else:
                print(f"  ok   {field}: {value[:80]}")

    print(f"\n{'PASS' if failures == 0 else 'FAIL'} — {failures} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
