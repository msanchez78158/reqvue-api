# ReqVue status — sanitized technical notes

Extracted results, exploratory scripts, and client-specific verification records
were removed for portfolio preparation. The owner explicitly retained the two
procurement PDFs listed below. The published cleanup branch has sanitized history;
the original main branch's older history has not been replaced.

## Architecture and existing behavior

- The production extraction path is `POST /parse`, using `extractor.py` and a
  single DeepSeek request through OpenRouter.
- PDF text conversion uses PyMuPDF rather than the earlier Docling stack.
- `trimmer.py` selects scored document chunks before extraction. This is a
  heuristic and can omit relevant content.
- Extracted JSON is validated with Pydantic. The extraction token budget is 6000.
- Job state lives in memory and is lost on restart; it assumes one instance.
- CORS permits only `https://redomaworks.com` and `https://www.redomaworks.com`.
- `/parse` caps PDF files and complete JSON bodies at 25 MiB. The JSON path
  checks actual streamed bytes before parsing or scheduling extraction.
- Image-only PDFs have no OCR. Drawing-only information cannot be extracted as text.
- `/parse/v2` depends on optional `agno`, which is intentionally absent from
  `requirements.txt`. Its shipping decision remains open.

## Verification artifacts

`Testing/` contains only `SPE8E426T1829.PDF` and
`MODOT 0000000343SL_SUPPLIER.pdf`, as explicitly requested by the owner.
`verify_deploy.py` uses the retained fixtures and their existing field checks;
the MoDOT path now points into `Testing/`. These procurement forms contain real
contact information; they are not fictional samples.

The offline tests in `tests/` mock extraction and do not call the LLM provider.
No live deployment verification was performed as part of this cleanup. Generated
document text and result files remain ignored and must not be committed with
private data.
