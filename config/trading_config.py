"""Central configuration for trading system.

This module defines all supported LLM models, tradeable coins, 
and trading frequencies. Used for validation and UI dropdowns.
"""

# =============================================================================
# SUPPORTED LLM MODELS
# =============================================================================
# Models that can be used for trading decisions
# Format: {model_id: {display_name, provider, description, cost_tier}}

SUPPORTED_LLM_MODELS = {
    "gpt-5-mini": {
        "display_name": "GPT-5 Mini",
        "provider": "openai",
        "description": "Fast and cost-effective, good for frequent trading",
        "cost_tier": "low",
    },
    "gpt-5.1": {
        "display_name": "GPT-5",
        "provider": "openai",
        "description": "Most capable, best for complex analysis",
        "cost_tier": "high",
    },
    "gpt-5-nano": {
        "display_name": "GPT-5 Nano",
        "provider": "openai",
        "description": "Fastest and cheapest, basic analysis",
        "cost_tier": "lowest",
    },
}

# Default model if none specified
DEFAULT_LLM_MODEL = "gpt-5-mini"


# =============================================================================
# SUPPORTED COINS (for Hyperliquid Perps)
# =============================================================================
# Coins available for trading on Hyperliquid perpetuals
# Must match Hyperliquid's supported assets

SUPPORTED_COINS = {
    "BTC": {
        "display_name": "Bitcoin",
        "symbol": "BTC/USDT",
        "hyperliquid_asset_id": 0,
        "min_size": 0.001,
    },
    "ETH": {
        "display_name": "Ethereum",
        "symbol": "ETH/USDT",
        "hyperliquid_asset_id": 1,
        "min_size": 0.01,
    },
    "SOL": {
        "display_name": "Solana",
        "symbol": "SOL/USDT",
        "hyperliquid_asset_id": 5,
        "min_size": 0.1,
    },
    "DOGE": {
        "display_name": "Dogecoin",
        "symbol": "DOGE/USDT",
        "hyperliquid_asset_id": 27,
        "min_size": 10,
    },
    "XRP": {
        "display_name": "Ripple",
        "symbol": "XRP/USDT",
        "hyperliquid_asset_id": 11,
        "min_size": 1,
    },
    "BNB": {
        "display_name": "Binance Coin",
        "symbol": "BNB/USDT",
        "hyperliquid_asset_id": 12,
        "min_size": 0.01,
    },
    "ARB": {
        "display_name": "Arbitrum",
        "symbol": "ARB/USDT",
        "hyperliquid_asset_id": 42,
        "min_size": 1,
    },
    "AVAX": {
        "display_name": "Avalanche",
        "symbol": "AVAX/USDT",
        "hyperliquid_asset_id": 10,
        "min_size": 0.1,
    },
    "LINK": {
        "display_name": "Chainlink",
        "symbol": "LINK/USDT",
        "hyperliquid_asset_id": 6,
        "min_size": 0.1,
    },
    "MATIC": {
        "display_name": "Polygon",
        "symbol": "MATIC/USDT",
        "hyperliquid_asset_id": 8,
        "min_size": 1,
    },
}

# For convenience - list of coin tickers
SUPPORTED_COIN_LIST = list(SUPPORTED_COINS.keys())


# =============================================================================
# TRADING FREQUENCIES
# =============================================================================
# How often the scheduler can run a trader

SUPPORTED_FREQUENCIES = {
    "1min": {
        "display_name": "Every Minute",
        "description": "Very active trading, high API costs",
        "interval_minutes": 1,
    },
    "5min": {
        "display_name": "Every 5 Minutes",
        "description": "Active trading",
        "interval_minutes": 5,
    },
    "15min": {
        "display_name": "Every 15 Minutes",
        "description": "Moderate frequency",
        "interval_minutes": 15,
    },
    "1hour": {
        "display_name": "Every Hour",
        "description": "Recommended for most strategies",
        "interval_minutes": 60,
    },
    "4hour": {
        "display_name": "Every 4 Hours",
        "description": "Swing trading",
        "interval_minutes": 240,
    },
    "1day": {
        "display_name": "Daily",
        "description": "Long-term positions, lowest API costs",
        "interval_minutes": 1440,
    },
}

DEFAULT_FREQUENCY = "1hour"


# =============================================================================
# RISK MANAGEMENT DEFAULTS
# =============================================================================
# Default settings for trader risk management

# Uncertainty threshold: if LLM's uncertainty > this value, skip the trade
# Range: 0.0 (never trade) to 1.0 (always trade regardless of uncertainty)
DEFAULT_UNCERTAINTY_THRESHOLD = 0.7

# Maximum position size as percentage of portfolio
# Range: 0.01 (1%) to 1.0 (100%)
DEFAULT_MAX_POSITION_SIZE_PCT = 0.25

# Default leverage for perpetual futures
# Range: 1.0 (no leverage) to 50.0 (max on Hyperliquid)
DEFAULT_LEVERAGE = 1.0

# Optional stop-loss and take-profit percentages (None = disabled)
DEFAULT_STOP_LOSS_PCT = None  # e.g., 0.05 = 5% stop-loss
DEFAULT_TAKE_PROFIT_PCT = None  # e.g., 0.10 = 10% take-profit

# Uncertainty threshold presets for UI
UNCERTAINTY_PRESETS = {
    "conservative": {
        "value": 0.3,
        "display_name": "Conservative",
        "description": "Only trade when LLM is very confident (uncertainty < 30%)",
    },
    "moderate": {
        "value": 0.5,
        "display_name": "Moderate",
        "description": "Trade when LLM is reasonably confident (uncertainty < 50%)",
    },
    "balanced": {
        "value": 0.7,
        "display_name": "Balanced (Default)",
        "description": "Skip only very uncertain trades (uncertainty < 70%)",
    },
    "aggressive": {
        "value": 0.9,
        "display_name": "Aggressive",
        "description": "Trade most signals, skip only extremely uncertain (uncertainty < 90%)",
    },
    "all_trades": {
        "value": 1.0,
        "display_name": "Execute All",
        "description": "Execute all trades regardless of uncertainty",
    },
}


# =============================================================================
# VALIDATION HELPERS
# =============================================================================

def is_valid_model(model: str) -> bool:
    """Check if a model is supported."""
    return model in SUPPORTED_LLM_MODELS


def is_valid_coin(coin: str) -> bool:
    """Check if a coin is supported."""
    return coin.upper() in SUPPORTED_COINS


def is_valid_frequency(frequency: str) -> bool:
    """Check if a frequency is supported."""
    return frequency.lower() in SUPPORTED_FREQUENCIES


def validate_coins(coins: list) -> tuple[bool, list]:
    """Validate a list of coins.
    
    Returns:
        Tuple of (all_valid, invalid_coins)
    """
    invalid = [c for c in coins if not is_valid_coin(c)]
    return len(invalid) == 0, invalid


def get_coin_symbol(coin: str) -> str:
    """Get the trading symbol for a coin (e.g., 'BTC' -> 'BTC/USDT')."""
    coin_upper = coin.upper()
    if coin_upper in SUPPORTED_COINS:
        return SUPPORTED_COINS[coin_upper]["symbol"]
    return f"{coin_upper}/USDT"


def get_hyperliquid_asset_id(coin: str) -> int:
    """Get Hyperliquid asset ID for a coin."""
    coin_upper = coin.upper()
    if coin_upper in SUPPORTED_COINS:
        return SUPPORTED_COINS[coin_upper]["hyperliquid_asset_id"]
    return 0  # Default to BTC if unknown


def validate_uncertainty_threshold(threshold: float) -> bool:
    """Validate uncertainty threshold is in valid range."""
    return 0.0 <= threshold <= 1.0


def validate_leverage(leverage: float) -> bool:
    """Validate leverage is in valid range for Hyperliquid."""
    return 1.0 <= leverage <= 50.0


def validate_position_size_pct(pct: float) -> bool:
    """Validate position size percentage is in valid range."""
    return 0.01 <= pct <= 1.0

