/**
 * The smallest inline markup that legal copy actually needs: links and bold.
 *
 * The alternative was writing each policy twice as JSX, once per language.
 * Prose split across dozens of `<p>` elements is prose nobody proofreads, and
 * the Vietnamese edition is the one that would rot — so the copy below lives as
 * plain strings in one array per language, the way the blog's `COPY` objects
 * already do, and this turns `[label](href)` and `**bold**` into elements.
 *
 * Deliberately NOT a markdown library: the input is a string literal in this
 * repo, never user content, so the only requirement is that it handles the two
 * marks the copy uses. Anything more is a dependency and an XSS surface bought
 * for nothing — note there is no `dangerouslySetInnerHTML` anywhere here.
 */
import { Fragment, type ReactNode } from "react";

/** `[label](href)` or `**bold**`, whichever comes first. */
const TOKEN = /\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*/g;

export function inline(text: string): ReactNode {
  const out: ReactNode[] = [];
  let last = 0;
  let key = 0;

  for (const m of text.matchAll(TOKEN)) {
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));

    if (m[1] !== undefined) {
      const href = m[2];
      // A mailto or an in-site path needs no new tab and no `rel`; an external
      // http(s) link gets both, because leaving the policy page is a decision
      // the reader did not ask to make while reading a policy.
      const external = /^https?:\/\//i.test(href);
      out.push(
        <a
          key={key++}
          href={href}
          {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
        >
          {m[1]}
        </a>,
      );
    } else {
      out.push(<strong key={key++}>{m[3]}</strong>);
    }
    last = at + m[0].length;
  }

  if (last < text.length) out.push(text.slice(last));
  return out.map((node, i) => <Fragment key={i}>{node}</Fragment>);
}

/** One section of a policy: a heading, then paragraphs and bullet lists. */
export type Block = { p: string } | { ul: string[] };
export type Section = { h2: string; blocks: Block[] };

export function renderSections(sections: Section[]): ReactNode {
  return sections.map((s) => (
    <Fragment key={s.h2}>
      <h2>{s.h2}</h2>
      {s.blocks.map((b, i) =>
        "p" in b ? (
          <p key={i}>{inline(b.p)}</p>
        ) : (
          <ul key={i}>
            {b.ul.map((li) => (
              <li key={li}>{inline(li)}</li>
            ))}
          </ul>
        ),
      )}
    </Fragment>
  ));
}
