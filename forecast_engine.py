"""
=========================================================
Mr.BOT Forecast Intelligence Engine
Version : V1.0
Author  : Mr.BOT Architecture
=========================================================

Forecast Intelligence là bộ não dự báo thị trường.

Nhiệm vụ:

- Phân tích trạng thái hiện tại
- Dự báo trạng thái tương lai
- Tính Forecast Score
- Tính Confidence
- Tính Reliability
- Giải thích lý do dự báo
- Lưu lịch sử Forecast
- Chuẩn bị dữ liệu cho Learning và Optimizer

Lưu ý:

Không được đưa ra quyết định mua bán.

Decision Engine mới là nơi quyết định hành động.

"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class ForecastResult:
    """
    Kết quả chuẩn của Forecast Intelligence.

    Đây là ngôn ngữ giao tiếp chính thức giữa:

    - Forecast Engine
    - Forecast Memory
    - Forecast Learning
    - Forecast Optimizer
    - Decision Engine

    Trong giai đoạn Foundation, chỉ có score và text là dữ liệu
    bắt buộc phải có.

    Các trường nâng cao được chuẩn bị sẵn nhưng chưa bắt buộc sử dụng.
    """

    # =====================================================
    # CORE RESULT
    # =====================================================

    score: float
    text: str

    # =====================================================
    # FORECAST INTELLIGENCE
    # =====================================================

    direction: Optional[str] = None
    confidence: Optional[float] = None
    reliability: Optional[float] = None
    regime: Optional[str] = None

    # =====================================================
    # EXPLAINABILITY
    # =====================================================

    reasons: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)

    # =====================================================
    # LEARNING METADATA
    # =====================================================

    pattern_id: Optional[str] = None
    sample_count: int = 0

    # =====================================================
    # EXTENSION DATA
    # =====================================================

    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """
        Chuẩn hóa và kiểm tra dữ liệu ngay khi ForecastResult được tạo.
        """

        self.score = self._normalize_number(
            value=self.score,
            field_name="score",
        )

        self.text = str(self.text or "").strip()

        if self.confidence is not None:
            self.confidence = self._normalize_percentage(
                value=self.confidence,
                field_name="confidence",
            )

        if self.reliability is not None:
            self.reliability = self._normalize_percentage(
                value=self.reliability,
                field_name="reliability",
            )

        self.sample_count = max(0, int(self.sample_count or 0))

        self.reasons = self._normalize_string_list(self.reasons)
        self.risk_flags = self._normalize_string_list(self.risk_flags)

        if not isinstance(self.metadata, dict):
            self.metadata = {}

    @staticmethod
    def _normalize_number(
        value: Any,
        field_name: str,
    ) -> float:
        """
        Chuyển dữ liệu sang float và báo lỗi rõ ràng nếu không hợp lệ.
        """

        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{field_name} phải là một giá trị số, "
                f"nhưng nhận được: {value!r}"
            ) from exc

    @staticmethod
    def _normalize_percentage(
        value: Any,
        field_name: str,
    ) -> float:
        """
        Chuẩn hóa confidence và reliability về vùng 0-100.
        """

        normalized_value = ForecastResult._normalize_number(
            value=value,
            field_name=field_name,
        )

        return max(0.0, min(100.0, normalized_value))

    @staticmethod
    def _normalize_string_list(values: Any) -> List[str]:
        """
        Loại dữ liệu rỗng và chuẩn hóa danh sách giải thích.
        """

        if values is None:
            return []

        if isinstance(values, str):
            values = [values]

        if not isinstance(values, (list, tuple, set)):
            return []

        normalized_values: List[str] = []

        for value in values:
            text = str(value or "").strip()

            if text:
                normalized_values.append(text)

        return normalized_values

    def to_dict(self) -> Dict[str, Any]:
        """
        Chuyển ForecastResult thành dictionary.

        Dùng khi:

        - Hiển thị trên giao diện
        - Lưu JSON
        - Ghi Forecast Memory
        - Truyền sang Learning hoặc Optimizer
        """

        return asdict(self)

    def to_legacy_tuple(self) -> tuple[float, str]:
        """
        Trả kết quả theo định dạng Forecast cũ:

            score, text

        Hàm này giúp tích hợp kiến trúc mới mà chưa cần sửa ngay
        toàn bộ code cũ trong ứng dụng.
        """

        return self.score, self.text

    def has_warning(self) -> bool:
        """
        Kiểm tra Forecast có cờ rủi ro hay không.
        """

        return bool(self.risk_flags)

    def is_complete(self) -> bool:
        """
        Kiểm tra ForecastResult đã có đủ dữ liệu cốt lõi hay chưa.
        """

        return bool(self.text) and self.score is not None


class ForecastEngine:
    """
    Forecast Intelligence Engine.

    Giai đoạn V1.0 Foundation:

    - Chuẩn hóa đầu ra bằng ForecastResult
    - Chưa thay đổi thuật toán Forecast hiện tại
    - Chưa triển khai Learning
    - Chưa triển khai Optimizer
    - Không đưa ra quyết định mua bán
    """

    VERSION = "1.0"

    def build_result(
        self,
        score: float,
        text: str,
        *,
        direction: Optional[str] = None,
        confidence: Optional[float] = None,
        reliability: Optional[float] = None,
        regime: Optional[str] = None,
        reasons: Optional[List[str]] = None,
        risk_flags: Optional[List[str]] = None,
        pattern_id: Optional[str] = None,
        sample_count: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ForecastResult:
        """
        Đóng gói kết quả Forecast thành ForecastResult.

        Hàm này chưa tính toán Forecast Score.

        Nó chỉ nhận kết quả từ logic Forecast hiện tại
        và chuyển sang ngôn ngữ mới của Forecast Intelligence.
        """

        return ForecastResult(
            score=score,
            text=text,
            direction=direction,
            confidence=confidence,
            reliability=reliability,
            regime=regime,
            reasons=reasons or [],
            risk_flags=risk_flags or [],
            pattern_id=pattern_id,
            sample_count=sample_count,
            metadata=metadata or {},
        )


def create_forecast_result(
    score: float,
    text: str,
    **kwargs: Any,
) -> ForecastResult:
    """
    Hàm tiện ích để tích hợp nhanh với code Forecast hiện tại.

    Code cũ:

        return score, text

    Code mới:

        return create_forecast_result(
            score=score,
            text=text,
        )

    Trong giai đoạn chuyển tiếp, nơi nào vẫn cần tuple cũ có thể dùng:

        result = create_forecast_result(score, text)
        score, text = result.to_legacy_tuple()
    """

    engine = ForecastEngine()

    return engine.build_result(
        score=score,
        text=text,
        **kwargs,
    )


__all__ = [
    "ForecastResult",
    "ForecastEngine",
    "create_forecast_result",
]
