# Translate a passage of a thesis chapter

You are translating one passage from the {chapter_name} chapter of a master's
thesis into {target_lang}. The passage is markdown and the student wrote it
themselves — you are changing its language and nothing else.

## Rules

1. **Keep the markdown structure line for line.** A `#`/`##`/`###` heading stays
   a heading at the same level. A `| a | b |` table row stays one table row with
   the same number of `|` separators, and the `|---|---|` separator row is copied
   through unchanged. Blank lines between blocks stay where they are. Do not
   merge blocks, split blocks, or reorder anything.
2. **Never touch a number.** Every figure, coefficient, p-value, sample size,
   table number and section number appears in your output exactly as it appears
   in the input — same digits, same decimal point, same `**` / `*` significance
   marks. You are not recomputing, rounding, or reformatting anything.
3. **Never touch a variable code.** `PB`, `ATT_3`, `TR_5`, `EXP`, `KMO`,
   `Sig.`, `df`, `R²`, `VIF`, `Beta` and the like are labels, not words. Copy
   them as they are.
4. **Do translate the words around them** — headings, table column headings and
   row labels ("Chỉ số" → "Indicator", "Giá trị" → "Value", "Hệ số KMO" → "KMO
   coefficient"), captions, source and note lines, and the running prose.
5. Preserve inline citations like (Author, Year) verbatim.
6. Match the academic register of a thesis. Do not add commentary, do not
   summarise, do not explain, do not drop a sentence you find repetitive.

## Passage

{selection}

## Output

The translated passage only — no preamble, no code fence, no quotation marks.
