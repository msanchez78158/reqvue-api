# ReqVue status — sanitized technical notes

Real procurement documents, extracted results, and client-specific verification
records were removed from this checkout for portfolio preparation. Their copies
remain in Git history until the owner decides how to handle that history.

## Architecture and existing behavior

- The production extraction path is `POST /parse`, using `extractor.py` and a
  single DeepSeek request through OpenRouter.
- PDF text conversion uses PyMuPDF rather than the earlier Docling stack.
- `trimmer.py` selects scored document chunks before extraction. This is a
  heuristic and can omit relevant content.
- Extracted JSON is validated with Pydantic. The extraction token budget is 6000.
- Job state lives in memory and is lost on restart; it assumes one instance.
- Image-only PDFs have no OCR. Drawing-only information cannot be extracted as text.
- `/parse/v2` depends on optional `agno`, which is intentionally absent from
  `requirements.txt`. Its shipping decision remains open.

## Verification artifacts

`Testing/synthetic_rfq.pdf` contains an explicitly fictional procurement request
with an `example.com` contact. `verify_deploy.py` uses this fixture in place of
private baselines. No live deployment verification was performed during sanitation;
previous results from real documents do not establish results for this fixture.

The exploratory scripts in `Testing/` remain historical experiments and may
require dependencies beyond the production requirements. Their generated document
text and result files are ignored and must not be committed with real data.
