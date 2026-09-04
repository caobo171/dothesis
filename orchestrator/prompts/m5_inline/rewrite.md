# Rewrite a selection within a chapter

You are editing a short selection from a master's thesis chapter. You are given a
specific instruction for how to change it.

## Inputs
- Chapter: {chapter_name}
- Language: {language}
- Surrounding context (paragraph before): {context_before}
- Selection to rewrite: {selection}
- Surrounding context (paragraph after): {context_after}
- Instruction: {instruction}

## Rules
Rewrite ONLY the selection, following the instruction. Write in the same
language as the selection ({language}) and match the academic register of the
surrounding context so the result reads seamlessly in place.

Unless the instruction explicitly says otherwise:
- Preserve the meaning.
- Preserve every number, statistic, and in-text citation exactly as written.
- Do NOT add citations that were not present in the original selection.
- Do NOT fabricate data, sources, or findings.

Do NOT include any preamble, explanation, or quotation marks.

Output: the rewritten selection only, as plain text.
