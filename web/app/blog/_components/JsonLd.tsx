/**
 * A single JSON-LD block.
 *
 * `<` is escaped in the serialized JSON. Without it a body containing the
 * literal string `</script>` — entirely plausible in a post about writing HTML
 * survey forms — closes this tag early and dumps the rest of the payload into
 * the document as markup.
 */
export function JsonLd({ data }: { data: Record<string, unknown> | null | undefined }) {
  if (!data) return null;
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replace(/</g, "\\u003c") }}
    />
  );
}
