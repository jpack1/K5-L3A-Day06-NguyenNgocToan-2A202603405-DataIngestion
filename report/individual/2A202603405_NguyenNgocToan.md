# Báo cáo cá nhân — Day 6

## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:** sách *Introduction to Python Programming* (OpenStax, Rice University), PDF tải từ `assets.openstax.org`, giấy phép **CC BY-NC-SA 4.0** (dùng cho mục đích học tập phi thương mại, có ghi nguồn). Snapshot SHA-256 `e1298e4f…0be383d`, 397 trang vật lý. Dùng 3 chapter 5 Loops (PDF trang 125–146), 9 Lists (221–236), 10 Dictionaries (237–258); khoảng trang lấy từ outline của PDF. Quy tắc tính: trang vật lý trong 3 khoảng trên có ≥ 300 ký tự sau chuẩn hóa. Kết quả: 60 trang vật lý, **59 trang được tính** (ch5: 21, ch9: 16, ch10: 22), loại trang 146 (chỉ có link video, 112 ký tự). Tổng 67.266 ký tự. Bìa, mục lục, preface, chapter khác, answer key và index không dùng. Manifest: `data/manifest.json`; text từng trang: `data/pages.jsonl`; script: `scripts/prepare_data.py`.
- **Chuẩn hóa, lỗi và giới hạn:** pypdf 6.21.4 trích text từng trang. Bỏ footer chạy (ví dụ `"116     5 • Loops"`) và dòng `"Access for free at openstax.org"`, đồng thời lấy số trang in từ footer làm `printed_page`. Chuẩn hóa Unicode NFKC, đổi `U+FFFD` (pypdf đọc sai ký tự bullet) thành `•`, đổi NBSP/tab, bỏ khoảng trắng cuối dòng, gộp dòng trống thừa; **giữ thụt đầu dòng** vì là code Python. Không cần OCR (mọi trang đều trích được text). Giới hạn: hình và video không được trích; thụt đầu dòng của code có thể không chính xác hoàn toàn; 3 trang mở đầu chương không có footer nên `printed_page = null`.
- **Embedding, vector store, metric, lệnh chạy, chi phí:** OpenAI `text-embedding-3-small`, 1536 chiều (số chiều được dò từ API khi khởi tạo), SDK `openai` 2.54.0. Query và document được embed giống nhau, không prefix, dùng text thô của chunk; lỗi API được báo ra, không có fallback sang vector giả. Vector store: PostgreSQL 16.16 + pgvector 0.8.7 (Docker `pgvector/pgvector:0.8.7-pg16`), bảng `chunks`, **exact cosine search** (`<=>`, không có index ANN), top-3. Python 3.14.10, psycopg 3.3.8. Lệnh chạy: xem `starter/README.md` (`python -m src.run --split dev|test`). Chi phí: ingest A 20.362 token (~0,00041 USD), B 18.652 token (~0,00037 USD), query dev + test 345 token; tổng ~**0,0008 USD** (theo giá niêm yết 0,02 USD/1M token).
- **Metadata bắt buộc, trường lọc, nguồn giá trị, lý do:** mỗi chunk có `document_id` (str, id cố định của nguồn), `source` (str, đường dẫn PDF), `page` (int, trang PDF vật lý). Thêm `printed_page` (int, từ footer), `chapter` (int) và `chapter_title` (str) lấy từ outline cấp 0 của PDF, `sections` (list[str], các section trong outline giao với trang đó), `char_start`/`char_end` (vị trí của chunk trong trang). **Trường lọc: `chapter`**, chọn vì 3 chương dùng chung nhiều thuật ngữ (`pop()`, `copy`, nested, comprehension, iterate) nên chương là phạm vi có ý nghĩa với người học. Giá trị lấy trực tiếp từ outline, không tự đoán.

## Cấu hình và benchmark

- **A / B / C:**
  - A: `fixed_size` 500 ký tự, overlap 50, cắt lại từ đầu ở mỗi trang (chunk không vượt qua ranh giới trang), không lọc.
  - B: `by_paragraph`, gom trọn các đoạn tối đa 500 ký tự. Đoạn kết thúc khi gặp dòng ngắn (< 80 ký tự) hoặc trước heading dạng `"5.2 For loop"`; heading luôn bắt đầu chunk mới; đoạn dài hơn 500 ký tự được cắt tại cuối câu. Không lọc.
  - C: dùng **chính chunk và vector của B**, chỉ thêm `WHERE chapter = %s` khi câu hỏi có filter.

  Cùng giới hạn 500 nên **A–B chỉ khác cách cắt chunk**; **B–C chỉ khác filter metadata**.
- **Benchmark:** 24 câu tiếng Anh (`benchmark/questions.jsonl`), **18 dev / 6 test**, chia trước khi chạy. Có 6 câu trực tiếp, 4 câu diễn đạt lại, 5 câu có điều kiện, 2 câu ngoại lệ và **7 câu có filter** (dev 5, test 2: q23 ch10, q24 ch9). Câu filter được viết mơ hồ giữa các chương; giá trị `chapter` là input giả định do người dùng cung cấp. Mỗi câu có `evidence_quote` nguyên văn và `alt_evidence` khi có trang hợp lệ khác. `scripts/validate_benchmark.py` kiểm tra quote nằm trên trang gold (bỏ qua khác biệt khoảng trắng), filter tồn tại và khớp trang gold, và số lượng split/filter đạt tối thiểu. Câu hỏi được AI soạn nháp từ corpus, sau đó được kiểm chứng tự động.
- **Tiêu chí chọn đã chốt trước khi xem test** (`benchmark/README.md`): chỉ dùng dev, theo thứ tự Evidence Hit@3 → Hit@1 (nếu hòa trong phạm vi 1 câu) → grounding → ít chunk/thời gian ingest thấp hơn.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian ingest | Chi phí ingest |
|---|---|---|---|---|---|---|
| A | dev | 5/18 | 11/18 | 171 | 2,16 s | ~0,00041 USD |
| B | dev | 6/18 | 10/18 | 203 | 2,43 s | ~0,00037 USD |
| C | dev | 6/18 | 12/18 | 203 (chung B) | 0 | 0 |
| A | test | 3/6 | 4/6 | 171 | (tái sử dụng) | 0 |
| B | test | 3/6 | 4/6 | 203 | (tái sử dụng) | 0 |
| C | test | 3/6 | 5/6 | 203 | (tái sử dụng) | 0 |

Thời gian và chi phí ingest là của lần nạp đầu (`results/ingest_first_run.json`). Nạp lại cùng dữ liệu: 0 chunk được embed lại, số dòng giữ nguyên. Thời gian truy vấn không được đo riêng.

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ, test (n/N) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 0,8 (10) | 18/18 | 0/2 | 0 / 1 / 5 → 1,83 |
| B | 1,6 (10) | 14/18 | 1/2 | 2 / 0 / 4 → 1,33 |
| C | 1,6 (10, chung chunk B) | 15/18 | 2/2 | 1 / 0 / 5 → 1,67 |

Filter tuân thủ trên dev: A 1/5, B 1/5, C 5/5.

**Đường dẫn trace, nhãn và cách chọn mẫu:**
- Trace top-3 đầy đủ (text, score, metadata, cờ hit): `results/dev/traces.jsonl`, `results/test/traces.jsonl`; tổng hợp: `summary.json` cùng thư mục.
- Nhãn thủ công: `results/manual/coherence.csv`, `test_metadata.csv`, `test_grounding.csv`.
- 10 vị trí coherence chốt trước khi chấm: ký tự giữa trang của mỗi trang thứ 6 trong 59 trang đã sắp xếp. Metadata và grounding được chấm trên 6 câu test × top-3.
- Phương pháp chấm: Claude chấm nháp theo thang điểm của GUIDE, rà soát lần 2 bằng cách đối chiếu text trang (sửa 2 bản ghi metadata), sau đó tôi duyệt toàn bộ và không sửa điểm.

## Phân tích và kết luận

- **A–B:** B giữ trọn ý tốt hơn (coherence 0,8 → 1,6; evidence bị tách qua chunk ở dev giảm từ 3 xuống 1), nhưng Evidence Hit@3 không tăng (dev 11 → 10, test 4 → 4) và grounding test giảm (1,83 → 1,33). **B–C:** filter đưa câu filter từ 3/5 lên 5/5 (dev) và từ 1/2 lên 2/2 (test), không ảnh hưởng câu không có filter, không tốn thêm chi phí.
  - **Ví dụ sai 1, q22 (test, gold trang 248):** "When iterating with items(), what does the loop variable receive on each pass?" Ở B/C, top-1 và top-2 là các chunk chỉ chứa dòng mục lục `"5.2 For loop"` và `"5.1 While loop"` (trang 125). Nguyên nhân: regex heading khớp cả dòng mục lục chương, nên mỗi dòng thành một chunk 12–14 ký tự có độ tương đồng cao với câu hỏi ngắn. A lấy đúng trang 248 nhưng chunk bị cắt mất đầu câu evidence (Hit tự động = False, grounding thủ công = 2).
  - **Ví dụ sai 2, q23 (test, filter ch10, gold trang 251/255):** "What does nested mean for this data type?" Không có filter, A/B trả về nested list của chương 9 (trang 229) và một mảnh câu ở trang 251. C lọc chương 10 và lấy được định nghĩa ở trang 255 (rank 3).
  - **Ví dụ dev q18 (gold trang 244):** `pop()` của dictionary bị `pop()` của list ở chương 9 lấn át trong A/B; C sửa được.
- **Chiến lược chọn: C**, theo luật chọn trên dev (Evidence Hit@3 12/18). Đánh đổi: C phụ thuộc vào việc người dùng cung cấp đúng chương; cho sai chương thì C loại mất đáp án. C chỉ có lợi khi câu hỏi mơ hồ giữa các phạm vi. Nếu ưu tiên grounding hơn độ chính xác tự động, A vẫn cạnh tranh nhờ overlap và chunk dài.
- **Hạn chế:**
  - Một cuốn sách, 3 chương, 24 câu hỏi do AI soạn nháp. Test chỉ 6 câu, nên 1 câu tương đương 17 điểm phần trăm.
  - Lỗi chunk mục lục của B được phát hiện khi đọc trace test và chưa được sửa. Nếu sửa thì kết quả test mới không còn độc lập.
  - Nhãn thủ công do AI chấm nháp và tôi duyệt, nên có nguy cơ thiên lệch neo theo nhãn nháp (anchoring).
  - `sections` là metadata cấp trang, không chính xác cho từng chunk.
  - Thời gian ingest là một lần đo trên máy cá nhân; chi phí ước tính theo giá niêm yết, chưa đối chiếu với hóa đơn.
- **Nếu làm lại:**
  1. Bỏ các dòng mục lục chương trước khi chunk, và gộp chunk quá ngắn (< 100 ký tự) vào chunk bên cạnh.
  2. Nhận diện heading con không đánh số (`"Continue"`, `"Copying a list"`).
  3. Thêm tiêu đề section vào text trước khi embed (contextual header) để câu hỏi không nhắc "dictionary" vẫn tìm đúng chương.
  4. Tạo tập test mới, lớn hơn, sau khi sửa B.
  5. Thử hybrid BM25 + dense trên dev.

## Sử dụng AI

Dùng Claude Code (Claude Opus 5.5) để: chọn corpus, viết code pipeline, soạn nháp câu hỏi benchmark, chấm nháp nhãn và viết nháp báo cáo. Cách kiểm tra:
- `scripts/validate_benchmark.py` kiểm chứng evidence; đã thử chèn lỗi giả và script bắt được.
- `tests/test_pipeline.py` là self-check offline cho chunking và evaluation.
- Nạp lại 2 lần để kiểm tra không nhân đôi.
- Tôi duyệt toàn bộ nhãn thủ công và đọc lại báo cáo.
