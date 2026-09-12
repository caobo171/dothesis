/**
 * The one accept list for every upload picker in the chat surface.
 *
 * Keep in sync with the uploads endpoint's text-extractable set
 * (`api/app/routers/uploads.py`: `_ALLOWED_MIME` / `_ALLOWED_EXT`). We only
 * advertise what the server can pull real text from, so analysis never runs on
 * an empty extraction.
 *
 * Both MIME types and extensions are listed on purpose: browsers report .docx
 * inconsistently (often `application/octet-stream`), so a MIME-only filter greys
 * out the very file a thesis arrives as. The server gate accepts by extension
 * for the same reason.
 *
 * This lives in its own module because it was previously duplicated per picker,
 * and the copy in the composer drifted to `application/pdf,text/plain` — which
 * made .docx unselectable even though the endpoint had accepted it all along.
 */
export const UPLOAD_ACCEPT =
  // documents
  "application/pdf,text/plain,text/markdown," +
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document," +
  // survey datasets — the stats tools compute on these off the workspace copy
  "text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet," +
  "application/vnd.ms-excel," +
  // SmartPLS / SPSS results export
  "text/html," +
  // pasted / attached screenshots
  "image/png,image/jpeg,image/gif,image/bmp,image/tiff,image/webp," +
  ".pdf,.txt,.md,.markdown,.docx,.csv,.xlsx,.xls,.sav,.htm,.html," +
  ".png,.jpg,.jpeg,.gif,.bmp,.tif,.tiff,.webp";
