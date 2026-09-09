"""
uncertainty_config.py

Configuration for demand and supply-side uncertainty features.

Provides:
- Demand regime definitions (LOW, NORMAL, HIGH, SPIKE)
- Regime transition probabilities
- Fat-tailed noise parameters
- Store correlation settings
- Shock event configurations
- Uncertainty level presets (MILD, HIGH, EXTREME)
"""

import numpy as np
from enum import Enum
from typing import Dict, List, Optional


class DemandRegime(Enum):
    """Demand regime states."""
    LOW = "low"           # Below-average demand period
    NORMAL = "normal"     # Typical demand
    HIGH = "high"         # Above-average demand
    SPIKE = "spike"       # Extreme demand surge


class ShockType(Enum):
    """Types of demand shocks."""
    FESTIVAL = "festival"         # Seasonal event (positive)
    PROMOTION = "promotion"       # Marketing campaign (positive)
    PANIC_BUYING = "panic_buying" # Sudden surge (positive)
    DISRUPTION = "disruption"     # External event (can be positive or negative)


# =========================
# REGIME SWITCHING CONFIG
# =========================

REGIME_MULTIPLIERS = {
    DemandRegime.LOW: 0.7,      # 30% below normal
    DemandRegime.NORMAL: 1.0,   # Baseline
    DemandRegime.HIGH: 1.4,     # 40% above normal
    DemandRegime.SPIKE: 2.5     # 150% above normal
}

# Transition probability matrix
# Rows: current regime, Columns: next regime
# Order: LOW, NORMAL, HIGH, SPIKE
REGIME_TRANSITION_PROBS = {
    'MILD': np.array([
        [0.85, 0.12, 0.03, 0.00],  # LOW -> ...
        [0.05, 0.85, 0.09, 0.01],  # NORMAL -> ...
        [0.03, 0.12, 0.84, 0.01],  # HIGH -> ...
        [0.10, 0.60, 0.25, 0.05]   # SPIKE -> ...
    ]),
    'HIGH': np.array([
        [0.70, 0.20, 0.08, 0.02],  # LOW -> ...
        [0.10, 0.70, 0.15, 0.05],  # NORMAL -> ...
        [0.08, 0.20, 0.65, 0.07],  # HIGH -> ...
        [0.15, 0.40, 0.30, 0.15]   # SPIKE -> ...
    ]),
    'EXTREME': np.array([
        [0.50, 0.30, 0.15, 0.05],  # LOW -> ...
        [0.15, 0.50, 0.25, 0.10],  # NORMAL -> ...
        [0.15, 0.25, 0.45, 0.15],  # HIGH -> ...
        [0.20, 0.30, 0.30, 0.20]   # SPIKE -> ...
    ])
}

# Regime persistence (minimum days in regime)
REGIME_MIN_DURATION = {
    'MILD': 5,
    'HIGH': 3,
    'EXTREME': 2
}

# =========================
# FAT-TAILED NOISE CONFIG
# =========================

FAT_TAIL_CONFIG = {
    'MILD': {
        'distribution': 'lognormal',  # or 'gamma'
        'sigma': 0.3,                 # log-normal spread
        'outlier_prob': 0.02,         # 2% chance of extreme outlier
        'outlier_multiplier': 2.0     # Outliers are 2x normal noise
    },
    'HIGH': {
        'distribution': 'lognormal',
        'sigma': 0.5,
        'outlier_prob': 0.05,
        'outlier_multiplier': 3.0
    },
    'EXTREME': {
        'distribution': 'gamma',
        'shape': 2.0,                 # Gamma shape parameter
        'scale': 1.0,                 # Gamma scale parameter
        'outlier_prob': 0.10,
        'outlier_multiplier': 4.0
    }
}

# =========================
# STORE CORRELATION CONFIG
# =========================

# Correlation between stores (for correlated demand)
STORE_CORRELATION = {
    'MILD': 0.3,      # Weak correlation
    'HIGH': 0.5,      # Moderate correlation
    'EXTREME': 0.7    # Strong correlation
}

# Correlation decay over distance (if stores have locations)
CORRELATION_DECAY = 0.1  # per unit distance

# =========================
# SHOCK EVENT CONFIG
# =========================

SHOCK_CONFIG = {
    'MILD': {
        'festival': {
            'probability': 0.02,      # 2% chance per day
            'duration_range': (2, 4), # 2-4 days
            'multiplier_range': (1.5, 2.0)
        },
        'promotion': {
            'probability': 0.03,
            'duration_range': (3, 7),
            'multiplier_range': (1.3, 1.7)
        },
        'panic_buying': {
            'probability': 0.005,
            'duration_range': (1, 2),
            'multiplier_range': (2.0, 3.0)
        },
        'disruption': {
            'probability': 0.01,
            'duration_range': (1, 3),
            'multiplier_range': (0.5, 0.8)  # Negative shock
        }
    },
    'HIGH': {
        'festival': {
            'probability': 0.04,
            'duration_range': (2, 5),
            'multiplier_range': (1.8, 2.5)
        },
        'promotion': {
            'probability': 0.06,
            'duration_range': (3, 10),
            'multiplier_range': (1.5, 2.0)
        },
        'panic_buying': {
            'probability': 0.02,
            'duration_range': (1, 3),
            'multiplier_range': (2.5, 4.0)
        },
        'disruption': {
            'probability': 0.03,
            'duration_range': (2, 5),
            'multiplier_range': (0.3, 0.7)
        }
    },
    'EXTREME': {
        'festival': {
            'probability': 0.06,
            'duration_range': (3, 7),
            'multiplier_range': (2.0, 3.5)
        },
        'promotion': {
            'probability': 0.10,
            'duration_range': (5, 14),
            'multiplier_range': (1.8, 2.5)
        },
        'panic_buying': {
            'probability': 0.05,
            'duration_range': (1, 4),
            'multiplier_range': (3.0, 5.0)
        },
        'disruption': {
            'probability': 0.05,
            'duration_range': (3, 7),
            'multiplier_range': (0.2, 0.6)
        }
    }
}

# =========================
# SUPPLY-SIDE UNCERTAINTY
# =========================

LEAD_TIME_UNCERTAINTY = {
    'MILD': {
        'base_multiplier': 1.0,
        'std_dev': 0.5,               # days
        'extreme_delay_prob': 0.01,   # 1% chance
        'extreme_delay_range': (3, 7) # 3-7 extra days
    },
    'HIGH': {
        'base_multiplier': 1.0,
        'std_dev': 1.0,
        'extreme_delay_prob': 0.05,
        'extreme_delay_range': (5, 14)
    },
    'EXTREME': {
        'base_multiplier': 1.2,       # 20% longer base lead time
        'std_dev': 2.0,
        'extreme_delay_prob': 0.10,
        'extreme_delay_range': (7, 21)
    }
}

FULFILLMENT_UNCERTAINTY = {
    'MILD': {
        'mean_fulfillment': 0.98,     # 98% average fulfillment
        'std_dev': 0.05,
        'min_fulfillment': 0.80       # Never below 80%
    },
    'HIGH': {
        'mean_fulfillment': 0.95,
        'std_dev': 0.10,
        'min_fulfillment': 0.60
    },
    'EXTREME': {
        'mean_fulfillment': 0.90,
        'std_dev': 0.15,
        'min_fulfillment': 0.40
    }
}

WAREHOUSE_BOTTLENECK = {
    'MILD': {
        'throughput_variability': 0.10,  # ±10%
        'congestion_threshold': 0.90,    # 90% capacity
        'congestion_penalty': 0.20       # 20% slowdown
    },
    'HIGH': {
        'throughput_variability': 0.20,
        'congestion_threshold': 0.80,
        'congestion_penalty': 0.35
    },
    'EXTREME': {
        'throughput_variability': 0.35,
        'congestion_threshold': 0.70,
        'congestion_penalty': 0.50
    }
}

# =========================
# OBSERVATION NOISE CONFIG
# =========================

OBSERVATION_NOISE = {
    'MILD': {
        'demand_forecast_error': 0.10,    # 10% forecast error
        'inventory_measurement_error': 0.02,  # 2% measurement error
        'regime_forecast_error': 0.20     # 20% error during regime changes
    },
    'HIGH': {
        'demand_forecast_error': 0.20,
        'inventory_measurement_error': 0.05,
        'regime_forecast_error': 0.40
    },
    'EXTREME': {
        'demand_forecast_error': 0.35,
        'inventory_measurement_error': 0.10,
        'regime_forecast_error': 0.60
    }
}

# =========================
# RECONCILIATION NOISE
# =========================

RECONCILIATION_NOISE = {
    'MILD': {
        'metric_noise_std': 0.01,     # 1% noise in metrics
        'delay_steps': 0              # No delay
    },
    'HIGH': {
        'metric_noise_std': 0.03,
        'delay_steps': 1              # 1-step delay
    },
    'EXTREME': {
        'metric_noise_std': 0.05,
        'delay_steps': 2              # 2-step delay
    }
}

# =========================
# UNCERTAINTY PRESETS
# =========================

class UncertaintyLevel(Enum):
    """Predefined uncertainty levels."""
    NONE = "none"         # No uncertainty (original system)
    MILD = "mild"         # Slight uncertainty
    HIGH = "high"         # Significant uncertainty
    EXTREME = "extreme"   # Severe stress test


UNCERTAINTY_PRESETS = {
    'NONE': {
        'enable_regime_switching': False,
        'enable_fat_tails': False,
        'enable_correlation': False,
        'enable_shocks': False,
        'enable_lead_time_uncertainty': False,
        'enable_partial_fulfillment': False,
        'enable_warehouse_bottlenecks': False,
        'enable_observation_noise': False,
        'enable_reconciliation_noise': False
    },
    'MILD': {
        'enable_regime_switching': True,
        'regime_transition_probs': REGIME_TRANSITION_PROBS['MILD'],
        'regime_min_duration': REGIME_MIN_DURATION['MILD'],
        
        'enable_fat_tails': True,
        'fat_tail_config': FAT_TAIL_CONFIG['MILD'],
        
        'enable_correlation': True,
        'store_correlation': STORE_CORRELATION['MILD'],
        
        'enable_shocks': True,
        'shock_config': SHOCK_CONFIG['MILD'],
        
        'enable_lead_time_uncertainty': True,
        'lead_time_config': LEAD_TIME_UNCERTAINTY['MILD'],
        
        'enable_partial_fulfillment': True,
        'fulfillment_config': FULFILLMENT_UNCERTAINTY['MILD'],
        
        'enable_warehouse_bottlenecks': True,
        'bottleneck_config': WAREHOUSE_BOTTLENECK['MILD'],
        
        'enable_observation_noise': True,
        'observation_noise_config': OBSERVATION_NOISE['MILD'],
        
        'enable_reconciliation_noise': True,
        'reconciliation_noise_config': RECONCILIATION_NOISE['MILD']
    },
    'HIGH': {
        'enable_regime_switching': True,
        'regime_transition_probs': REGIME_TRANSITION_PROBS['HIGH'],
        'regime_min_duration': REGIME_MIN_DURATION['HIGH'],
        
        'enable_fat_tails': True,
        'fat_tail_config': FAT_TAIL_CONFIG['HIGH'],
        
        'enable_correlation': True,
        'store_correlation': STORE_CORRELATION['HIGH'],
        
        'enable_shocks': True,
        'shock_config': SHOCK_CONFIG['HIGH'],
        
        'enable_lead_time_uncertainty': True,
        'lead_time_config': LEAD_TIME_UNCERTAINTY['HIGH'],
        
        'enable_partial_fulfillment': True,
        'fulfillment_config': FULFILLMENT_UNCERTAINTY['HIGH'],
        
        'enable_warehouse_bottlenecks': True,
        'bottleneck_config': WAREHOUSE_BOTTLENECK['HIGH'],
        
        'enable_observation_noise': True,
        'observation_noise_config': OBSERVATION_NOISE['HIGH'],
        
        'enable_reconciliation_noise': True,
        'reconciliation_noise_config': RECONCILIATION_NOISE['HIGH']
    },
    'EXTREME': {
        'enable_regime_switching': True,
        'regime_transition_probs': REGIME_TRANSITION_PROBS['EXTREME'],
        'regime_min_duration': REGIME_MIN_DURATION['EXTREME'],
        
        'enable_fat_tails': True,
        'fat_tail_config': FAT_TAIL_CONFIG['EXTREME'],
        
        'enable_correlation': True,
        'store_correlation': STORE_CORRELATION['EXTREME'],
        
        'enable_shocks': True,
        'shock_config': SHOCK_CONFIG['EXTREME'],
        
        'enable_lead_time_uncertainty': True,
        'lead_time_config': LEAD_TIME_UNCERTAINTY['EXTREME'],
        
        'enable_partial_fulfillment': True,
        'fulfillment_config': FULFILLMENT_UNCERTAINTY['EXTREME'],
        
        'enable_warehouse_bottlenecks': True,
        'bottleneck_config': WAREHOUSE_BOTTLENECK['EXTREME'],
        
        'enable_observation_noise': True,
        'observation_noise_config': OBSERVATION_NOISE['EXTREME'],
        
        'enable_reconciliation_noise': True,
        'reconciliation_noise_config': RECONCILIATION_NOISE['EXTREME']
    }
}


def get_uncertainty_config(level: str = 'NONE') -> Dict:
    """
    Get uncertainty configuration for specified level.
    
    Args:
        level: Uncertainty level ('NONE', 'MILD', 'HIGH', 'EXTREME')
    
    Returns:
        Configuration dictionary
    """
    level = level.upper()
    if level not in UNCERTAINTY_PRESETS:
        raise ValueError(f"Unknown uncertainty level: {level}. Choose from {list(UNCERTAINTY_PRESETS.keys())}")
    
    return UNCERTAINTY_PRESETS[level].copy()
