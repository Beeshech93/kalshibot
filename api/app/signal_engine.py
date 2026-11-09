"""Signal Engine for BTC SCALPING AI.
Combines Quantitative Binary Option Pricing (Black-Scholes probability),
Kalshi Order Book Implied Probability, Distance to Strike (TO BEAT),
and Multi-Timeframe Technical Momentum (1m, 5m, 15m) to determine
whether ALTO (SUBIDA / YES) or BAJO (BAJADA / NO) is most probable.
"""

from dataclasses import dataclass
import logging
import math
from typing import Any, Dict, List, Optional
from app.technical_analysis import IndicatorSnapshot

logger = logging.getLogger("SignalEngine")


@dataclass
class SignalDecision:
    signal_type: str  # YES, NO, WAIT
    direction_label: str  # ALTO (SUBIDA / YES), BAJO (BAJADA / NO), ESPERA (WAIT)
    confidence_score: float  # 0 to 100
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
            "direction_label": self.direction_label,
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
    """Quantitative decision engine for Kalshi BTC binary contracts."""

    def __init__(self, min_confidence: float = 58.0, annual_vol: float = 0.55):
        self.min_confidence = min_confidence
        self.annual_vol = annual_vol

    @staticmethod
    def _normal_cdf(x: float) -> float:
        """Standard Normal Cumulative Distribution Function Phi(x)."""
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    def calculate_bs_probability(self, spot: float, strike: float, seconds_remaining: int) -> float:
        """Calculates Black-Scholes implied binary call probability P(Spot >= Strike at expiration).
        Returns probability of YES between 0.0 and 100.0.
        """
        if strike <= 0 or spot <= 0:
            return 50.0

        # Time to expiration in years (clamped to minimum 30 seconds to prevent division by zero)
        tau = max(30, seconds_remaining) / (365.25 * 24.0 * 3600.0)
        sigma_sqrt_tau = self.annual_vol * math.sqrt(tau)

        if sigma_sqrt_tau <= 0:
            return 100.0 if spot >= strike else 0.0

        # z-score for binary cash-or-nothing call
        # d2 = [ln(S/K) - 0.5 * sigma^2 * tau] / (sigma * sqrt(tau))
        d2 = (math.log(spot / strike) - (0.5 * (self.annual_vol ** 2) * tau)) / sigma_sqrt_tau
        prob_yes = self._normal_cdf(d2) * 100.0
        return max(1.0, min(99.0, prob_yes))

    def evaluate(
        self,
        mtf_analysis: Dict[str, Optional[IndicatorSnapshot]],
        kalshi_market: Optional[Dict[str, Any]],
        current_btc_price: float
    ) -> SignalDecision:
        """Evaluates whether YES (ALTO) or NO (BAJO) is quantitatively and technically most probable."""
        ind_15m = mtf_analysis.get("15m")
        ind_5m = mtf_analysis.get("5m")
        ind_1m = mtf_analysis.get("1m")

        if not ind_15m or not ind_5m:
            return SignalDecision(
                signal_type="WAIT",
                direction_label="ESPERA (WAIT)",
                confidence_score=0.0,
                technical_justification="Datos insuficientes de velas cerradas en temporalidades clave (15m/5m).",
                btc_price=current_btc_price,
                market_ticker=kalshi_market.get("ticker", "N/A") if kalshi_market else "N/A",
                contract_price=None,
                reference_price=kalshi_market.get("strike_price") if kalshi_market else None,
                indicators={},
                time_remaining_str="N/A"
            )

        market_ticker = kalshi_market.get("ticker", "N/A") if kalshi_market else "N/A"
        time_rem_str = kalshi_market.get("time_remaining_str", "N/A") if kalshi_market else "N/A"
        ref_strike = kalshi_market.get("strike_price") if kalshi_market else None
        contract_yes_ask = kalshi_market.get("yes_ask") if kalshi_market else None
        contract_no_ask = kalshi_market.get("no_ask") if kalshi_market else None
        sec_rem = kalshi_market.get("seconds_remaining", 0) if kalshi_market else 0

        # Critical expiration guard (<= 60s remaining is too late for reliable execution)
        if 0 < sec_rem <= 60:
            return SignalDecision(
                signal_type="WAIT",
                direction_label="🟡 ESPERA (WAIT)",
                confidence_score=20.0,
                technical_justification=f"Tiempo restante crítico ({sec_rem}s <= 60s). Contrato en proceso de liquidación final.",
                btc_price=current_btc_price,
                market_ticker=market_ticker,
                contract_price=contract_yes_ask,
                reference_price=ref_strike,
                indicators=ind_15m.to_dict(),
                time_remaining_str=time_rem_str
            )

        # ---------------------------------------------------------------------
        # 1. Component A: Technical Indicator Probability (1m, 5m, 15m)
        # ---------------------------------------------------------------------
        tech_score = 50.0  # Base neutral
        justifications = []

        # 15m Trend & EMAs
        if ind_15m.trend == "BULLISH":
            tech_score += 15.0
            justifications.append("15m: EMA 9>21>50 alcista")
        elif ind_15m.trend == "BEARISH":
            tech_score -= 15.0
            justifications.append("15m: EMA 9<21<50 bajista")
        elif ind_15m.trend == "MILD_BULLISH":
            tech_score += 8.0
        elif ind_15m.trend == "MILD_BEARISH":
            tech_score -= 8.0

        # 15m Momentum (MACD & RSI)
        if ind_15m.macd_histogram > 0:
            tech_score += 10.0
        else:
            tech_score -= 10.0

        if ind_15m.rsi_14 >= 55.0:
            tech_score += 10.0
            justifications.append(f"15m: RSI({ind_15m.rsi_14:.1f}) comprador")
        elif ind_15m.rsi_14 <= 45.0:
            tech_score -= 10.0
            justifications.append(f"15m: RSI({ind_15m.rsi_14:.1f}) vendedor")

        # 5m & 1m Micro-Structure
        if ind_5m.trend in ("BULLISH", "MILD_BULLISH"):
            tech_score += 10.0
        elif ind_5m.trend in ("BEARISH", "MILD_BEARISH"):
            tech_score -= 10.0

        if ind_1m:
            if ind_1m.close_price > ind_1m.ema_9:
                tech_score += 5.0
            else:
                tech_score -= 5.0

        tech_prob_yes = max(5.0, min(95.0, tech_score))

        # ---------------------------------------------------------------------
        # 2. Component B: Binary Option Probability vs Strike (TO BEAT)
        # ---------------------------------------------------------------------
        bs_prob_yes = 50.0
        dist_str = ""
        if ref_strike and ref_strike > 0:
            diff = current_btc_price - ref_strike
            diff_pct = (diff / ref_strike) * 100.0
            sign = "+" if diff >= 0 else ""
            dist_str = f"Spot (${current_btc_price:,.2f}) vs Strike (${ref_strike:,.2f}) [{sign}${diff:.2f}, {sign}{diff_pct:.3f}%]"
            justifications.append(dist_str)

            bs_prob_yes = self.calculate_bs_probability(current_btc_price, ref_strike, sec_rem)
            justifications.append(f"Probabilidad matemática Black-Scholes: {bs_prob_yes:.1f}% YES")

        # ---------------------------------------------------------------------
        # 3. Component C: Kalshi Market Consensus & Orderbook Probability
        # ---------------------------------------------------------------------
        mkt_prob_yes = bs_prob_yes
        if contract_yes_ask is not None and contract_no_ask is not None:
            # Implied market probability from ask prices
            # If yes_ask is 80 and no_ask is 22, midpoint yes is ~79
            mkt_prob_yes = float(contract_yes_ask)
            justifications.append(f"Mercado Kalshi: YES={contract_yes_ask:.0f}¢ | NO={contract_no_ask:.0f}¢")

        # ---------------------------------------------------------------------
        # 4. Ensemble Probability Integration
        # Weighting: Distance & Black-Scholes (45%), Kalshi Market (35%), Indicators (20%)
        # ---------------------------------------------------------------------
        if ref_strike and ref_strike > 0:
            final_prob_yes = (0.45 * bs_prob_yes) + (0.35 * mkt_prob_yes) + (0.20 * tech_prob_yes)
        else:
            final_prob_yes = tech_prob_yes

        final_prob_no = 100.0 - final_prob_yes

        # ---------------------------------------------------------------------
        # 5. Final Classification (ALTO / BAJO / ESPERA)
        # ---------------------------------------------------------------------
        if final_prob_yes >= self.min_confidence:
            final_signal = "YES"
            direction_label = "🟢 ALTO (SUBIDA / YES)"
            confidence = final_prob_yes
            contract_price = contract_yes_ask
            justifications.insert(0, f"Veredicto ALTO: Probabilidad estimada de {final_prob_yes:.1f}% para cerrar por encima de ${ref_strike:,.2f}.")
        elif final_prob_no >= self.min_confidence:
            final_signal = "NO"
            direction_label = "🔴 BAJO (BAJADA / NO)"
            confidence = final_prob_no
            contract_price = contract_no_ask
            justifications.insert(0, f"Veredicto BAJO: Probabilidad estimada de {final_prob_no:.1f}% para cerrar por debajo de ${ref_strike:,.2f}.")
        else:
            final_signal = "WAIT"
            direction_label = "🟡 ESPERA (WAIT)"
            confidence = max(final_prob_yes, final_prob_no)
            contract_price = contract_yes_ask
            justifications.insert(0, f"Veredicto ESPERA: Probabilidades equilibradas ({final_prob_yes:.1f}% YES vs {final_prob_no:.1f}% NO). Zona de indecisión.")

        justification_text = " | ".join(justifications)

        return SignalDecision(
            signal_type=final_signal,
            direction_label=direction_label,
            confidence_score=confidence,
            technical_justification=justification_text,
            btc_price=current_btc_price,
            market_ticker=market_ticker,
            contract_price=contract_price,
            reference_price=ref_strike,
            indicators=ind_15m.to_dict(),
            time_remaining_str=time_rem_str
        )
