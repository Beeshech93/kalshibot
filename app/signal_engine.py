"""Signal Engine for BTC SCALPING AI.
Combines Trend, Momentum, Volume, Multi-Timeframe Confirmation, and Kalshi Contract Conditions
to generate YES, NO, or WAIT signals with a 0-100 confidence score.
"""

from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Optional
from app.technical_analysis import IndicatorSnapshot

logger = logging.getLogger("SignalEngine")


@dataclass
class SignalDecision:
    signal_type: str  # YES, NO, WAIT
    confidence_score: float  # 0 to 100 (Heuristic model score, not true probability)
    technical_justification: str
    btc_price: float
    market_ticker: str
    contract_price: Optional[float]
    reference_price: Optional[float]
    indicators: Dict[str, Any]
    time_remaining_str: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_type": self.signal_type,
            "confidence_score": round(self.confidence_score, 1),
            "technical_justification": self.technical_justification,
            "btc_price": round(self.btc_price, 2),
            "market_ticker": self.market_ticker,
            "contract_price": self.contract_price,
            "reference_price": self.reference_price,
            "indicators": self.indicators,
            "time_remaining_str": self.time_remaining_str
        }


class SignalEngine:
    """Evaluates technical indicators and Kalshi contract state to emit trading signals."""

    def __init__(self, min_confidence: float = 60.0):
        self.min_confidence = min_confidence

    def evaluate(
        self,
        mtf_analysis: Dict[str, Optional[IndicatorSnapshot]],
        kalshi_market: Optional[Dict[str, Any]],
        current_btc_price: float
    ) -> SignalDecision:
        """Main signal evaluation logic combining multi-timeframe indicators and contract conditions."""
        ind_15m = mtf_analysis.get("15m")
        ind_5m = mtf_analysis.get("5m")
        ind_1m = mtf_analysis.get("1m")

        # 1. Base validation
        if not ind_15m or not ind_5m:
            return SignalDecision(
                signal_type="WAIT",
                confidence_score=0.0,
                technical_justification="Datos insuficientes de velas cerradas en temporalidades clave (15m/5m).",
                btc_price=current_btc_price,
                market_ticker=kalshi_market.get("ticker", "N/A") if kalshi_market else "N/A",
                contract_price=None,
                reference_price=kalshi_market.get("strike_price") if kalshi_market else None,
                indicators={},
                time_remaining_str="N/A"
            )

        # 2. Kalshi contract checks
        market_ticker = "N/A"
        time_rem_str = "N/A"
        ref_strike = None
        contract_yes_ask = None
        contract_no_ask = None

        if kalshi_market:
            market_ticker = kalshi_market.get("ticker", "N/A")
            time_rem_str = kalshi_market.get("time_remaining_str", "N/A")
            ref_strike = kalshi_market.get("strike_price")
            contract_yes_ask = kalshi_market.get("yes_ask")
            contract_no_ask = kalshi_market.get("no_ask")
            sec_rem = kalshi_market.get("seconds_remaining", 0)

            # Contract time sanity check (less than 90 seconds is too close for a scalping entry)
            if sec_rem > 0 and sec_rem < 90:
                return SignalDecision(
                    signal_type="WAIT",
                    confidence_score=25.0,
                    technical_justification=f"Tiempo restante crítico ({sec_rem}s). Contrato próximo a liquidación; riesgo excesivo.",
                    btc_price=current_btc_price,
                    market_ticker=market_ticker,
                    contract_price=contract_yes_ask,
                    reference_price=ref_strike,
                    indicators=ind_15m.to_dict(),
                    time_remaining_str=time_rem_str
                )

        # 3. Scoring System (0 - 100)
        yes_score = 0.0
        no_score = 0.0
        justifications = []

        # A. Trend on 15m (Weight: 30)
        if ind_15m.trend == "BULLISH":
            yes_score += 30.0
            justifications.append("15m: Estructura alcista (EMA 9 > 21 > 50 con precio superior).")
        elif ind_15m.trend == "BEARISH":
            no_score += 30.0
            justifications.append("15m: Estructura bajista (EMA 9 < 21 < 50 con precio inferior).")
        elif ind_15m.trend == "MILD_BULLISH":
            yes_score += 15.0
            justifications.append("15m: EMA 9 cruzando al alza sobre EMA 21.")
        elif ind_15m.trend == "MILD_BEARISH":
            no_score += 15.0
            justifications.append("15m: EMA 9 cruzando a la baja bajo EMA 21.")
        else:
            justifications.append("15m: Tendencia neutra / consolidación.")

        # B. Momentum on 15m: MACD + RSI (Weight: 25)
        if ind_15m.macd_histogram > 0 and ind_15m.macd_line > ind_15m.macd_signal:
            yes_score += 15.0
            justifications.append("15m: MACD con histograma positivo y cruce alcista.")
        elif ind_15m.macd_histogram < 0 and ind_15m.macd_line < ind_15m.macd_signal:
            no_score += 15.0
            justifications.append("15m: MACD con histograma negativo y cruce bajista.")

        if 52.0 <= ind_15m.rsi_14 <= 70.0:
            yes_score += 10.0
            justifications.append(f"15m: RSI({ind_15m.rsi_14:.1f}) con momentum alcista saludable.")
        elif 30.0 <= ind_15m.rsi_14 <= 48.0:
            no_score += 10.0
            justifications.append(f"15m: RSI({ind_15m.rsi_14:.1f}) con presión vendedora controlada.")
        elif ind_15m.rsi_14 > 75.0:
            # Overbought penalty
            yes_score -= 10.0
            justifications.append(f"15m: RSI({ind_15m.rsi_14:.1f}) en sobrecompra extrema (riesgo de retroceso).")
        elif ind_15m.rsi_14 < 25.0:
            # Oversold penalty
            no_score -= 10.0
            justifications.append(f"15m: RSI({ind_15m.rsi_14:.1f}) en sobreventa extrema (riesgo de rebote).")

        # C. Multi-Timeframe Alignment: 5m & 1m (Weight: 25)
        if ind_5m.trend in ("BULLISH", "MILD_BULLISH"):
            yes_score += 15.0
            justifications.append("5m: Tendencia de corto plazo confirma dirección alcista.")
        elif ind_5m.trend in ("BEARISH", "MILD_BEARISH"):
            no_score += 15.0
            justifications.append("5m: Tendencia de corto plazo confirma dirección bajista.")

        if ind_1m:
            if ind_1m.momentum in ("STRONG_UP", "WEAK_UP"):
                yes_score += 10.0
            elif ind_1m.momentum in ("STRONG_DOWN", "WEAK_DOWN"):
                no_score += 10.0

        # D. Volume Confirmation (Weight: 20)
        if ind_15m.volume_abnormal:
            justifications.append("15m: Volumen anormal detectado (>2x promedio); movimiento impulsivo.")
            if yes_score > no_score:
                yes_score += 20.0
            else:
                no_score += 20.0
        elif ind_15m.volume_confirmed:
            justifications.append("15m: Volumen superior a la media de 20 periodos.")
            if yes_score > no_score:
                yes_score += 10.0
            else:
                no_score += 10.0
        else:
            justifications.append("15m: Volumen bajo / sin confirmación institucional.")

        # E. Relative Strike comparison (if available)
        if ref_strike and ref_strike > 0:
            diff_pct = ((current_btc_price - ref_strike) / ref_strike) * 100.0
            if diff_pct > 0.05 and yes_score > no_score:
                yes_score += 5.0
                justifications.append(f"Spot BTC (${current_btc_price:,.2f}) se encuentra por encima del Strike (${ref_strike:,.2f}).")
            elif diff_pct < -0.05 and no_score > yes_score:
                no_score += 5.0
                justifications.append(f"Spot BTC (${current_btc_price:,.2f}) se encuentra por debajo del Strike (${ref_strike:,.2f}).")

        # Cap scores between 0 and 100
        yes_score = min(100.0, max(0.0, yes_score))
        no_score = min(100.0, max(0.0, no_score))

        # 4. Final Decision
        final_signal = "WAIT"
        final_confidence = 0.0
        selected_contract_price = None

        if yes_score >= self.min_confidence and yes_score > (no_score + 15.0):
            final_signal = "YES"
            final_confidence = yes_score
            selected_contract_price = contract_yes_ask
        elif no_score >= self.min_confidence and no_score > (yes_score + 15.0):
            final_signal = "NO"
            final_confidence = no_score
            selected_contract_price = contract_no_ask
        else:
            final_signal = "WAIT"
            final_confidence = max(yes_score, no_score)
            selected_contract_price = contract_yes_ask
            justifications.append(f"Señales técnicas mixtas o puntuación inferior al umbral mínimo ({self.min_confidence:.0f}%).")

        justification_text = " | ".join(justifications)

        return SignalDecision(
            signal_type=final_signal,
            confidence_score=final_confidence,
            technical_justification=justification_text,
            btc_price=current_btc_price,
            market_ticker=market_ticker,
            contract_price=selected_contract_price,
            reference_price=ref_strike,
            indicators=ind_15m.to_dict(),
            time_remaining_str=time_rem_str
        )

