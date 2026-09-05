# AI patterns — what to look for, and what to leave alone

Read this when a passage still reads flat after a rewrite, when a supervisor says
"giống ChatGPT" and you need something more specific than "viết lại đi", or when
you have to explain what is wrong with a paragraph before touching it.

Every entry has a **Leave it when** line. That line carries the same weight as
the pattern above it. A list of things to delete, used without its guards, is how
a rewrite makes a document worse: on the one dissertation where we hold real
before-and-after Turnitin reports, the rewritten paragraphs went from 16.4% to
36.6% flagged while the untouched ones barely moved.

Three rules bind at every entry:

- **Finding a pattern is not permission to delete a claim.** A thesis sentence
  that is padded still says something. Compress it; do not drop it. If it needs a
  citation it does not have, flag it for the writer.
- **Fix the pattern, not the word.** Swapping a watched word for a synonym leaves
  the shape intact, and shape is what reads as machine-written.
- **Invent nothing.** No number, citation, example or claim enters the text that
  was not already in it. Adding a vivid detail is the fastest way to make prose
  sound human and, in a thesis, it is fabrication.

The before/after pairs below all preserve their frozen tokens, because they have
to pass `scripts/frozen_check.py` like any other rewrite.

## A. Claims and evidence

### 1. Inflated importance and legacy

**Watch (VI):** đóng vai trò vô cùng quan trọng, là minh chứng rõ nét cho, đánh dấu bước ngoặt, có ý nghĩa to lớn, góp phần không nhỏ
**Watch (EN):** plays a crucial role, stands as a testament, marks a pivotal moment, underscores the importance of
**Tell:** an ordinary result is dressed as a turning point. The claim grows; the evidence does not.
**Before:**
Kết quả này cho thấy phong cách lãnh đạo chuyển đổi đóng một vai trò vô cùng quan trọng, đánh dấu bước ngoặt trong việc nâng cao sự hài lòng của nhân viên (β = 0,412; p < 0,01).
**After:**
Phong cách lãnh đạo chuyển đổi có tác động tích cực tới sự hài lòng của nhân viên (β = 0,412; p < 0,01).
**Leave it when:** the source reports a genuinely large effect and the sentence quantifies it. "Hệ số lớn nhất trong mô hình", backed by the comparison table, is a finding rather than inflation.

### 2. Shallow analysis bolted on with "việc …" and "-ing"

**Watch (VI):** qua đó góp phần, từ đó khẳng định, thể hiện rõ nét, việc … cho thấy
**Watch (EN):** highlighting, underscoring, reflecting, thereby contributing to
**Tell:** a trailing clause is added to make a plain fact sound analysed. Cut the tail and no information is lost.
**Before:**
Hệ số Cronbach's Alpha của thang đo đạt 0,872, qua đó góp phần khẳng định độ tin cậy của thang đo, phản ánh chất lượng của dữ liệu thu thập được.
**After:**
Hệ số Cronbach's Alpha của thang đo đạt 0,872, cho thấy thang đo đạt độ tin cậy.
**Leave it when:** the tail states a criterion or a consequence the source actually gives, such as a threshold comparison or a decision rule. Decoration is what goes.

### 3. Vague sources

**Watch (VI):** nhiều nghiên cứu cho thấy, các chuyên gia cho rằng, theo một số tài liệu, đã được chứng minh
**Watch (EN):** studies have shown, experts argue, research suggests, it is widely accepted
**Tell:** a claim is attributed to an unnamed crowd. In a thesis this is not a style problem, it is an uncited claim, and a marker catches it where a rewrite hides it.
**Before:**
Nhiều nghiên cứu trước đây đã chỉ ra rằng sự hài lòng trong công việc có ảnh hưởng tích cực đến ý định gắn bó của nhân viên.
**After:**
Sự hài lòng trong công việc có ảnh hưởng tích cực đến ý định gắn bó của nhân viên (cần bổ sung trích dẫn).
**Leave it when:** the paragraph names the study straight after, or the literature review already cited it. Never delete the claim to make the flag go away, and never invent a source to fill it.

### 4. Formulaic limitations and future-research padding

**Watch (VI):** mặc dù còn một số hạn chế nhất định, nghiên cứu vẫn, mở ra nhiều hướng nghiên cứu tiếp theo, cần có thêm các nghiên cứu
**Watch (EN):** despite these limitations, future research should explore, further studies are needed
**Tell:** the section exists because the template requires one, and says nothing a reader could act on.
**Before:**
Mặc dù còn một số hạn chế nhất định, chẳng hạn như mẫu chỉ gồm nhân viên khối văn phòng tại Hà Nội, nghiên cứu vẫn có những đóng góp quan trọng và mở ra nhiều hướng nghiên cứu tiếp theo trong tương lai.
**After:**
Hạn chế chính của nghiên cứu là mẫu chỉ gồm nhân viên khối văn phòng tại Hà Nội.
**Leave it when:** the template requires the section and the paragraph names a real constraint. The padding around a limitation is the tell, not the limitation.

### 5. Cutoff disclaimers and speculative gap-fill

**Watch (VI):** do hạn chế về dữ liệu, có thể suy đoán rằng, nhiều khả năng là, chưa có thông tin đầy đủ
**Watch (EN):** as of my last update, it is believed that, while specific data is limited, likely
**Tell:** the draft could not find a source, said so, then filled the hole with a guess that now reads like a finding.
**Before:**
Do chưa có số liệu chính thức, có thể suy đoán rằng tỷ lệ nghỉ việc của ngành trong năm 2023 vào khoảng 15%.
**After:**
Chưa tìm được số liệu chính thức về tỷ lệ nghỉ việc của ngành năm 2023. Con số 15% trong bản nháp không có nguồn, nên phải bỏ hoặc thay bằng số liệu có trích dẫn.
**Leave it when:** the hedge reports genuine statistical uncertainty. "Kết quả chưa đủ bằng chứng để kết luận" is correct practice, not a tell.

### 6. Generic positive endings

**Watch (VI):** nhìn chung nghiên cứu đã đạt được mục tiêu, hứa hẹn nhiều triển vọng, góp phần vào sự phát triển chung
**Watch (EN):** the future looks promising, this represents an important step
**Tell:** the paragraph ends on a send-off instead of on its last useful fact.
**Before:**
Nhìn chung, nghiên cứu đã đạt được các mục tiêu đề ra và hứa hẹn mở ra nhiều triển vọng cho sự phát triển chung của ngành, trong đó ba giả thuyết H1, H2 và H4 được chấp nhận.
**After:**
Ba giả thuyết H1, H2 và H4 được chấp nhận.
**Leave it when:** the conclusion chapter is supposed to restate contributions. A restatement tied to the findings is required; a send-off with no content is not.

## B. Rhythm and structure

### 7. Uniform sentence length

**Watch (VI):** no lexical trigger. Run `python3 scripts/frozen_check.py --scan draft.txt`.
**Watch (EN):** same. This one is measured, not read.
**Tell:** every sentence lands within a few words of the same length. Splitting the measured dissertation by what Turnitin highlighted, flagged paragraphs had a sentence-length CV of 0.247 against 0.473 for clean ones, while mean sentence length and vocabulary richness barely differed. Synonym-swapping moves none of it.
**Before:**
Kết quả phân tích cho thấy nhân tố A có tác động tích cực. Kết quả phân tích cho thấy nhân tố B có tác động tích cực. Kết quả phân tích cho thấy nhân tố C không có ý nghĩa.
**After:**
Nhân tố A và B đều có tác động tích cực. Nhân tố C thì không, hệ số của nó không đạt ý nghĩa thống kê.
**Leave it when:** `--scan` says the paragraph is already varied. Uniformity travels with flagged prose, but it is not what the detector measures, and forcing the number up is what produced the regression above. Use it to find limp writing, not as a score to farm.

### 8. Comma-chains

**Watch (VI):** any sentence past roughly 40 words held together with commas
**Watch (EN):** same
**Tell:** clauses are strung together because the draft never decided where the thought ends. A 79-word sentence is not more formal, it is harder to read.
**Before:**
Nghiên cứu tiến hành khảo sát 245 nhân viên tại 12 khách sạn ở Hà Nội, dữ liệu được thu thập trong ba tháng, sau đó được làm sạch và phân tích bằng SmartPLS để kiểm định các giả thuyết đã đề xuất trong mô hình nghiên cứu.
**After:**
Nghiên cứu khảo sát 245 nhân viên tại 12 khách sạn ở Hà Nội, dữ liệu thu thập trong ba tháng. Các giả thuyết được kiểm định bằng SmartPLS.
**Leave it when:** the clauses are genuinely one thought and splitting them would repeat the same subject three times. Length alone is not the tell; uniform length is.

### 9. Repeated openings and template frames

**Watch (VI):** Kết quả cho thấy … three times running, Nghiên cứu này …, Bảng 4.x cho thấy …
**Watch (EN):** The results show, This study, Table 4.x shows
**Tell:** the same frame opens sentence after sentence. The word is not the problem; the template is.
**Before:**
Kết quả cho thấy H1 được chấp nhận. Kết quả cho thấy H2 được chấp nhận. Kết quả cho thấy H3 bị bác bỏ.
**After:**
H1 và H2 được chấp nhận. H3 bị bác bỏ.
**Leave it when:** the repetition is doing work, such as a hypothesis table read row by row, or deliberate parallelism in a summary.

### 10. Metronome connectors

**Watch (VI):** Hơn nữa, Bên cạnh đó, Ngoài ra, Đồng thời, Đặc biệt
**Watch (EN):** Furthermore, Moreover, Additionally, In addition
**Tell:** one connector is ordinary. Three heading consecutive sentences is a metronome, and it is the most common single tell in Vietnamese drafted by a model.
**Before:**
Ngoài ra, thang đo đạt độ tin cậy. Bên cạnh đó, giá trị hội tụ được đảm bảo. Hơn nữa, giá trị phân biệt cũng đạt yêu cầu.
**After:**
Thang đo đạt độ tin cậy và giá trị hội tụ. Giá trị phân biệt cũng đạt yêu cầu.
**Leave it when:** a single connector marks a real contrast or addition. The run is the tell, not the word.

### 11. Forced groups of three

**Watch (VI):** a list of exactly three where the analysis covers two
**Watch (EN):** same, plus "innovation, inspiration, and insight" style triples
**Tell:** items are added or dropped to make a rhythmic set of three.
**Before:**
Thang đo được đánh giá qua độ tin cậy, giá trị hội tụ và giá trị phân biệt, mặc dù phần phân tích chỉ trình bày hai tiêu chí đầu.
**After:**
Thang đo được đánh giá qua độ tin cậy và giá trị hội tụ, đúng như phần phân tích trình bày.
**Leave it when:** the source really has three items. Do not cut a fourth to make a triple and do not add a third to complete one. Report the number the source has.

### 12. False "từ X đến Y" sweeps

**Watch (VI):** từ … đến …, bao quát toàn bộ, trên mọi khía cạnh
**Watch (EN):** from X to Y, spanning everything from
**Tell:** two endpoints are named to imply full coverage the study never had.
**Before:**
Nghiên cứu bao quát toàn bộ vấn đề nhân sự, từ tuyển dụng đến giữ chân nhân viên, mặc dù chỉ đo lường sự hài lòng và ý định nghỉ việc.
**After:**
Nghiên cứu đo lường sự hài lòng và ý định nghỉ việc.
**Leave it when:** the source names both endpoints and the ground between them is genuinely covered.

### 13. Not-only-but-also templates

**Watch (VI):** Không chỉ … mà còn …, Không những … mà …
**Watch (EN):** Not only … but also, It's not just X, it's Y
**Tell:** a two-part frame is used for emphasis rather than for a real contrast, then reused in the next paragraph.
**Before:**
Chất lượng dịch vụ không chỉ tác động trực tiếp đến sự hài lòng mà còn tác động gián tiếp thông qua hình ảnh thương hiệu.
**After:**
Chất lượng dịch vụ tác động trực tiếp đến sự hài lòng và gián tiếp qua hình ảnh thương hiệu.
**Leave it when:** the contrast is itself the finding, such as a direct effect that survives when a mediator enters the model. Once in a section is fine; the repetition is the tell.

## C. Wording

### 14. Overused vocabulary

**Watch (VI):** toàn diện, đột phá, cách mạng, tối ưu hóa, nâng cao hiệu quả, thúc đẩy, tận dụng, vô cùng quan trọng, sâu sắc
**Watch (EN):** comprehensive, robust, significant potential, leverage, foster, landscape, transformative, delve, crucial
**Tell:** the words a model reaches for and a person does not, especially in groups.
**Before:**
Nghiên cứu đề xuất giải pháp toàn diện nhằm tối ưu hóa và nâng cao hiệu quả công tác quản trị nhân sự.
**After:**
Nghiên cứu đề xuất các giải pháp cho công tác quản trị nhân sự.
**Leave it when:** the word is the accurate one. "Robust standard errors" is a method name, and a cited framework described as "toàn diện" keeps the word its author used.

### 15. Avoiding "là" and "có"

**Watch (VI):** đóng vai trò là, được xem như là, sở hữu, thể hiện
**Watch (EN):** serves as, stands as, features, boasts, represents
**Tell:** simple verbs are replaced by longer phrases that add nothing.
**Before:**
Sự hài lòng đóng vai trò là biến trung gian trong mô hình và sở hữu hệ số tác động 0,318.
**After:**
Sự hài lòng là biến trung gian trong mô hình, với hệ số tác động 0,318.
**Leave it when:** the phrase is the field's standard term. "Đóng vai trò trung gian" is how mediation is written in Vietnamese methods sections, and terminology beats the rule.

### 16. Filler openings

**Watch (VI):** Có thể thấy rằng, Điều đáng chú ý là, Trong bối cảnh hiện nay, Nhìn chung có thể nói
**Watch (EN):** It is important to note that, In order to, Due to the fact that, At this point in time
**Tell:** the sentence takes a run-up before it starts.
**Before:**
Có thể thấy rằng, kết quả phân tích đã chỉ ra rằng nhân tố Chất lượng dịch vụ có tác động tích cực tới Sự hài lòng.
**After:**
Chất lượng dịch vụ có tác động tích cực tới Sự hài lòng.
**Leave it when:** the opener carries a real transition. "Ngược lại với kỳ vọng, …" reports a result and stays.

### 17. Stacked qualifiers

**Watch (VI):** có thể phần nào cho thấy, dường như có khả năng, ở một mức độ nhất định
**Watch (EN):** could potentially, might arguably, in some cases it may
**Tell:** hedges pile up until nothing is claimed. Usually the residue of several editing passes.
**Before:**
Kết quả này có thể phần nào cho thấy rằng đào tạo dường như có khả năng ảnh hưởng ở một mức độ nhất định đến năng suất.
**After:**
Kết quả này cho thấy đào tạo có thể ảnh hưởng đến năng suất.
**Leave it when:** one qualifier is doing real work. A result that missed significance must stay hedged, and stripping that hedge is a worse error than the stack.

### 18. Statistical vocabulary that looks like AI vocabulary

**Watch (VI):** đáng kể, có ý nghĩa, tương quan, độ tin cậy, mô hình phù hợp
**Watch (EN):** significant, robust, correlation, reliability, model fit
**Tell:** none. This entry exists to stop the four above it. In a results or methods passage these are technical terms, and swapping "đáng kể" for "khá lớn" changes a claim about a p-value into a claim about size.
**Before:**
Mối quan hệ giữa hai biến có ý nghĩa thống kê ở mức 1% (p = 0,003).
**After:**
Mối quan hệ giữa hai biến có ý nghĩa thống kê ở mức 1% (p = 0,003).
**Leave it when:** always, in results and methods. The word is only ordinary vocabulary somewhere like "một khoản đầu tư đáng kể" in an introduction.

### 19. Fake deeper truths

**Watch (VI):** Về bản chất, Xét cho cùng, Điều quan trọng thực sự là
**Watch (EN):** At its core, The real question is, Fundamentally
**Tell:** an ordinary point is announced as a hidden insight.
**Before:**
Về bản chất, điều thực sự quan trọng ở đây là năng lực quản trị của doanh nghiệp.
**After:**
Năng lực quản trị của doanh nghiệp là yếu tố quan trọng ở đây.
**Leave it when:** the sentence corrects a real misreading and the paragraph then supports the correction.

### 20. Formulaic sayings

**Watch (VI):** là chìa khóa của, là xương sống của, là kim chỉ nam cho
**Watch (EN):** is the backbone of, the language of, the currency of
**Tell:** a claim is turned into a saying that sounds deep and states nothing measurable.
**Before:**
Nguồn nhân lực là chìa khóa của mọi thành công trong doanh nghiệp.
**After:**
Nguồn nhân lực ảnh hưởng đến kết quả hoạt động của doanh nghiệp.
**Leave it when:** the metaphor is an established term in the field and the text cites it as one.

## D. Formatting

### 21. Too much bold

**Watch (VI):** bold on ordinary nouns in body text
**Watch (EN):** same
**Tell:** a chatbot bolds what it considers important, which in a thesis is decided by the template.
**Before:**
Nghiên cứu sử dụng **SmartPLS** để kiểm định **mô hình cấu trúc** với **245 quan sát**.
**After:**
Nghiên cứu sử dụng SmartPLS để kiểm định mô hình cấu trúc với 245 quan sát.
**Leave it when:** the template requires bold, as for defined terms on first use or table headers.

### 22. Lists with bold mini-headings

**Watch (VI):** **Nhãn:** rồi lặp lại chính nhãn đó trong câu
**Watch (EN):** "**Performance:** Performance has been improved"
**Tell:** every item opens with a bold label and a colon, then restates the label.
**Before:**
**Độ tin cậy:** Độ tin cậy của thang đo đã được cải thiện. **Giá trị hội tụ:** Giá trị hội tụ đạt yêu cầu.
**After:**
Thang đo đạt độ tin cậy và giá trị hội tụ.
**Leave it when:** the list is a genuine enumeration the reader will scan, such as a hypothesis list or a variable definition table.

### 23. A heading repeated in the sentence below it

**Watch (VI):** Phần này trình bày …, Trong mục này, tác giả sẽ …
**Watch (EN):** This section presents …
**Tell:** the first sentence after a heading only restates the heading.
**Before:**
4.3. Kiểm định độ tin cậy của thang đo

Phần này kiểm định độ tin cậy của thang đo. Hệ số Cronbach's Alpha của cả sáu thang đo đều vượt 0,7.
**After:**
4.3. Kiểm định độ tin cậy của thang đo

Hệ số Cronbach's Alpha của cả sáu thang đo đều vượt 0,7.
**Leave it when:** the first sentence adds scope, sample or method rather than repeating the heading's words.

### 24. Emojis and decorative symbols

**Watch (VI):** ✅ ⚡ 🚀 in headings, bullets or captions
**Watch (EN):** same
**Tell:** decoration a chat interface encourages and a thesis never uses.
**Before:**
✅ Kết luận: mô hình phù hợp với dữ liệu thị trường 🚀
**After:**
Kết luận: mô hình phù hợp với dữ liệu thị trường.
**Leave it when:** never, in the body of a thesis. A symbol inside quoted survey material stays as quoted.

### 25. Em and en dashes as parenthetical punctuation

**Watch (VI):** any " — " between clauses
**Watch (EN):** two or more in one paragraph
**Tell:** near-universal in model output, near-absent in real Vietnamese academic prose.
**Before:**
The sample — 245 employees across 12 hotels — was collected over three months — a period covering one full season.
**After:**
The sample of 245 employees across 12 hotels was collected over three months, a period covering one full season.
**Leave it when:** an en dash joins a numeric range such as 2019–2023 or a page range. Vietnamese drops the parenthetical dash outright; English keeps at most one per paragraph.

### 26. Curly quotes mixed with straight ones

**Watch (VI):** “ ” and " " in the same document
**Watch (EN):** same
**Tell:** the mix shows text was pasted from a chat window into a document that quotes differently. Either mark alone proves nothing.
**Before:**
Khái niệm “sự gắn kết” được định nghĩa theo Meyer và Allen (1991), còn "sự hài lòng" theo Locke (1976).
**After:**
Khái niệm "sự gắn kết" được định nghĩa theo Meyer và Allen (1991), còn "sự hài lòng" theo Locke (1976).
**Leave it when:** the whole document uses one style consistently. Word and Google Docs curl quotes by default, so consistent curly quotes are normal.

## E. Chatbot residue

### 27. Assistant text left in the draft

**Watch (VI):** Dưới đây là, Hy vọng phần này hữu ích, Bạn có muốn tôi, Chắc chắn rồi
**Watch (EN):** Here is, I hope this helps, Would you like me to, Certainly!
**Tell:** the greeting or the offer that wrapped a chat answer was pasted in with it.
**Before:**
Dưới đây là phần phân tích nhân tố khám phá. Hy vọng phần này hữu ích cho bạn! Hệ số KMO đạt 0,842.
**After:**
Hệ số KMO đạt 0,842.
**Leave it when:** never. If it survives the draft it prints in the bound copy.

### 28. Meta commentary about the writing

**Watch (VI):** Đây là một phần rất quan trọng, tác giả xin trình bày như sau, như đã đề cập ở trên nhiều lần
**Watch (EN):** Great question, as I mentioned, in this section I will now
**Tell:** the text talks about itself instead of saying the thing.
**Before:**
Đây là một phần rất quan trọng của luận văn, và tác giả xin trình bày như sau về kết quả hồi quy.
**After:**
Kết quả hồi quy như sau.
**Leave it when:** the sentence is a roadmap the template asks for. See 32.

### 29. Placeholders left behind

**Watch (VI):** XX%, [tên tác giả], (cần bổ sung), (chưa có số liệu)
**Watch (EN):** TBD, [insert citation], XX%
**Tell:** the draft marked a hole and the hole is still there. A humanizing pass must not make it read better.
**Before:**
Tỷ lệ phản hồi đạt XX% (cần bổ sung số liệu), cao hơn mức trung bình của các nghiên cứu tương tự.
**After:**
Tỷ lệ phản hồi đạt XX% (cần bổ sung số liệu), cao hơn mức trung bình của các nghiên cứu tương tự.
**Leave it when:** always leave it, exactly as it is, and tell the writer. Smoothing a placeholder into fluent prose is how it reaches the examiner.

## F. Terminology and register

### 30. Renaming the same construct

**Watch (VI):** Chất lượng dịch vụ → yếu tố chất lượng → nhân tố này
**Watch (EN):** the construct → the factor → this variable
**Tell:** general advice on AI writing says to vary how you name a repeated subject. For a thesis that is backwards. A construct has one name, fixed by the model, the hypotheses, the questionnaire and the tables, and renaming it breaks the link between them.
**Before:**
Chất lượng dịch vụ tác động tới sự hài lòng. Yếu tố chất lượng cũng ảnh hưởng tới lòng trung thành. Nhân tố này được đo bằng năm biến quan sát.
**After:**
Chất lượng dịch vụ tác động tới sự hài lòng. Chất lượng dịch vụ cũng ảnh hưởng tới lòng trung thành, và được đo bằng năm biến quan sát.
**Leave it when:** always. If the repetition reads heavy, merge the sentences as above. The full name still has to appear wherever the claim is stated.

### 31. Term drift between languages

**Watch (VI):** a Vietnamese term and its English gloss used interchangeably after the first mention
**Watch (EN):** the reverse, in an English thesis by a Vietnamese author
**Tell:** the draft switches language mid-paragraph for the same variable, which breaks the tie to the tables.
**Before:**
Mô hình đo lường sự hài lòng (satisfaction) và ý định nghỉ việc; kết quả cho thấy satisfaction có tác động ngược chiều tới turnover intention.
**After:**
Mô hình đo lường sự hài lòng (satisfaction) và ý định nghỉ việc (turnover intention); kết quả cho thấy sự hài lòng có tác động ngược chiều tới ý định nghỉ việc.
**Leave it when:** the English term is the accepted one in the field and the thesis defines it that way on first use. Gloss once, then stay in one language.

### 32. Announcing the next point

**Watch (VI):** Tiếp theo chúng ta sẽ tìm hiểu, Trước khi đi vào chi tiết, Hãy cùng phân tích
**Watch (EN):** Let's dive in, Here's what you need to know, In this section we will explore
**Tell:** the text announces a point instead of making it.
**Before:**
Trước khi đi vào chi tiết, hãy cùng phân tích kết quả kiểm định giả thuyết. Kết quả cho thấy bốn trong sáu giả thuyết được chấp nhận.
**After:**
Bốn trong sáu giả thuyết được chấp nhận.
**Leave it when:** a chapter opens with a roadmap by convention. "Chương 2 trình bày cơ sở lý thuyết và mô hình nghiên cứu" is required by many templates. The conversational "hãy cùng" is the tell, not the roadmap.

## What not to flag

None of these is evidence on its own, and treating any of them as a pattern is
how a rewrite damages work that was fine.

- **Passive voice in methods.** "Dữ liệu được thu thập bằng bảng hỏi" is correct academic Vietnamese. Forcing an actor into the sentence is a register error, not a fix.
- **Statistical vocabulary.** See 18. Every word in that entry is a technical term where it appears.
- **Template phrasing the university mandates.** Section titles, the declaration page, the roadmap sentence, the limitations heading. The student cannot change these and neither can you.
- **Correct but unidiomatic English from a Vietnamese author.** "Levels of length of service" is this writer's English. Polishing it into native-academic phrasing aims the text at a language model's own default register, which is the thing being detected. This is measured, not theoretical: it is what took the rewritten paragraphs of one dissertation from 16.4% to 36.6% flagged.
- **A single em dash, a single "Hơn nữa", one long sentence.** Patterns count when they stack.
- **Consistent terminology.** Required, per 30. Sameness here is discipline, not a tell.
- **Formal vocabulary as such.** Only the words in 14, and only where a plainer word carries the same meaning.
- **Clean grammar and consistent style.** Polish is not evidence. Supervisors edit drafts, and many students write well.
- **Curly quotes on their own.** Word, Google Docs and macOS insert them.
- **Anything `frozen_check.py` owns.** Numbers, p-values, β, table and figure references, citations, years. If a rewrite needs one of these to move, the rewrite is wrong.
- **Text written before November 2022.** An older draft chapter or a paragraph a supervisor inserted is not model output.

## Human details to keep

These carry the writer's voice, and a rewrite that sands them off has removed
the evidence that a person wrote this.

- **The student's own reasoning for a choice**, in their own words, even when it is clumsy. This is also the single best answer to a supervisor who says the writing feels generic.
- **Uneven rhythm.** A six-word sentence after a forty-word one is what real writing does.
- **Concrete local detail.** The company, the season the survey ran, the response rate that came in lower than hoped.
- **Results that did not work.** A rejected hypothesis reported as rejected, without softening.
- **Awkward but correct collocations** that belong to this author.
- **Anything the supervisor has already approved.** Rewriting it invites the same objection twice.

## How this fits the workflow

1. `--scan` to find the paragraphs worth touching.
2. Name the patterns. Say which numbers, so the writer can see the reasoning.
3. Decide at the level of a whole section. Turnitin scores overlapping stretches of roughly five to ten sentences, so a rewritten paragraph next to an untouched one is judged as one piece, and untouched paragraphs on that seam picked up flags on the measured document.
4. Rewrite against an anchor, one section at a time.
5. `frozen_check.py original.txt rewritten.txt`, every time.
6. On failure keep the original, repair once, and stop. Two passes that produce prose you would defend in a viva beat five that chase a number.

## Where these come from

The pattern taxonomy is adapted from Wikipedia's
[Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)
(CC BY-SA 4.0), maintained by WikiProject AI Cleanup, which
[blader/humanizer](https://github.com/blader/humanizer) (MIT) organised and
numbered for agent use.

Everything specific to a thesis is DoThesis's: the Vietnamese equivalents, the
academic-register examples, the guards on every entry, the measurements quoted
above, and entries 18, 29 and 30, which reverse or block general-purpose advice
that damages academic writing.
