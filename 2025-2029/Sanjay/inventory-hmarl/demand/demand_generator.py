"""
demand_generator.py

Enhanced stochastic demand generation with realistic uncertainty.

Features:
- Base demand with seasonal patterns (original)
- Regime switching (LOW, NORMAL, HIGH, SPIKE)
- Fat-tailed noise (log-normal/gamma distributions)
- Demand shock events (festivals, promotions, disruptions)
- Backward compatible (all new features disabled by default)
"""

import numpy as np
from typing import Optional, Dict, List, Tuple
from enum import Enum


class DemandRegime(Enum):
    """Demand regime states."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    SPIKE = 3


class DemandGenerator:
    """
    Generates stochastic demand with optional uncertainty features.
    
    Backward compatible: All uncertainty features disabled by default.
    
    Formula (basic):
        demand(day) = base_demand 
                      * (1 + seasonality_amplitude * sin(2π * day / period))
                      * demand_multiplier
                      + noise(std_dev)
    
    Formula (with uncertainty):
        demand(day) = base_demand
                      * regime_multiplier(current_regime)
                      * seasonal_factor(day)
                      * demand_multiplier
                      * shock_multiplier(day)
                      + fat_tailed_noise()
    """
    
    def __init__(
        self,
        base_demand: float = 50.0,
        demand_std: float = 10.0,
        seasonality_amplitude: float = 0.0,
        seasonality_period: int = 30,
        demand_multiplier: float = 1.0,
        seed: Optional[int] = None,
        uncertainty_config: Optional[Dict] = None
    ):
        """
        Initialize demand generator.
        
        Args:
            base_demand: Mean daily demand
            demand_std: Standard deviation of demand
            seasonality_amplitude: Seasonal variation amplitude (0 = no seasonality)
            seasonality_period: Seasonal cycle length in days
            demand_multiplier: Scaling factor for this demand stream
            seed: Random seed for reproducibility
            uncertainty_config: Optional uncertainty configuration dict
        """
        self.base_demand = base_demand
        self.demand_std = demand_std
        self.seasonality_amplitude = seasonality_amplitude
        self.seasonality_period = seasonality_period
        self.demand_multiplier = demand_multiplier
        
        # Random number generator
        self.rng = np.random.RandomState(seed)
        
        # Spike parameters (controlled by scenarios - backward compatible)
        self.spike_days = set()
        self.spike_multiplier = 1.0
        
        # Uncertainty features (disabled by default)
        self.uncertainty_config = uncertainty_config or {}
        self._init_uncertainty_features()
    
    def _init_uncertainty_features(self):
        """Initialize uncertainty features from config."""
        # Regime switching
        self.enable_regime_switching = self.uncertainty_config.get('enable_regime_switching', False)
        if self.enable_regime_switching:
            from demand.uncertainty_config import DemandRegime as ConfigRegime, REGIME_MULTIPLIERS
            self.current_regime = DemandRegime.NORMAL
            self.regime_day_count = 0
            self.regime_transition_probs = self.uncertainty_config.get('regime_transition_probs')
            self.regime_min_duration = self.uncertainty_config.get('regime_min_duration', 3)
            self.regime_multipliers = {
                DemandRegime.LOW: 0.7,
                DemandRegime.NORMAL: 1.0,
                DemandRegime.HIGH: 1.4,
                DemandRegime.SPIKE: 2.5
            }
        
        # Fat-tailed noise
        self.enable_fat_tails = self.uncertainty_config.get('enable_fat_tails', False)
        if self.enable_fat_tails:
            self.fat_tail_config = self.uncertainty_config.get('fat_tail_config', {})
        
        # Shock events
        self.enable_shocks = self.uncertainty_config.get('enable_shocks', False)
        if self.enable_shocks:
            self.shock_config = self.uncertainty_config.get('shock_config', {})
            self.active_shocks = []  # List of (end_day, multiplier) tuples
    
    def reset(self, seed: Optional[int] = None):
        """
        Reset the random number generator.
        
        Args:
            seed: New random seed (optional)
        """
        if seed is not None:
            self.rng = np.random.RandomState(seed)
        self.spike_days = set()
        
        # Reset uncertainty state
        if self.enable_regime_switching:
            self.current_regime = DemandRegime.NORMAL
            self.regime_day_count = 0
        if self.enable_shocks:
            self.active_shocks = []
    
    def set_spike(self, days: list, multiplier: float = 2.0):
        """
        Configure demand spike for specific days (backward compatible).
        
        Args:
            days: List of days to spike demand
            multiplier: Demand multiplier for spike days
        """
        self.spike_days = set(days)
        self.spike_multiplier = multiplier
    
    def _update_regime(self, day: int):
        """Update demand regime using transition probabilities."""
        if not self.enable_regime_switching:
            return
        
        self.regime_day_count += 1
        
        # Only allow transition if minimum duration met
        if self.regime_day_count < self.regime_min_duration:
            return
        
        # Get transition probabilities for current regime
        current_idx = self.current_regime.value
        transition_probs = self.regime_transition_probs[current_idx]
        
        # Sample next regime
        next_regime_idx = self.rng.choice(4, p=transition_probs)
        next_regime = DemandRegime(next_regime_idx)
        
        # Update regime if changed
        if next_regime != self.current_regime:
            self.current_regime = next_regime
            self.regime_day_count = 0
    
    def _get_regime_multiplier(self) -> float:
        """Get demand multiplier for current regime."""
        if not self.enable_regime_switching:
            return 1.0
        return self.regime_multipliers[self.current_regime]
    
    def _generate_fat_tailed_noise(self) -> float:
        """Generate noise from fat-tailed distribution."""
        if not self.enable_fat_tails:
            # Standard Gaussian noise (backward compatible)
            return self.rng.normal(0, self.demand_std)
        
        config = self.fat_tail_config
        distribution = config.get('distribution', 'lognormal')
        
        # Base noise
        if distribution == 'lognormal':
            sigma = config.get('sigma', 0.3)
            # Log-normal with mean 0
            noise = self.rng.lognormal(0, sigma) - np.exp(sigma**2 / 2)
            noise *= self.demand_std
        elif distribution == 'gamma':
            shape = config.get('shape', 2.0)
            scale = config.get('scale', 1.0)
            noise = self.rng.gamma(shape, scale) - shape * scale
            noise *= self.demand_std / (shape * scale)
        else:
            noise = self.rng.normal(0, self.demand_std)
        
        # Add occasional extreme outliers
        outlier_prob = config.get('outlier_prob', 0.02)
        if self.rng.random() < outlier_prob:
            outlier_multiplier = config.get('outlier_multiplier', 2.0)
            noise *= outlier_multiplier
        
        return noise
    
    def _update_shocks(self, day: int):
        """Update active shock events."""
        if not self.enable_shocks:
            return
        
        # Remove expired shocks
        self.active_shocks = [(end_day, mult) for end_day, mult in self.active_shocks if day < end_day]
        
        # Probabilistically trigger new shocks
        for shock_type, shock_params in self.shock_config.items():
            prob = shock_params.get('probability', 0.0)
            if self.rng.random() < prob:
                # Trigger shock
                duration_range = shock_params.get('duration_range', (1, 3))
                duration = self.rng.randint(duration_range[0], duration_range[1] + 1)
                
                multiplier_range = shock_params.get('multiplier_range', (1.5, 2.0))
                multiplier = self.rng.uniform(multiplier_range[0], multiplier_range[1])
                
                end_day = day + duration
                self.active_shocks.append((end_day, multiplier))
    
    def _get_shock_multiplier(self) -> float:
        """Get combined multiplier from all active shocks."""
        if not self.enable_shocks or not self.active_shocks:
            return 1.0
        
        # Multiply all active shock multipliers
        total_multiplier = 1.0
        for _, multiplier in self.active_shocks:
            total_multiplier *= multiplier
        
        return total_multiplier
    
    def _seasonal_factor(self, day: int) -> float:
        """
        Calculate seasonal adjustment factor.
        
        Args:
            day: Current simulation day
            
        Returns:
            Seasonal multiplier (1.0 = no adjustment)
        """
        if self.seasonality_amplitude == 0:
            return 1.0
        
        # Sinusoidal pattern
        phase = 2 * np.pi * day / self.seasonality_period
        seasonal_component = self.seasonality_amplitude * np.sin(phase)
        
        return 1.0 + seasonal_component
    
    def generate(self, day: int) -> float:
        """
        Generate demand for a specific day.
        
        Args:
            day: Current simulation day (0-indexed)
            
        Returns:
            Demand value (non-negative)
        """
        # Update regime (if enabled)
        self._update_regime(day)
        
        # Update shocks (if enabled)
        self._update_shocks(day)
        
        # Start with base demand scaled by multiplier
        mean_demand = self.base_demand * self.demand_multiplier
        
        # Apply regime multiplier
        regime_mult = self._get_regime_multiplier()
        mean_demand *= regime_mult
        
        # Apply seasonal adjustment
        seasonal_factor = self._seasonal_factor(day)
        mean_demand *= seasonal_factor
        
        # Apply shock multiplier
        shock_mult = self._get_shock_multiplier()
        mean_demand *= shock_mult
        
        # Add stochastic noise (fat-tailed if enabled)
        noise = self._generate_fat_tailed_noise()
        demand = mean_demand + noise
        
        # Apply manual spike if configured for this day (backward compatible)
        if day in self.spike_days:
            demand *= self.spike_multiplier
        
        # Ensure non-negative demand
        demand = max(0, demand)
        
        return demand
    
    def generate_series(self, num_days: int) -> np.ndarray:
        """
        Generate demand for multiple days at once.
        
        Args:
            num_days: Number of days to generate
            
        Returns:
            Array of demand values
        """
        return np.array([self.generate(day) for day in range(num_days)])
    
    def get_expected_demand(self, day: int) -> float:
        """
        Get expected demand (without noise) for a given day.
        Useful for forecasting.
        
        Args:
            day: Simulation day
            
        Returns:
            Expected demand value
        """
        mean_demand = self.base_demand * self.demand_multiplier
        seasonal_factor = self._seasonal_factor(day)
        return mean_demand * seasonal_factor
    
    def get_current_regime(self) -> Optional[DemandRegime]:
        """Get current demand regime (if regime switching enabled)."""
        if self.enable_regime_switching:
            return self.current_regime
        return None


class CorrelatedDemandGenerator:
    """
    Generates correlated demand across multiple stores.
    
    Uses Cholesky decomposition to create correlated random variables.
    """
    
    def __init__(
        self,
        num_stores: int,
        base_generators: List[DemandGenerator],
        correlation: float = 0.0,
        seed: Optional[int] = None
    ):
        """
        Initialize correlated demand generator.
        
        Args:
            num_stores: Number of stores
            base_generators: List of DemandGenerator instances (one per store)
            correlation: Correlation coefficient between stores (0-1)
            seed: Random seed
        """
        self.num_stores = num_stores
        self.generators = base_generators
        self.correlation = correlation
        self.rng = np.random.RandomState(seed)
        
        # Create correlation matrix
        self.corr_matrix = self._create_correlation_matrix()
        
        # Cholesky decomposition for correlated sampling
        self.cholesky = np.linalg.cholesky(self.corr_matrix)
    
    def _create_correlation_matrix(self) -> np.ndarray:
        """Create correlation matrix."""
        corr = np.eye(self.num_stores)
        for i in range(self.num_stores):
            for j in range(i + 1, self.num_stores):
                corr[i, j] = self.correlation
                corr[j, i] = self.correlation
        return corr
    
    def generate(self, day: int) -> List[float]:
        """
        Generate correlated demand for all stores.
        
        Args:
            day: Simulation day
        
        Returns:
            List of demand values (one per store)
        """
        # Generate independent standard normal variables
        independent = self.rng.standard_normal(self.num_stores)
        
        # Transform to correlated variables
        correlated = self.cholesky @ independent
        
        # Generate base demands and add correlated noise
        demands = []
        for i, generator in enumerate(self.generators):
            # Get base demand (without noise)
            base = generator.get_expected_demand(day)
            
            # Add correlated noise
            noise_std = generator.demand_std
            demand = base + correlated[i] * noise_std
            
            # Apply regime and shock multipliers
            if generator.enable_regime_switching:
                generator._update_regime(day)
                demand *= generator._get_regime_multiplier()
            
            if generator.enable_shocks:
                generator._update_shocks(day)
                demand *= generator._get_shock_multiplier()
            
            # Ensure non-negative
            demand = max(0, demand)
            demands.append(demand)
        
        return demands


class MultiSKUDemandGenerator:
    """
    Manages demand generation for multiple SKUs.
    
    Each SKU has its own demand generator with potentially
    different parameters.
    """
    
    def __init__(
        self,
        sku_configs: dict,
        demand_multiplier: float = 1.0,
        seed: Optional[int] = None,
        uncertainty_config: Optional[Dict] = None
    ):
        """
        Initialize multi-SKU demand generator.
        
        Args:
            sku_configs: Dict mapping SKU_ID -> config dict with demand parameters
            demand_multiplier: Store-level demand multiplier
            seed: Random seed
            uncertainty_config: Optional uncertainty configuration
        """
        self.generators = {}
        
        for sku_id, config in sku_configs.items():
            # Create individual generator for each SKU
            sku_seed = seed + hash(sku_id) % 10000 if seed is not None else None
            
            self.generators[sku_id] = DemandGenerator(
                base_demand=config.get("base_demand", 50.0),
                demand_std=config.get("demand_std", 10.0),
                seasonality_amplitude=config.get("seasonality_amplitude", 0.0),
                seasonality_period=config.get("seasonality_period", 30),
                demand_multiplier=demand_multiplier,
                seed=sku_seed,
                uncertainty_config=uncertainty_config
            )
    
    def generate(self, day: int) -> dict:
        """
        Generate demand for all SKUs for a given day.
        
        Args:
            day: Simulation day
            
        Returns:
            Dict mapping SKU_ID -> demand value
        """
        return {
            sku_id: generator.generate(day)
            for sku_id, generator in self.generators.items()
        }
    
    def set_spike(self, sku_id: str, days: list, multiplier: float = 2.0):
        """
        Set demand spike for a specific SKU.
        
        Args:
            sku_id: SKU identifier
            days: List of spike days
            multiplier: Spike multiplier
        """
        if sku_id in self.generators:
            self.generators[sku_id].set_spike(days, multiplier)
    
    def reset(self, seed: Optional[int] = None):
        """Reset all generators."""
        for sku_id, generator in self.generators.items():
            sku_seed = seed + hash(sku_id) % 10000 if seed is not None else None
            generator.reset(sku_seed)
