# The editorial pass

A second read over a draft that is already good. Adapted from WELE's founder
checklist of 2026-09-08, rewritten for a corpus whose subject is SPSS, SmartPLS
and a thesis defence rather than listening practice. Run it before a post ships,
and run it over a shipped post when its turn in the voice pass comes up.

**This is a pass, not a rewrite.** Name the strongest parts first and leave them
alone. In this bank those are usually the worked output table with its reading,
the failure mode with its fix, and the paragraph that says what a supervisor
will ask. A pass that touches every sentence has stopped being a pass and will
lose the parts that were working.

## The paragraph test

Every paragraph must do at least one of these:

- teach the reader something they can act on with the software open
- show real output, or a plausible illustrative table, and read it
- name a failure mode and what to do about it
- say how to write the result into the thesis, or what the defence will ask
- move the reader to the next idea

A paragraph that exists mainly to sound authoritative, or to carry a keyword,
gets rewritten or cut.

## What to fix

1. **Assertions in the post's own voice about the reader's numbers.** `Thang đo
   của bạn sẽ đạt`, `mô hình chắc chắn hội tụ`, `kết quả sẽ tốt hơn`. You cannot
   know their alpha, their p-value or their R². Describe the condition and the
   threshold with its source, then stop. Hedged, negated and quoted absolutes are
   correct writing and are not this defect; see `voice.md`.
2. **Numbers with no source.** Every threshold traces to `canonical-sources.md`,
   as the exact string given there. A number that has no source loses the number
   and keeps the shape of the thing.
3. **Accuracy beats a sharper line.** `Alpha thấp nghĩa là thang đo hỏng` is
   wrong: a low Alpha with three items is often the item count, not the scale. If
   the punchier phrasing is not true, the phrasing goes.
4. **Curate the tables.** Six well-chosen rows beat twelve. Cut a row that
   teaches nothing the row above it did not, and keep the one that shows the
   awkward case: the item that loads on two factors, the HTMT at 0.87, the
   negative eigenvalue.
5. **Memorable lines stay occasional.** Keep the one that earns its place and let
   the rest of the post be plain.
6. **Headings must describe what is in the section.** A section mixing the menu
   path, the output reading and how to write it up is not `Các lỗi thường gặp`.
7. **Keyword paragraphs belong in the FAQ.** A definition dropped mid-narrative
   to catch `<term> là gì` reads as an SEO patch. Move it to the FAQ, where a
   reader genuinely asking it will look.
8. **The FAQ does not re-explain the body.** If the body covered it, answer in
   two or three sentences and point back conceptually. The FAQ is for the
   questions the post did not already answer at length.
9. **No invented comparisons about effort or time.** Not `một buổi chiều là xong
   cả chương 4`. Say what the step involves and what usually makes it slow.
10. **Order by differentiation.** The worked output and its reading come early.
    Long reference tables stay in the post, for search and for reference, but
    later.
11. **The close is the next concrete action,** one paragraph, no heading, one CTA
    link. Not `Chúc bạn bảo vệ thành công`.

## What not to do

Do not make the post more formal. The register stays one person who has run the
analysis talking to one student with the data file open. Do not translate the
technical terms students use in English. Do not delete a worked table to hit a
word count: cut restatement instead.
