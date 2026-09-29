# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Nguyễn Hoàng Việt
- **MSSV:** 2A202602602
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/vietnh04/K4-L3A-Day13-NguyenHoangViet-2A202602602-Monitoring-LLMOps
- **Commit SHA cuối:** 13b6066
- **Challenge ID:** day13-k4-l3a-monitoring-llmops-v1
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602602`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.png` |
| Log validator | `evidence/02-log-validator.png` |
| Dashboard validator | `evidence/03-dashboard-validator.png` |
| Structured log | `evidence/04-structured-log.png` |
| PII redaction | `evidence/05-pii-redaction.png` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/10-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 0/100 (thiếu PII/enrichment) | 100/100 | Đạt chuẩn JSON schema, correlation ID, enrichment và scrub PII |
| `validate_dashboard.py` | 6/6 panel | 6/6 panel | Hợp lệ toàn bộ 6 panel contract |
| `pytest` | 23 passed, 4 failed | 27 passed | 100% passed toàn bộ unit và integration tests |
| Số traces hợp lệ | 0 | 22+ traces | Tạo thành công trên project Langfuse cá nhân |
| Số PII leak | Còn leak CCCD/thẻ | 0 | Đã scrub sạch CCCD, điện thoại VN, email, thẻ tín dụng |
| Latency P95 / TTFT P95 | ~160ms / ~55ms | ~155ms / ~52ms (Baseline) | Khi inject incident `rag_slow` tăng vọt lên ~2660ms / 53ms |
| Retrieval success rate | 100% | 100% | Hoạt động bình thường, không ghi nhận dropped docs |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:**
  Middleware trong `app/middleware.py` nhận header `x-request-id`. Nếu hợp lệ theo regex `^req-[0-9a-f]{8}$` thì sử dụng lại, nếu thiếu hoặc sai định dạng thì sinh mới ngẫu nhiên bằng `f"req-{secrets.token_hex(4)}"`. Correlation ID sau đó được bind vào `structlog.contextvars` trước khi request xử lý, và trả về cho client thông qua response header `x-request-id` và `x-response-time`.
- **Các metadata được ghi vào structured log:**
  Toàn bộ các log đều có: `correlation_id`, `user_id_hash` (băm sha256 12 ký tự hex đầu), `session_id`, `feature`, `model`, `env`, `service`, `event`. Khi request hoàn tất (`response_sent`), ghi thêm `latency_ms`, `ttft_ms`, `tokens_in`, `tokens_out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success`.
- **Cách bảo đảm PII được scrub trước khi ghi:**
  Đăng ký hàm `scrub_pii_processor` làm processor đầu tiên trong pipeline của Structlog (`app/logging_config.py`), chạy trước bước render JSON (`JSONRenderer`) và xuất ra console/file. Hàm quét đệ quy mọi kiểu dữ liệu (dict, list, str) và thay thế email, số điện thoại VN (+84, 09x...), CCCD (12 số) và thẻ ngân hàng (16 số) thành các token redact như `[REDACTED_EMAIL]`, `[REDACTED_PHONE_VN]`, `[REDACTED_CCCD]`, `[REDACTED_CREDIT_CARD]`.
- **Cách kiểm chứng kết quả:**
  Chạy `python scripts/validate_logs.py` đạt 100/100 điểm, không phát hiện PII leak trong toàn bộ file `data/logs.jsonl`; đồng thời vượt qua các bài test trong `tests/test_pii.py` và `tests/test_chat_observability.py`.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:**
  Tất cả các trace được gửi trực tiếp về Langfuse project cá nhân `day13-k4-l3a-2A202602602` sử dụng key pair riêng trong `.env`. Các trace đều chứa tag `[lab]`, `[qa]`, model `[claude-sonnet-4-5]` và môi trường `dev`.
- **Cấu trúc root/retrieval/generation observations:**
  - **Root Observation (`lab-agent-run` - loại `agent`):** Đo tổng thể request, ghi nhận correlation ID, user_id_hash, session_id, số tài liệu và query_preview an toàn.
  - **Child Observation 1 (`rag-retrieval` - loại `retriever`):** Đo riêng thời gian tìm kiếm và truy xuất ngữ cảnh từ mock RAG corpus.
  - **Child Observation 2 (`fake-llm-generate` - loại `generation`):** Đo thời gian sinh câu trả lời của LLM, liên kết managed prompt, số token `input_tokens`, `output_tokens` và chi phí ước tính `cost_usd`.
- **Cách nối trace với log:**
  Trường `correlation_id` từ structlog context được truyền vào trường `metadata` của Langfuse trace attributes (`metadata={"correlation_id": correlation_id}`). Khi có request bất thường trong file log, chỉ cần copy correlation ID là tìm ra ngay trace tương ứng trên Langfuse.
- **Prompt name:** `day13-chat`
- **Version/label baseline:** Version 1 mang label `baseline` và `production`.
- **Version/label candidate:** Version 2 mang label `candidate` (bổ sung chỉ dẫn trả lời súc tích).
- **Trace ID của mỗi version:**
  - Version 1: Trace ID `day13-agent-request` (Session `s01`, `prompt_version: "1"`)
  - Version 2: Trace ID `day13-agent-request` (Session `candidate-test`, `prompt_version: "2"`)
- **Cách promote và rollback `production`:**
  - Promote: Trên Langfuse UI, chuyển label `production` từ Version 1 sang Version 2. App nhận version mới tức thì mà không cần restart server hay deploy lại mã nguồn.
  - Rollback: Khi phát hiện sự cố, chuyển ngược label `production` từ Version 2 về Version 1 trên giao diện Langfuse. Request tiếp theo tự động tải lại template ổn định của Version 1.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:**
  1. `latency`: Theo dõi P50, P95, P99 và TTFT P95 nhằm đánh giá tail latency.
  2. `traffic`: Đếm số lượng request/phút để giám sát tải hệ thống.
  3. `errors`: Giám sát error rate và tỷ lệ retrieval thành công (`tool_success`).
  4. `cost`: Tổng chi phí USD tích lũy từ lượng token tiêu thụ.
  5. `tokens`: Lượng input và output tokens tiêu thụ theo thời gian.
  6. `quality`: Điểm chất lượng trung bình của phản hồi dựa trên heuristic proxy.
- **SLO và lý do chọn:**
  SLO `fast_successful_requests`: 99.5% request hoàn thành thành công và có `latency <= 3000ms` trong chu kỳ 28 ngày. Chọn ngưỡng 3000ms vì baseline hệ thống bình thường phản hồi trong ~150ms-200ms; ngưỡng 3000ms bảo vệ chặt chẽ trải nghiệm người dùng chat trực tuyến đồng thời dung thứ cho độ trễ mạng nhất định.
- **Cách tính error budget:**
  Error budget = 100% - 99.5% = 0.5%. Với 100,000 requests trong 28 ngày, hệ thống chỉ cho phép tối đa 500 requests bị chậm (> 3000ms) hoặc bị lỗi (5xx).
- **Ba alert và runbook tương ứng:**
  1. `high_response_latency`: P95 latency > 3000ms trong 5m (Warning, kênh Slack, runbook: `docs/alerts.md#alert-1`).
  2. `elevated_error_rate`: Error rate > 2% trong 3m (Critical, kênh Slack, runbook: `docs/alerts.md#alert-2`).
  3. `retrieval_degradation`: Retrieval success rate < 90% trong 5m (Warning, kênh Slack, runbook: `docs/alerts.md#alert-3`).

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`
- **Khoảng thời gian điều tra:** 16:29:50 – 16:30:10 (29/09/2026)
- **Triệu chứng từ metrics:**
  Trên Dashboard, Panel Latency ghi nhận P95 latency tăng vọt từ baseline ~155ms lên **~2660ms**, vi phạm nghiêm trọng ngưỡng cảnh báo 2000ms.
- **Log line và correlation ID liên quan:**
  - `correlation_id`: `req-c89b99a8` (Session `k4-l3a-challenge-s02`)
  - Log line:
    ```json
    {"service": "api", "latency_ms": 2658, "ttft_ms": 51, "tokens_in": 34, "tokens_out": 100, "cost_usd": 0.001602, "quality_score": 0.9, "tool_name": "retrieval", "tool_success": true, "payload": {"answer_preview": "Starter answer. You should improve this output logic and add better quality chec..."}, "event": "response_sent", "user_id_hash": "aae0b94055a9", "model": "claude-sonnet-4-5", "session_id": "k4-l3a-challenge-s02", "env": "dev", "feature": "monitoring", "correlation_id": "req-c89b99a8", "level": "info", "ts": "2026-09-29T09:30:04.541642Z"}
    ```
- **Trace ID và span gây ảnh hưởng:**
  - Trace `day13-agent-request` trên Langfuse tương ứng `req-c89b99a8`.
  - Span bị nghẽn: **`rag-retrieval`** mất **2.50s** trên tổng số **2.66s** của request (~94% tổng thời gian). Span `fake-llm-generate` chỉ mất **0.15s** (hoàn toàn bình thường).
- **Root cause:**
  Thành phần Retrieval (Vector Database / Mock RAG) gặp sự cố suy giảm hiệu năng (`rag_slow`), gây chậm trễ thêm 2.5 giây khi tìm kiếm tài liệu cho feature `monitoring`.
- **Fix action:**
  Tắt incident giả lập bằng lệnh `python scripts/inject_incident.py --disable`. Trong môi trường thực tế: khởi động lại/scale pod vector database, kiểm tra chỉ mục indexing và bật cache tài liệu.
- **Preventive measure:**
  Cấu hình timeout nghiêm ngặt cho client retrieval (ví dụ: timeout sau 1.5s thì fallback về trả lời không cần context hoặc dùng keyword search tĩnh); áp dụng circuit breaker và alert `high_response_latency` để phản ứng kịp thời trước khi cạn error budget.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:**
  Quyết định thiết lập `capture_input=False` và `capture_output=False` trên các observation decorator của Langfuse nhằm tuân thủ nguyên tắc Zero-PII Leak. Thay vì đưa văn bản thô chưa che lên cloud của bên thứ ba, hệ thống chỉ lưu `query_preview` đã tóm tắt an toàn trong `metadata`, đảm bảo an toàn dữ liệu nhạy cảm của người dùng.
- **Một lỗi/blocker đã gặp:**
  Khi phân tách child spans cho retrieval và LLM generation, ban đầu gặp lỗi do thiếu timestamp và xử lý context observation lồng nhau, khiến test suite báo lỗi biến chưa định nghĩa.
- **Cách tìm nguyên nhân và xử lý:**
  Quan sát kỹ traceback lỗi của pytest, tái cấu trúc việc wrap observation qua các hàm helper nội bộ `@observe` (`_retrieve` và `_generate`) trong `LabAgent` để đảm bảo vừa gửi đủ span lên Langfuse vừa tính toán chính xác latency, cost và quality score cho metric recorder.
- **Cách hiểu luồng Metrics → Logs → Traces:**
  - **Metrics** phát hiện triệu chứng diện rộng và khoảng thời gian xảy ra sự cố (hệ thống bị gì, lúc nào).
  - **Logs** cung cấp chi tiết ngữ cảnh và định danh request cụ thể gặp lỗi qua `correlation_id` (request nào bị ảnh hưởng).
  - **Traces** mổ xẻ chi tiết từng span con bên trong request đó để chỉ điểm chính xác bước bị nghẽn hoặc sập (tại sao và bước nào là nguyên nhân).
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
  Prompt versioning giúp kiểm soát vòng đời thay đổi của ứng dụng AI tương tự như source code; việc giám sát token/cost ngăn chặn thâm hụt ngân sách; còn SLO và cơ chế rollback cho phép đội ngũ vận hành phản ứng tức thì khi prompt mới làm suy giảm chất lượng hoặc tăng vọt độ trễ.
- **Điều quan trọng nhất đã học:**
  Kỹ năng xây dựng hệ thống quan sát toàn diện (Observability) cho ứng dụng LLM, kết hợp nhịp nhàng giữa telemetry local (structured logs, metrics) và distributed tracing trên cloud để điều tra sự cố theo bằng chứng rõ ràng.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**
  Chất lượng phản hồi hiện tại vẫn dùng mô hình đánh giá heuristic đơn giản (`_heuristic_quality`); trong tương lai cần tích hợp thêm LLM-as-a-judge hoặc evaluation dataset định lượng chi tiết hơn.

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối.
- [x] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [x] Incident evidence nối đúng metric → log → trace.
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [x] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [x] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
