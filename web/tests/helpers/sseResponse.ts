// Builds a fake SSE Response from an array of raw SSE chunks.
// Designed for MSW handlers in tests — lets us test partial-chunk parsing
// by splitting the payload across multiple enqueues before the stream closes.
export function streamResponse(chunks: string[]): Response {
  const stream = new ReadableStream({
    start(controller) {
      const encoder = new TextEncoder();
      chunks.forEach(c => controller.enqueue(encoder.encode(c)));
      controller.close();
    },
  });
  return new Response(stream, {
    headers: { "Content-Type": "text/event-stream" },
  });
}
