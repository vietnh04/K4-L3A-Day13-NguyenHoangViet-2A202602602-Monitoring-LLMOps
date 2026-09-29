# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert 1

- Tên: high_response_latency
- Severity: warning
- Duration: 5m
- Kênh thông báo: Slack (#alerts-llmops)
- SLI/SLO liên quan: `fast_successful_requests` (SLO target: 99.5% requests <= 3000ms trong 28d)
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` duy trì liên tục trong ít nhất 5 phút.
- Ảnh hưởng tới người dùng: Người dùng nhận phản hồi chat chậm trễ bất thường, giao diện chờ lâu gây ức chế, tăng nguy cơ timeout phía client và bào mòn error budget của SLO.
- Ba bước kiểm tra đầu tiên:
  1. Mở Panel Latency trên Dashboard để xác định xu hướng P50/P95/P99 và TTFT (Time To First Token) bắt đầu tăng từ thời điểm nào.
  2. Lọc file `data/logs.jsonl` tìm các log sự kiện `response_sent` có `latency_ms > 3000` để trích xuất `correlation_id` của các request bị ảnh hưởng.
  3. Mở Langfuse theo `correlation_id` đó để quan sát Trace Waterfall: xác định bước con gây nghẽn là `rag-retrieval` (vector DB chậm/chờ mạng) hay `fake-llm-generate` (sinh token quá dài).
- Mitigation tạm thời:
  - Nếu do retrieval nghẽn: tạm thời bật chế độ cache ngữ cảnh, giảm số lượng tài liệu `top-k` hoặc cấu hình fallback sang fast keyword search.
  - Nếu do LLM generation kéo dài: giới hạn `max_tokens` của response, hoặc rollback prompt về version ngắn hơn.
- Owner: oncall-llmops

## Alert 2

- Tên: elevated_error_rate
- Severity: critical
- Duration: 3m
- Kênh thông báo: Slack (#alerts-critical)
- SLI/SLO liên quan: Guardrail `error_rate_pct_max: 2%` và SLI `fast_successful_requests`
- Điều kiện và thời gian duy trì: `error_rate > 2%` (tỷ lệ sự kiện `request_failed` / `request_received`) kéo dài trong 3 phút.
- Ảnh hưởng tới người dùng: Người dùng nhận thông báo lỗi 500 hoặc app không thể phản hồi câu hỏi, gây gián đoạn dịch vụ nghiêm trọng và đốt cháy nhanh chóng error budget.
- Ba bước kiểm tra đầu tiên:
  1. Kiểm tra Panel Errors trên Dashboard để phân tích `error_type` (ví dụ: `RuntimeError`, `TimeoutError`, `KeyError`) và số lượng request thất bại.
  2. Truy vấn `data/logs.jsonl` với điều kiện `event == "request_failed"` để đọc thông tin lỗi chi tiết trong `payload.detail` và lấy `correlation_id`.
  3. Tra cứu `correlation_id` trên Langfuse để kiểm tra span bị lỗi và stack trace xem lỗi phát sinh từ code nội bộ, prompt render hay phụ thuộc bên ngoài.
- Mitigation tạm thời:
  - Nếu lỗi xảy ra ngay sau khi cập nhật prompt: lập tức rollback label `production` về version ổn định trước đó trên Langfuse.
  - Nếu do dịch vụ phụ thuộc sập: kích hoạt circuit breaker trả về câu trả lời fallback an toàn thân thiện thay vì ném lỗi 500 ra client.
- Owner: oncall-llmops

## Alert 3

- Tên: retrieval_degradation
- Severity: warning
- Duration: 5m
- Kênh thông báo: Slack (#alerts-rag)
- SLI/SLO liên quan: Guardrail `retrieval_success_rate_pct_min: 90%`
- Điều kiện và thời gian duy trì: Tỷ lệ truy xuất tài liệu thành công `retrieval_success_rate < 90%` trong 5 phút.
- Ảnh hưởng tới người dùng: AI trả lời thiếu tài liệu hỗ trợ, tăng nguy cơ hallucination hoặc phải dùng câu trả lời chung chung (fallback), làm giảm chất lượng phản hồi (`quality_score`).
- Ba bước kiểm tra đầu tiên:
  1. Kiểm tra Panel Errors / Quality trên Dashboard để xem tỷ lệ retrieval thành công và điểm chất lượng có sụt giảm đồng thời không.
  2. Lọc `data/logs.jsonl` tìm các log có `tool_success == false` hoặc kiểm tra các log có `doc_count == 0` để lấy các `correlation_id` bị mất ngữ cảnh.
  3. Vào Langfuse xem span `rag-retrieval` trong các trace đó để kiểm tra mã lỗi kết nối, timeout hoặc phân tích embedding query.
- Mitigation tạm thời:
  - Khởi động lại hoặc restart pod dịch vụ vector database / retrieval service.
  - Tạm thời bật chế độ static corpus retrieval fallback để đảm bảo bot vẫn có dữ liệu cơ bản phục vụ người dùng.
- Owner: oncall-rag
