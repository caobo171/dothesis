/**
 * The post body renderer.
 *
 * A server component on purpose: the body IS the page as far as a crawler is
 * concerned, so it has to arrive in the HTML rather than after hydration.
 * react-markdown holds no state, so nothing here needs the client.
 */
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import rehypeRaw from "rehype-raw";
import rehypeSlug from "rehype-slug";
import remarkGfm from "remark-gfm";

import { HeadingSlugger } from "../_lib/markdown";

/** Minimal hast shapes — enough to walk the tree without a new dependency. */
type HastNode = {
  type: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
};

/** The text content of an element, the way the DOM would report it. */
function textOf(node: HastNode): string {
  if (node.type === "text") return node.value ?? "";
  if (!node.children) return "";
  return node.children.map(textOf).join("");
}

/**
 * Overwrite every heading id with the shared ASCII slug.
 *
 * rehype-slug runs first and is kept because it is the upstream default and
 * covers headings that arrive through raw HTML, but its ids come from
 * github-slugger, which preserves Vietnamese diacritics. The contents box, the
 * FAQ anchors and the Python side all use the ASCII slugger, so this pass has
 * the last word. Running it as a plugin rather than in the `h2` component is
 * deliberate: the slugger's collision counter has to see every heading in
 * document order, and per-element components are not guaranteed that.
 */
function rehypeAsciiHeadingIds() {
  return (tree: HastNode) => {
    const slugger = new HeadingSlugger();
    const walk = (node: HastNode) => {
      if (node.type === "element" && node.tagName && /^h[1-6]$/.test(node.tagName)) {
        node.properties = { ...(node.properties ?? {}), id: slugger.slug(textOf(node)) };
        return; // headings do not nest headings
      }
      node.children?.forEach(walk);
    };
    walk(tree);
  };
}

/** Anything that leaves this origin. Protocol-relative `//host` counts. */
function isExternal(href: string): boolean {
  return /^(https?:)?\/\//i.test(href) || /^mailto:/i.test(href);
}

const components: Components = {
  table({ node: _node, ...props }) {
    return (
      <div className="blog-tablewrap">
        <table {...props} />
      </div>
    );
  },
  a({ node: _node, href, ...props }) {
    const target = href ?? "";
    if (!isExternal(target)) return <a href={target} {...props} />;
    // `noopener` is the security half (the opened tab cannot reach back through
    // window.opener); `nofollow` keeps a thousand auto-written posts from
    // spraying link equity at competitor URLs the writer cited as sources.
    return (
      <a href={target} target="_blank" rel="noopener noreferrer nofollow" {...props} />
    );
  },
  img({ node: _node, ...props }) {
    // A plain <img>, not next/image: post bodies reference arbitrary remote
    // URLs, and next/image would need every one of those hosts allow-listed in
    // next.config before it would render at all.
    // eslint-disable-next-line @next/next/no-img-element
    return <img loading="lazy" decoding="async" {...props} alt={props.alt ?? ""} />;
  },
};

export function Markdown({ children }: { children: string }) {
  return (
    <div className="blog-prose">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw, rehypeSlug, rehypeAsciiHeadingIds]}
        components={components}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
