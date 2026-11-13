# Benchmark

Chốt ngày 2026-11-13, **trước mọi lần chạy retrieval**. Không sửa `questions.jsonl` sau khi đã xem kết quả; nếu buộc phải đổi tập test, ghi lại ở đây và coi kết quả cũ là không còn độc lập.

- Corpus: `data/pages.jsonl` (OpenStax *Introduction to Python Programming*, chapter 5 Loops, 9 Lists, 10 Dictionaries; xem `data/manifest.json`).
- Câu hỏi: `questions.jsonl`, 24 câu, **18 dev / 6 test**. Câu hỏi, đáp án và evidence viết bằng tiếng Anh để cùng ngôn ngữ với corpus.
- Kiểm chứng: chạy `python scripts/validate_benchmark.py` từ `starter/`. Script kiểm tra mỗi evidence có nằm nguyên văn ở trang gold, giá trị filter có tồn tại trong corpus và khớp với trang gold, và số lượng split/filter đạt tối thiểu.

## Các trường

| Trường | Ý nghĩa |
|---|---|
| `id`, `split`, `type` | `type` ∈ `direct`, `paraphrase`, `condition`, `exception`, `filter` (chỉ dùng để phân tích lỗi) |
| `question`, `expected_answer` | Đáp án viết từ evidence, không dùng kiến thức ngoài |
| `gold_source_id`, `gold_page` | `document_id` và số trang PDF vật lý (trường `page` trong corpus, không phải `printed_page`) |
| `evidence_quote` | Đoạn văn nguyên văn trên trang gold sau chuẩn hóa |
| `alt_evidence` | Các cặp `{page, quote}` khác cũng hợp lệ (ví dụ trang chapter summary lặp lại định nghĩa). Khớp bất kỳ cặp nào đều tính là hit |
| `filter` | Filter metadata do ngữ cảnh người dùng cung cấp trước khi truy xuất, hoặc `null` |

**Quy tắc khớp evidence:** một chunk được tính là hit khi `document_id` + `page` trùng một trang gold/alt và text của chunk chứa **trọn** quote sau khi gộp mọi khoảng trắng (`" ".join(s.split())`). Quote bị tách qua hai chunk không tính là hit và được ghi vào log lỗi.

## Metadata filter

Trường lọc: `chapter` (int, lấy từ outline của PDF). Các câu filter được cố ý viết mơ hồ giữa các chương: `pop()`, nested, `copy`, comprehension đều xuất hiện ở cả list và dictionary; nested còn xuất hiện ở loop. Giá trị `chapter` là **input giả định**: người dùng cho biết họ đang học chương nào. Giá trị này không bao giờ suy ra từ đáp án gold.
Cấu hình C chỉ áp filter cho câu có `filter` khác `null`; các câu còn lại chạy không lọc và cho kết quả giống B.

| | dev | test |
|---|---|---|
| Câu có filter | 5 (q06 ch5, q07 ch9, q09 ch9, q17 ch10, q18 ch10) | 2 (q23 ch10, q24 ch9) |

## Chia dev/test

Tập test được chọn để phủ cả ba chương, đủ năm loại câu, và dùng các trang gold mà không câu dev nào dùng làm gold (trang 127, 138, 225, 248, 251, 228). Ngoại lệ và nguy cơ rò rỉ:

- q23 (nested dictionaries) có cùng dạng "nested" với q06/q09 ở dev; q24 (copy) có cùng dạng mơ hồ list/dictionary với q07/q18 ở dev. Tinh chỉnh trên dev vì thế có thể gián tiếp có lợi cho các câu test này.
- Trang alt 236 của q24 và trang alt 255 của q23 là trang chapter summary, cũng được q07 và q16 ở dev sử dụng.
- Chỉ có một cuốn sách của một nhóm tác giả: kết quả không suy rộng ra ngoài corpus này.

## Tiêu chí chọn cấu hình (chốt trước khi chạy)

Chỉ chọn cấu hình dựa trên **dev**, theo thứ tự:
1. Evidence Hit@3 cao nhất.
2. Nếu hòa (chênh nhau không quá 1 câu): Hit@1 cao hơn.
3. Vẫn hòa: điểm grounding chấm thủ công trên các mẫu dev cao hơn.
4. Vẫn hòa: ít chunk hơn / thời gian ingest thấp hơn.

Sau đó cố định cấu hình đã chọn, chạy test một lần, và báo cáo cả ba cấu hình trên test để so sánh.

## Tác giả

Câu hỏi, đáp án và evidence được soạn với sự hỗ trợ của AI (Claude) dựa trên corpus đã chuẩn hóa, và được kiểm chứng tự động bằng `validate_benchmark.py`. Học viên cần tự đối chiếu từng câu với PDF và ghi lại mọi chỉnh sửa tại đây.
