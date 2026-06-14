import "@tiptap/core";

// tiptap-markdown ships no types, so the Markdown extension's storage isn't
// known to TS. Augment @tiptap/core's (empty) Storage interface with just the
// surface we use — editor.storage.markdown.getMarkdown().
declare module "@tiptap/core" {
  interface Storage {
    markdown: {
      getMarkdown: () => string;
    };
  }
}
