# Xác nhận Foreign Flow V1 (Confirmation Protocol)

## Mục tiêu

Giai đoạn **xác nhận tiền đăng ký** cho ứng viên Foreign Flow đã đóng băng từ Blind Research V1.  
Không mở lại discovery. Không giao dịch.

## Ranh giới đóng băng

- Dữ liệu trong mẫu kết thúc: **2026-08-24**
- T0 xác nhận chỉ sau ngày này

## Ứng viên đóng băng

| Vai trò | Feature | Horizon | Định nghĩa |
|--------|---------|---------|------------|
| Primary | `abn_abs_z20` | T10 | `|net_z_60| > 2.0` |
| Secondary | `net_hi_pct90` | T10 | `net_pct_252 >= 0.90` |
| Anti-edge (tuỳ chọn) | `streak_neg_le_m5` | T10 | `net_streak <= -5` |

Đánh giá **độc lập**. Secondary không cứu được Primary.

## Trạng thái cho phép

`WAITING_FOR_EVENTS` | `WAITING_FOR_MATURITY` | `CONFIRMATION_IN_PROGRESS` | `CONFIRMED` | `FAILED_CONFIRMATION` | `INCONCLUSIVE`

## Operator xem gì

Chỉ: candidate, state, triggers, matured T10, unique symbols, unique dates, data-quality status, đã được phép chốt chưa.  
Không khuyến khích giao dịch từ kết quả tạm.

## Artefact

Thư mục này: `diagnostics/foreign_flow_confirmation_v1/`  
Ledger runtime: `data/foreign_flow_confirmation/`  
Code: `modules/foreign_flow_confirmation/`

## Verdict thiết kế

Xem `CONFIRMATION_MANIFEST.json` → `readiness_verdict`.
