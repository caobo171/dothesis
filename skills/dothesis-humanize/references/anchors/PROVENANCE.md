# Anchor provenance

Every anchor in this directory has to be defensible on three counts: it is real
human writing, it was published before ~2022, and it is **not in the search
index** — the third being the one that decides whether the anchor helps or
hurts. See `README.md` for why, and `docs/anchor-sourcing-brief.md` for the
sourcing procedure this record follows.

Sourced 2026-08-07 from a candidate list produced by a browser agent working
from that brief.

Two rounds are recorded here: the Vietnamese anchors first, then the English
ones (`docs/anchor-sourcing-prompt-en.md`), which are judged on a different bar —
see "English anchors" below.

# Vietnamese anchors

## Installed

Both sources are articles in **Tạp chí Khoa học Thương mại** (Journal of Trade
Science, ISSN 1859-3666), the Thuongmai University economics journal. Full-issue
PDFs are published free of charge on the journal's own site.

| Anchor | Source | Section | Words |
|---|---|---|---|
| `vi_ketqua_efa` | [A] | 4.2–4.3 reliability + EFA | 386 |
| `vi_banluan_hoiquy` | [A] | 4.4 linear regression + interpretation | 376 |
| `vi_tongquan_nghiencuu` | [A] | 2.3 related studies | 379 |
| `vi_phuongphap_khaosat` | [B] | 3.1 sampling and data collection | 353 |

**[A]** Nguyễn Thị Ngọc Huyền và Trần Thị Thanh Phương (2021), "Tác động của
thực tiễn quản trị nguồn nhân lực đến hiệu quả công việc của nhân viên ngành
tài chính tiêu dùng tại Thành phố Hồ Chí Minh", *Tạp chí Khoa học Thương mại*
số 154/2021, mã số 154.2.HRMg.21, tr. 65.
<https://tckhtm.tmu.edu.vn/upload/news/files/154-b6.pdf>
Received 16/03/2021. PDF creation date 2021-07-16.

**[B]** Vũ Tuấn Dương và Nguyễn Thị Thanh Nhàn (2021), "Nghiên cứu tác động của
chất lượng và giá trị dịch vụ đến sự hài lòng của sinh viên tại một số trường
đại học tư thục trên địa bàn Hà Nội", *Tạp chí Khoa học Thương mại* số 153/2021,
mã số 153.3OMIs.31, tr. 105.
<https://tckhtm.tmu.edu.vn/upload/news/files/153-b13.pdf>
PDF creation date 2021-06-02.

Three of the four anchors come from source [A]. That is a known weakness — the
router picks between them on register, but three of the four registers are one
author pair's voice. Replace one when another clean source turns up.

### Index test

Each source was tested twice, on two different distinctive sentences, quoted:

| Source | Sentence | Result |
|---|---|---|
| [A] | "sau khi loại bỏ 64 phiếu không đạt yêu cầu thì còn lại 612 phiếu sử dụng được" | no match |
| [A] | "tổng phương sai trích là 76.314%" | no match |
| [B] | "1068 sinh viên chính quy đang theo học năm 1 đến năm 4 tại ba trường Đại học tư thục" | no match |
| [B] | "Công cụ xử lí dữ liệu là phần mềm IBM SPSS 22 và IBM AMOS 23" | no match |

A title-level search for [A] returned only the journal's own table-of-contents
PDF; for [B], nothing at all. Neither appears on 123doc, tailieu.vn, scribd,
academia.edu, ResearchGate or studocu.

Caveat on the method: these searches ran through the agent's web search tool,
not Google directly, so they corroborate the browser agent's Google checks
rather than reproduce them. Two sentences agreeing is weak-but-real evidence;
it is not proof of absence from any training corpus.

### Licence

The journal site carries, verbatim:

> © Bản quyền thuộc về Đại học Thương mại
> Giấy phép xuất bản số 195/GP-BTTTT ngày 05/6/2023. Bộ Thông tin và Truyền thông

No Creative Commons or other open licence is stated. These are ~380-word
excerpts of an all-rights-reserved work, held server-side and used as prompt
input. They are never copied into student output — the humanize pass shows the
anchor as a voice to imitate, and `verify_frozen` would flag reproduced spans —
and this directory is not part of `skills-public/`, so nothing here reaches an
end user. Reasonable-quotation territory, but it is a judgement call, not a
licence grant. Revisit if the anchors ever move client-side.

## Rejected

Four candidates the browser agent had rated **CAO** (high value / not indexed)
failed on re-test. Recording them so nobody re-imports them later.

| Candidate | Why rejected |
|---|---|
| Võ Thị Ánh Nguyệt và Nguyễn Hoàng Minh Trí, số 143/2020, mã số 143.1DEco.11 | Full PDF hosted on ResearchGate. The brief lists ResearchGate as automatic rejection. |
| Mai Thanh Lan và Đỗ Vũ Phương Anh, số 142/2020, mã số 142.2BMkt.21 | Test sentence reproduced verbatim on tailieugiaotrinh.com, a document aggregator. Fully indexed. |
| Nguyễn Thị Minh Nhàn và Bùi Thị Ánh Tuyết, số 140/2020, mã số 140.1HRMg.11 | The article itself did not match, but the same authors' near-identical work on the same topic is on tapchicongthuong.vn and doan.edu.vn. The voice is in the corpus even if this PDF is not. Precautionary. |
| Võ Thị Ngọc Thúy và cộng sự, số 159/2021, mã số 159.1TRMg.11 | Passed the sentence test, rejected on register. Section 4.4 is tourism policy recommendation, which reads like the Vietnamese policy/news prose that saturates the web. `README.md` lists this family of registers as holding its AI signal regardless of anchor quality. |

Two of five sources tested therefore had a false CAO rating, and a third was
marginal. **Do not trust an index rating you have not re-tested yourself**, and
test more than one sentence — the first sentence passed for both false CAOs.

## Extraction notes

Reproducing this is not just "run pdftotext". The journal typesets two
justified columns around floating tables, and two failure modes corrupt the text
invisibly:

- Plain `pdftotext` interleaves the two columns into single lines, welding
  unrelated half-sentences together.
- `pdftotext -x/-W` cropping clips the last glyph of any line reaching the
  gutter — "quản trị" became "quản tr", "Kết quả" became "Kế quả". Vietnamese
  diacritics make this easy to miss.

What worked: pdfminer layout analysis, assigning each text box to a column by
which side of the page midpoint its centre falls on. Then strip running heads,
page numbers, table captions and source notes; re-flow paragraphs using the
justified-text heuristic (a short line that ends a sentence ends a paragraph);
rejoin words the typesetter hyphenated across a line break; and truncate at the
last full stop so the anchor never ends on a fragment.

The scratch scripts are not checked in — they were one-shot. The important part
is knowing the two corruption modes exist and reading the Vietnamese to confirm
they are gone.

Author imperfections were **kept** on purpose, per `README.md`: the run-on
opening of `vi_tongquan_nghiencuu`, inconsistent capitalisation of
"Cronbach's alpha", the stray "(bảng 3)" cross-references. Those irregularities
are the part that sits off-distribution.

# English anchors

Sourced 2026-08-07 against `docs/anchor-sourcing-prompt-en.md`. All five slots
are filled, each from a different paper by a different author team, across three
journals. Every source is Tier 1: an English-language quantitative business or
service paper by Vietnamese authors, published before 2022.

The English bar is deliberately different from the Vietnamese one. Literal
absence from the index is not achievable for English academic text, so the tests
below establish (a) real human authorship, (b) no aggregator mirror, and (c) no
near-duplicate by the same authors — while the *register* criterion does the
real work: these are non-native academic English, and the imperfections are
kept, because polished native phrasing is exactly the register the rewrite must
move away from.

## Installed

| Anchor | Source | Section | Words |
|---|---|---|---|
| `en_results_sem` | [C] | 4.1–4.2 reliability, regression, hypothesis verdicts | 384 |
| `en_methodology_survey` | [D] | 4 research methodology — pilot, administration, sampling | 361 |
| `en_discussion` | [E] | 5 discussion | 272 |
| `en_litreview` | [F] | 2–2.1 literature review, TAM | 353 |
| `en_intro_problem` | [G] | 1 introduction | 325 |

**[C]** Van Thi Bich and Tran Thi My Huong (2019), "Factors Affecting Employee
Cohesion in Post-Merger Enterprises", *VNU Journal of Science: Economics and
Business*, Vol. 35, No. 5E, pp. 51–59.
<https://js.vnu.edu.vn/EAB/article/view/4296>
Received 05 November 2019; Revised 20 December 2019; Accepted 26 December 2019.

**[D]** Nguyen Thi Quynh Nga and Giang Bao Quynh Nhu (2020), "An empirical study
on factors influencing consumer impulsive purchase behavior: a case of Ho Chi
Minh city in the 4.0 era", *Journal of International Economics and Management*,
Vol. 20 No. 3, pp. 17–41. doi:10.38203/jiem.020.3.0014
<https://jiem.ftu.edu.vn/index.php/jiem/article/view/26>
Received 17 May 2020; Revised 23 August 2020; Accepted 05 September 2020.

**[E]** Phan Thi Kim Tuyen and Pham Xuan Hung (2021), "Factors Influencing
Patients' Satisfaction with Healthcare Services – A Case Study of Public
Hospitals in Hue City", *Hue University Journal of Science: Economics and
Development*, Vol. 130, No. 5B, pp. 117–127.
<https://jos.hueuni.edu.vn/index.php/hujos-ed/article/view/6656>

**[F]** Hoang Dam Luong Thuy and Nguyen Thu Ha (2020), "What Drives Intention to
Use Facebook: An Empirical Study of Vietnamese Users", *VNU Journal of Science:
Economics and Business*, Vol. 36, No. 5E, pp. 92–103.
<https://js.vnu.edu.vn/EAB/article/view/4460>
Received 08 December 2020; Revised 19 December 2020; Accepted 19 December 2020.

**[G]** Dao Thi Thu Giang and Cao Thi Hong Vinh (2020), "Do business linkages
play a role in upgrading workers' skills among small and medium-sized
enterprises in Vietnam?", *Journal of International Economics and Management*,
Vol. 20 No. 3, pp. 96–117. doi:10.38203/jiem.020.3.0018
<https://jiem.ftu.edu.vn/index.php/jiem/article/download/30/25>
Received 08 June 2020; Revised 10 October 2020; Accepted 15 October 2020.

### Index test

Four steps per source, as the prompt requires: two quoted sentences from
different sections, a title-plus-author search, and an author-plus-topic search
for a near-duplicate paper.

| Source | Step | Result |
|---|---|---|
| [C] | "employees were encouraged to complete the survey during work time" | no match |
| [C] | "there is no relationship between Gender, Working experience in enterprises, Position, and Income and organizational commitment" | no match |
| [C] | title + both authors | journal's own article page only |
| [C] | authors + organizational commitment / post-merger | no near-duplicate |
| [D] | "we shared the activation codes which can activate free account to become a premium account" | no match |
| [D] | "Now we celebrate the journey of the past decade with many transformations in ourselves as a person" | no match |
| [D] | title + both authors | journal's own article page and PDF only |
| [D] | "Nguyen Thi Quynh Nga" + impulse buying | no near-duplicate |
| [E] | "the good interaction between inpatient and hospital staff will increase the satisfaction of inpatients" | no match |
| [E] | "The majority of respondents who took part in this research came from Thua Thien Hue province" | no match |
| [E] | title + "public hospitals in Hue city" | journal's own article page only |
| [E] | both authors + patient satisfaction / service quality | no near-duplicate |
| [F] | "57 per cent of them are not happy with Facebook chat support" | no match (traces only to the Q&Me survey the paper cites) |
| [F] | "the mass of users connects to a user and become a factor to explain the social media usage behaviour" | no match |
| [F] | title | journal's own article page only |
| [F] | both authors + Facebook / social media | no near-duplicate |
| [G] | "standing alone in the business battlefield could lead to an inevitable stagnancy" | no match |
| [G] | "due to the method of collecting data every two years, some adjustments have been made in the survey instruments" | no match |
| [G] | title | journal's own article page only |
| [G] | both authors + business linkages / workers' skills | no near-duplicate; a ResearchGate *profile* page for one author appears, listing titles but not hosting this PDF |

Same caveat as the Vietnamese round: these searches ran through the agent's web
search tool, not Google directly. Two sentences agreeing is weak-but-real
evidence of absence from that index; it is not proof of absence from a training
corpus. For English that was never the goal — see the note above.

### Licence

Quoted verbatim from each publisher's page. No licence was inferred.

**[C], [F] — VNU Journal of Economics and Business.** No copyright or licence
statement appears on the article page or the journal home page. The only
relevant line is the press permit:

> VNU Journal of Economics and Business (VNU-JEB) was established by the VNU
> University of Economics and Business according to license No. 233/GP-BTTTT
> dated April 27, 2021, signed by the Minister of Information and Communication.

Copyright licence: **not stated**.

**[D], [G] — Journal of International Economics and Management.** The site
footer carries:

> @2019 Journal of International Economics and Management
> Governing agency: Foreign Trade University
> License No. 500/GP-BTTTT on November 15, 2019

Copyright licence: **not stated** (that is a publishing permit, not a grant).

**[E] — Hue University Journal of Science: Economics and Development.** The
article page carries:

> This work is licensed under a Creative Commons Attribution-ShareAlike 4.0
> International License.
> Copyright (c) 2021

This is the one source with an explicit open licence.

The same reasoning as the Vietnamese anchors applies to [C], [D], [F] and [G]:
these are ~250–400 word excerpts held server-side and used as prompt input, never
copied into student output, and this directory is not part of `skills-public/`.
Reasonable-quotation territory, but a judgement call rather than a licence grant.
Revisit if the anchors ever move client-side.

## Rejected

The dominant finding of this round: **Vietnamese journal articles in English are
mirrored onto ResearchGate and academia.edu by their own authors at a very high
rate.** Of roughly 30 candidates that matched on register and year, most failed
the title-plus-author step. Recording them so nobody re-imports them.

| Candidate | Why rejected |
|---|---|
| JIEM 3, 4, 5, 17, 22, 23, 27, 28, 29, 36, 43 | Full PDF on ResearchGate, academia.edu, ProQuest, studocu or a document aggregator |
| HCMC Open University 216, 220, 224, 226, 542, 562, 984, 1400, 1419 | Same — ResearchGate or academia.edu. Nine of nine OU candidates tested failed |
| Hue 5750, 5961 | ResearchGate; 5961 also academia.edu |
| VNU JEB 4167, 4182, 4196, 4199, 4224, 4302, 4374, 4456, 4457 | ResearchGate, academia.edu, scribd or doan.edu.vn |
| Dalat 592 | ResearchGate |
| JIEM 6 — out-of-class student engagement | The paper itself is clean, but the same authors' near-identical study is in *Journal of Applied Research in Higher Education* (Emerald, 2024). Near-duplicate rule |
| HCMC Open University 988 — "Impacts of passion with job, perceived justice on OCB and creative behaviors" | Passed both sentence tests and the title test. Rejected on the fourth step: a co-author has a 2023 perceived-justice PLS-SEM paper whose full PDF is indexed on jfm.edu.vn. Precautionary, same as Vietnamese source 140/2020 |
| Dalat 690 — destination image, satisfaction and eWOM, Sa Dec | Passed both sentence tests and the title test. Rejected on the fourth step: the author is a co-author of a destination-image paper indexed on ResearchGate, SSRN and KoreaScience |
| JIEM 21 (green hotels), JIEM 37 (joint master student satisfaction) | Passed the mirror test. Rejected on **extraction**: the PDFs use subset fonts with no usable ToUnicode map, and pdfminer and pdftotext both return a mix of correctly decoded and shift-encoded characters that cannot be disambiguated word by word. An anchor cannot be built from text that might be silently wrong |
| VNU JEB 4285 (SME manager skills), 4454 (business productivity, Hertfordshire and Hung Yen) | Clean on every index step. Rejected on **register**: both sections are enumerated policy and training recommendations, which `README.md` lists as the register that holds its AI signal regardless of anchor quality |

## Extraction notes (English round)

Same two silent-corruption modes as the Vietnamese round, plus one new one.

The VNU JEB PDFs are two-column justified with floating tables, and paragraphs
run **left column then right column within a band**, not down the whole left
column first. Box-level extraction therefore interleaves paragraph halves. The
fix was to dump text *lines* with their x/y coordinates and reconstruct reading
order by hand — for example in [C], "…explained by four independent variables,
included: (i) Job satisfaction … and (iv) Work" continues as "stress. Results of
variance analysis in Table 5 has an F value of 203.805…" in the right column,
which the box order put three paragraphs away.

The same method resolved a genuine ambiguity in [F], where a single justified
line had been split into four boxes. The printed line reads "…can bring
'entertainment' for users [25]. Such that," — not "…the fact that, usage of an
information system…", which is what the box order suggested. Getting this wrong
would have put a fabricated sentence in the anchor.

New mode: **subset fonts with no ToUnicode map.** Several JIEM PDFs emit
`(cid:N)` tokens for part of the text and shift-encoded literal characters for
the rest, in the same paragraph. The mapping is a uniform ASCII shift where it
applies, but it does not apply uniformly, so "which" arrives as "ZhLFh" with the
h correct and the rest shifted. There is no reliable per-word way to tell a
shifted character from a correct one. Those PDFs were rejected rather than
guessed at.

Author imperfections were **kept** deliberately, as with the Vietnamese anchors,
and they are the point of the English round:

- `en_discussion` — "the roles of **survive** dimensions of hospital services"
  (a typo for "service", verified against the printed line), "the second
  important **factors**", "an impact of the 'Responsiveness' factor on patient
  satisfaction **the** public hospitals".
- `en_litreview` — "needs to be **re-revaluated**", "excludes the fact usage of
  an information system can bring", "customer acceptance is **mostly closely
  relevant to** technology changes", "the mass of users … **become** a factor".
- `en_results_sem` — "Comparing the value (strength) of **βeta**", "among
  **employee** in post-merger enterprises", "human resource management
  activities in this field in Vietnam and other environments are not different".
- `en_methodology_survey` — "the answers are **decent** for our research",
  "turning on proper email auto-checking function".
- `en_intro_problem` — "standing alone in the business battlefield could lead to
  an inevitable stagnancy", "which makes significant contribution to the
  economy".

Two typographic flattenings were unavoidable and are recorded here so they are
not mistaken for author error: in `en_results_sem`, the subscripted
"β<sub>normalization</sub>" of the original is rendered "β normalization", and
table/figure cross-references such as "(see Table 2)" were kept, as they were in
the Vietnamese anchors.
