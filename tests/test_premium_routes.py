# tests/test_premium_routes.py
"""
Tests for premium_routes.py - Premium strategy API routes.

Phase 3: API route tests.
"""

import pytest
from pydantic import ValidationError

from app.premium_routes import (
    PremiumConfigBase,
    PremiumConfigCreate,
    PremiumConfigUpdate,
    PremiumConfigResponse,
    StrategyStateResponse,
    SchedulerStatusResponse,
    SignalTriggerRequest,
    SignalTriggerResponse,
)


class TestPremiumConfigModels:
    """Test Pydantic models for premium config."""

    def test_premium_config_base_defaults(self):
        """Test PremiumConfigBase default values."""
        config = PremiumConfigBase()

        assert config.signal_tf == "15m"
        assert config.htf_tf == "4h"
        assert config.osc_preset == "preset1"
        assert config.cash_use_pct == 90.0
        assert config.hard_cap_pct == 95.0
        assert config.min_profit_pct == 0.5
        assert config.buy_tranches == [25, 50, 75, 100]
        assert config.sell_tranches == [50, 100]
        assert config.use_4regime is True

    def test_premium_config_base_custom_values(self):
        """Test PremiumConfigBase with custom values."""
        config = PremiumConfigBase(
            signal_tf="1h",
            htf_tf="1D",
            osc_preset="preset2",
            cash_use_pct=80.0,
            hard_cap_pct=90.0,
            buy_tranches=[20, 40, 60, 80, 100],
            use_4regime=False,
        )

        assert config.signal_tf == "1h"
        assert config.htf_tf == "1D"
        assert config.osc_preset == "preset2"
        assert config.cash_use_pct == 80.0
        assert config.hard_cap_pct == 90.0
        assert config.buy_tranches == [20, 40, 60, 80, 100]
        assert config.use_4regime is False

    def test_premium_config_base_validation_cash_use_pct(self):
        """Test validation for cash_use_pct bounds."""
        # Valid values
        PremiumConfigBase(cash_use_pct=0)
        PremiumConfigBase(cash_use_pct=100)
        PremiumConfigBase(cash_use_pct=50.5)

        # Invalid values
        with pytest.raises(ValidationError):
            PremiumConfigBase(cash_use_pct=-1)

        with pytest.raises(ValidationError):
            PremiumConfigBase(cash_use_pct=101)

    def test_premium_config_create_requires_asset_id(self):
        """Test PremiumConfigCreate requires asset_id."""
        config = PremiumConfigCreate(asset_id=1)
        assert config.asset_id == 1

    def test_premium_config_update_no_asset_id(self):
        """Test PremiumConfigUpdate doesn't have asset_id."""
        config = PremiumConfigUpdate()
        assert not hasattr(config, "asset_id") or config.model_fields.get("asset_id") is None

    def test_premium_config_response(self):
        """Test PremiumConfigResponse model."""
        config = PremiumConfigResponse(
            id=1,
            asset_id=10,
            signal_tf="15m",
            htf_tf="4h",
            osc_preset="preset1",
            cash_use_pct=90.0,
            hard_cap_pct=95.0,
            min_profit_pct=0.5,
            buy_tranches=[25, 50, 75, 100],
            sell_tranches=[50, 100],
            buy_after_max="extend",
            sell_after_max="extend",
            buy_stage_1_only=False,
            sell_stage_1_only=False,
            use_lower_band_filter=True,
            use_below_avg_filter=True,
            use_prev_signal_filter=True,
            use_prev_exec_filter=True,
            use_4regime=True,
            r1_pullback_enabled=True,
            r3_breakout_enabled=True,
            one_trade_per_bar=True,
        )

        assert config.id == 1
        assert config.asset_id == 10


class TestStrategyStateResponse:
    """Test StrategyStateResponse model."""

    def test_strategy_state_defaults(self):
        """Test default values."""
        state = StrategyStateResponse(id=1, asset_id=10)

        assert state.buy_stage == 0
        assert state.sell_stage == 0
        assert state.last_buy_signal_price is None
        assert state.r1_pullback_active is False

    def test_strategy_state_with_values(self):
        """Test with actual values."""
        state = StrategyStateResponse(
            id=1,
            asset_id=10,
            buy_stage=2,
            sell_stage=1,
            last_buy_signal_price=50000.0,
            last_buy_exec_price=49500.0,
            r1_pullback_active=True,
        )

        assert state.buy_stage == 2
        assert state.sell_stage == 1
        assert state.last_buy_signal_price == 50000.0
        assert state.r1_pullback_active is True


class TestSchedulerStatusResponse:
    """Test SchedulerStatusResponse model."""

    def test_scheduler_status_model(self):
        """Test scheduler status response."""
        status = SchedulerStatusResponse(
            state="running",
            asset_count=5,
            active_timeframes=["15m", "4h"],
            assets=[
                {
                    "asset_id": 1,
                    "symbol": "BTC-USDT",
                    "exchange": "okx",
                    "timeframe": "15m",
                    "enabled": True,
                    "error_count": 0,
                    "last_processed": None,
                }
            ],
        )

        assert status.state == "running"
        assert status.asset_count == 5
        assert "15m" in status.active_timeframes
        assert len(status.assets) == 1


class TestSignalModels:
    """Test signal request/response models."""

    def test_signal_trigger_request(self):
        """Test signal trigger request model."""
        request = SignalTriggerRequest(asset_id=1)
        assert request.asset_id == 1

    def test_signal_trigger_response_success(self):
        """Test signal trigger response for success."""
        response = SignalTriggerResponse(
            success=True,
            signal_id="sig_1_1000_abc",
            action="buy",
            reason_code="R1_PULLBACK",
            message="Signal generated",
        )

        assert response.success is True
        assert response.signal_id == "sig_1_1000_abc"
        assert response.action == "buy"

    def test_signal_trigger_response_failure(self):
        """Test signal trigger response for failure."""
        response = SignalTriggerResponse(
            success=False,
            message="Asset not found",
        )

        assert response.success is False
        assert response.signal_id is None
        assert response.message == "Asset not found"


class TestConfigValidation:
    """Test configuration validation."""

    def test_buy_after_max_valid_values(self):
        """Test buy_after_max accepts valid values."""
        for value in ["extend", "cycle", "stop"]:
            config = PremiumConfigBase(buy_after_max=value)
            assert config.buy_after_max == value

    def test_sell_after_max_valid_values(self):
        """Test sell_after_max accepts valid values."""
        for value in ["extend", "cycle", "stop"]:
            config = PremiumConfigBase(sell_after_max=value)
            assert config.sell_after_max == value

    def test_tranches_as_list(self):
        """Test tranches accept list of integers."""
        config = PremiumConfigBase(
            buy_tranches=[10, 20, 30, 40, 50],
            sell_tranches=[25, 50, 75, 100],
        )

        assert len(config.buy_tranches) == 5
        assert len(config.sell_tranches) == 4
        assert config.buy_tranches[0] == 10
        assert config.sell_tranches[-1] == 100

    def test_empty_tranches(self):
        """Test empty tranches list."""
        config = PremiumConfigBase(
            buy_tranches=[],
            sell_tranches=[],
        )

        assert config.buy_tranches == []
        assert config.sell_tranches == []


class TestFilterSettings:
    """Test filter settings in config."""

    def test_filter_defaults(self):
        """Test filter default values."""
        config = PremiumConfigBase()

        assert config.use_lower_band_filter is True
        assert config.use_below_avg_filter is True
        assert config.use_prev_signal_filter is True
        assert config.use_prev_exec_filter is True

    def test_all_filters_disabled(self):
        """Test all filters can be disabled."""
        config = PremiumConfigBase(
            use_lower_band_filter=False,
            use_below_avg_filter=False,
            use_prev_signal_filter=False,
            use_prev_exec_filter=False,
        )

        assert config.use_lower_band_filter is False
        assert config.use_below_avg_filter is False
        assert config.use_prev_signal_filter is False
        assert config.use_prev_exec_filter is False


class TestRegimeSettings:
    """Test regime settings in config."""

    def test_regime_defaults(self):
        """Test regime default values."""
        config = PremiumConfigBase()

        assert config.use_4regime is True
        assert config.r1_pullback_enabled is True
        assert config.r3_breakout_enabled is True

    def test_regime_disabled(self):
        """Test disabling 4regime mode."""
        config = PremiumConfigBase(
            use_4regime=False,
            r1_pullback_enabled=False,
            r3_breakout_enabled=False,
        )

        assert config.use_4regime is False
        assert config.r1_pullback_enabled is False
        assert config.r3_breakout_enabled is False


class TestOscPresets:
    """Test oscillator preset validation."""

    def test_preset_values(self):
        """Test preset string values."""
        for preset in ["preset1", "preset2"]:
            config = PremiumConfigBase(osc_preset=preset)
            assert config.osc_preset == preset

    def test_custom_preset(self):
        """Test custom preset name."""
        config = PremiumConfigBase(osc_preset="custom_preset")
        assert config.osc_preset == "custom_preset"
