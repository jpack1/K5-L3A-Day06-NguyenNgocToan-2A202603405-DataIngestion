# Đánh giá A / B / C

Lần chạy dev ngày 2026-11-13; cấu hình **C** được chọn theo luật chốt trước trong `benchmark/README.md` (Evidence Hit@3 cao nhất trên dev). Test chạy **một lần** sau khi chọn (`python -m src.run --split test`). Nguồn số liệu: `results/{dev,test}/summary.json`, `traces.jsonl`; nhãn thủ công trong `results/manual/`.

> **Phương pháp chấm nhãn:** nhãn thủ công do Claude (AI) chấm theo đúng thang điểm trong GUIDE, sau đó Claude rà soát lần 2 bằng cách đối chiếu lại với text trang và ranh giới chunk. Lần rà soát 2 sửa 2 bản ghi metadata (xem mục 3). Học viên Nguyễn Ngọc Toàn đã duyệt toàn bộ nhãn và không sửa điểm nào; cột `grader` ghi rõ quy trình này. Nguy cơ thiên lệch: nhãn nháp do AI tạo có thể ảnh hưởng đến người duyệt (anchoring).

Thiết lập chung: OpenAI `text-embedding-3-small` (1536 chiều, query và document embed giống nhau), PostgreSQL 16 + pgvector 0.8.7, exact cosine search, top-3. A = fixed 500/50; B = by_paragraph tối đa 500; C = chunk/vector của B + filter `chapter` cho câu có filter.

## 1. Độ chính xác truy xuất

| Cấu hình | Dev Hit@1 | Dev Evidence Hit@3 | Test Hit@1 | Test Evidence Hit@3 |
|---|---|---|---|---|
| A | 5/18 | 11/18 | 3/6 | 4/6 |
| B | 6/18 | 10/18 | 3/6 | 4/6 |
| C | 6/18 | **12/18** | 3/6 | **5/6** |

Chỉ số phụ (không thay định nghĩa chính):

| | Dev: gold page trong top-3 | Dev: evidence bị tách qua chunk | Test: gold page trong top-3 | Test: evidence bị tách |
|---|---|---|---|---|
| A | 14/18 | 3 | 6/6 | 2 |
| B | 11/18 | 1 | 5/6 | 1 |
| C | 13/18 | 1 | 5/6 | 0 |

A thường lấy đúng trang nhưng câu evidence bị cắt bởi cửa sổ 500 ký tự (ví dụ q02, q07, q22, q23). B/C hiếm khi tách evidence hơn nhưng lại mất trang gold do các chunk rất ngắn (xem mục 5).

## 2. Tính mạch lạc của chunk

10 vị trí chốt trước khi chấm: ký tự giữa trang của mỗi trang thứ 6 trong 59 trang đã sắp xếp (trang 125, 131, 137, 143, 224, 230, 236, 242, 248, 254). C dùng chunk của B nên điểm bằng B. Chi tiết và lý do: `results/manual/coherence.csv`.

| Cấu hình | Điểm 2 | Điểm 1 | Điểm 0 | Trung bình /2 |
|---|---|---|---|---|
| A | 0 | 8 | 2 | 0,8 |
| B (= C) | 7 | 2 | 1 | 1,6 |

A gần như luôn bắt đầu/kết thúc giữa câu hoặc giữa từ (`'implement r'`, `'execu'`). B giữ trọn đoạn; lỗi còn lại của B là chunk chỉ có link + tiêu đề bài tập (pos10) và đoạn câu hỏi bị cắt theo giới hạn 500 (pos02).

## 3. Tính hữu dụng của metadata

Kiểm tra 6 câu test × top-3 = 18 bản ghi mỗi cấu hình (`results/manual/test_metadata.csv`). Các cột `auto_*` được đối chiếu với **bản trích xuất lại trực tiếp từ PDF** (không dùng `pages.jsonl`): text có nằm trên trang đó, `printed_page = page − 10`, `chapter` khớp khoảng trang của outline, heading trong chunk có thuộc `sections`.

| | Bản ghi metadata đủ và đúng | Câu filter mà top-3 tuân thủ filter |
|---|---|---|
| A | 18/18 | 0/2 |
| B | 14/18 | 1/2 |
| C | 15/18 | **2/2** |

- Lỗi duy nhất: `sections` sai ở chunk B/C chỉ chứa dòng mục lục chương (ví dụ `"5.2 For loop"` trên trang 125 được gán section `5.1 While loop`). Chunk mục lục `"5.1 While loop"` cũng sai dù trùng tên section, vì nó nằm trong mục lục chứ không thuộc nội dung section 5.1; bản nháp đầu bỏ sót lỗi này và đã được sửa ở lần rà soát 2. `source`, `page`, `printed_page`, `chapter` đúng ở mọi bản ghi.
- **Trường hữu ích:** `chapter` giúp lọc đúng phạm vi. q23 (nested, ch10): B trả về nested list của chương 9, C lọc đúng và lấy được định nghĩa nested dictionary ở trang 255. `printed_page` giúp người đọc tra đúng số trang in trong sách.
- **Hạn chế:** `sections` là metadata cấp trang (section đang hoạt động ở đầu trang + section bắt đầu trên trang), nên không chính xác cho từng chunk; không nên dùng làm filter. Filter `chapter` là input giả định; nếu người dùng cho sai chương thì C sẽ loại mất đáp án.

## 4. Grounding quality (bằng chứng truy xuất, không phải độ chính xác câu trả lời LLM)

6 câu test, chấm top-3: 0 = không có bằng chứng, 1 = có nhưng thiếu điều kiện/ngữ cảnh, 2 = đủ để trả lời và truy nguồn (`results/manual/test_grounding.csv`).

| Cấu hình | 2 | 1 | 0 | Trung bình /2 |
|---|---|---|---|---|
| A | 5 | 1 | 0 | 1,83 |
| B | 4 | 0 | 2 | 1,33 |
| C | 5 | 0 | 1 | 1,67 |

A cao nhất vì ở q22, chunk A bị cắt mất đầu câu nhưng vẫn chứa `"...items() function, both the key and value for each item are passed to the loop variable"`: đủ để trả lời dù Evidence Hit tự động = False (bằng chứng tương đương do người chấm xác nhận). Đây là ví dụ Hit@3 tự động và grounding thủ công không trùng nhau.

## 5. Tác động của chiến lược dữ liệu

| | A | B | C |
|---|---|---|---|
| Số chunk | 171 | 203 | 203 (dùng chung B) |
| Độ dài min / median / mean / max | 61 / 500 / 426,1 / 500 | 6 / 386 / 330,7 / 500 | như B |
| Tổng ký tự được embed | 72.866 (có overlap) | 67.126 | 0 thêm |
| Token embedding | 20.362 | 18.652 | 0 thêm |
| Thời gian ingest | 2,16 s | 2,43 s | 0 |
| Chi phí | ~0,00041 USD | ~0,00037 USD | 0 |

Chi phí tính theo giá niêm yết 0,02 USD / 1M token. Nạp lại cùng dữ liệu: 0 chunk được embed lại, số dòng giữ nguyên (171 / 203).

**A → B (đổi cách chunk):** coherence tăng rõ (0,8 → 1,6), evidence bị tách giảm (dev 3 → 1), nhưng Evidence Hit@3 không tăng (dev 11 → 10, test 4 → 4) và grounding test giảm (1,83 → 1,33). Nguyên nhân chính là **lỗi của B**: các dòng mục lục ở trang mở đầu chương (`"5.1 While loop"`, `"5.2 For loop"`...) khớp regex heading nên mỗi dòng thành một chunk riêng 6–40 ký tự. Những chunk này có độ tương đồng cao với câu hỏi ngắn và chiếm top-3 (q22: top-1/top-2 của B đều là chunk mục lục). Heading con không đánh số (ví dụ `"Continue"`) bị dính vào cuối chunk trước.

**B → C (chỉ thêm filter):** với 7 câu có filter, Evidence Hit@3 tăng từ 3/5 lên 5/5 (dev) và từ 1/2 lên 2/2 (test); câu không có filter giữ nguyên kết quả. Filter không tốn thêm chi phí embedding hay lưu trữ. Đánh đổi: C phụ thuộc vào việc người dùng cung cấp đúng chương.

**Lựa chọn:** C, theo luật chọn trên dev. Kết quả test (5/6) cùng hướng với dev, nhưng mẫu test chỉ có 6 câu: chênh 1 câu tương đương 17 điểm phần trăm, không đủ để kết luận chiến lược tốt nhất tổng quát.

## Lỗi điển hình

| Câu | Cấu hình | Lỗi |
|---|---|---|
| q22 (test) | B, C | Chunk mục lục `"5.2 For loop"` chiếm top-1; câu hỏi không nhắc "dictionary" nên trôi sang chương 5 |
| q23 (test) | A, B | Không có filter → lấy nested list chương 9; chunk A ở trang 251 chỉ có mảnh câu, không có định nghĩa |
| q18 (dev) | A, B | `pop()` của dictionary bị lấn át bởi `pop()` của list ở chương 9; C sửa được nhờ filter |
| q10 (dev) | A, B, C | Đúng trang 234 nhưng câu evidence bị tách qua hai chunk |
| q11 (dev) | A, B, C | Câu về điều kiện của `sort()` nằm ở trang chapter summary 235; các trang 224–226 về sorting được xếp cao hơn |

## Giới hạn và thiên lệch

- Nhãn coherence/grounding/metadata là **bản nháp của AI**, người chấm cuối là tác giả bài: có nguy cơ thiên lệch vì cùng người thiết kế pipeline và benchmark.
- Lỗi chunk mục lục của B được phát hiện **khi đọc trace test**. Pipeline chưa được sửa. Nếu sửa, kết quả test mới không còn là kiểm tra độc lập; cần ghi rõ hoặc tạo tập test mới.
- 1 cuốn sách, 3 chương, 24 câu tiếng Anh do AI soạn: không suy rộng ra corpus khác.
