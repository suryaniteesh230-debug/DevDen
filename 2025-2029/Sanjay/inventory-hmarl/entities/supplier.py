"""
supplier.py

Enhanced supplier entity with realistic uncertainty.

Features:
- Stochastic lead times (base + random delay)
- Partial fulfillment (capacity constraints)
- Rare extreme delays (supply disruptions)
- Backward compatible (uncertainty disabled by default)
"""

from typing import Dict, Optional
from collections import deque
import numpy as np


class Supplier:
    """
    Represents an upstream supplier with optional uncertainty.
    
    Backward compatible: All uncertainty features disabled by default.
    
    Attributes:
        supplier_id: Unique identifier
        name: Human-readable name
        lead_time: Base delivery lead time in days
        reliability: Probability of successful fulfillment (0-1)
        uncertainty_config: Optional uncertainty configuration
    """
    
    def __init__(
        self,
        supplier_id: str,
        name: str,
        lead_time: int = 7,
        reliability: float = 1.0,
        uncertainty_config: Optional[Dict] = None,
        seed: Optional[int] = None
    ):
        """
        Initialize supplier.
        
        Args:
            supplier_id: Unique identifier
            name: Supplier name
            lead_time: Base delivery lead time in days
            reliability: Order fulfillment probability (0-1)
            uncertainty_config: Optional uncertainty configuration
            seed: Random seed for reproducibility
        """
        self.supplier_id = supplier_id
        self.name = name
        self.lead_time = lead_time
        self.reliability = reliability
        
        # Random number generator
        self.rng = np.random.RandomState(seed)
        
        # Pending orders: queue of (delivery_day, warehouse_id, order_dict)
        self.pending_orders = deque()
        
        # History
        self.total_orders_received = 0
        self.total_orders_fulfilled = 0
        self.total_units_supplied = 0
        self.total_units_requested = 0
        
        # Uncertainty features (disabled by default)
        self.uncertainty_config = uncertainty_config or {}
        self._init_uncertainty_features()
    
    def _init_uncertainty_features(self):
        """Initialize uncertainty features from config."""
        # Lead time uncertainty
        self.enable_lead_time_uncertainty = self.uncertainty_config.get('enable_lead_time_uncertainty', False)
        if self.enable_lead_time_uncertainty:
            self.lead_time_config = self.uncertainty_config.get('lead_time_config', {})
        
        # Partial fulfillment
        self.enable_partial_fulfillment = self.uncertainty_config.get('enable_partial_fulfillment', False)
        if self.enable_partial_fulfillment:
            self.fulfillment_config = self.uncertainty_config.get('fulfillment_config', {})
    
    def _calculate_stochastic_lead_time(self, base_lead_time: int) -> int:
        """
        Calculate stochastic lead time with occasional extreme delays.
        
        Args:
            base_lead_time: Base lead time in days
        
        Returns:
            Actual lead time (days)
        """
        if not self.enable_lead_time_uncertainty:
            return base_lead_time
        
        config = self.lead_time_config
        
        # Apply base multiplier
        base_multiplier = config.get('base_multiplier', 1.0)
        lead_time = base_lead_time * base_multiplier
        
        # Add normal variation
        std_dev = config.get('std_dev', 0.5)
        variation = self.rng.normal(0, std_dev)
        lead_time += variation
        
        # Occasional extreme delays
        extreme_prob = config.get('extreme_delay_prob', 0.01)
        if self.rng.random() < extreme_prob:
            extreme_range = config.get('extreme_delay_range', (3, 7))
            extreme_delay = self.rng.randint(extreme_range[0], extreme_range[1] + 1)
            lead_time += extreme_delay
        
        # Ensure minimum lead time of 1 day
        return max(1, int(np.round(lead_time)))
    
    def _calculate_fulfillment_ratio(self) -> float:
        """
        Calculate partial fulfillment ratio.
        
        Returns:
            Fulfillment ratio (0-1)
        """
        if not self.enable_partial_fulfillment:
            return 1.0  # Full fulfillment
        
        config = self.fulfillment_config
        
        # Sample from normal distribution
        mean = config.get('mean_fulfillment', 0.98)
        std_dev = config.get('std_dev', 0.05)
        min_fulfillment = config.get('min_fulfillment', 0.80)
        
        ratio = self.rng.normal(mean, std_dev)
        
        # Clip to valid range
        ratio = max(min_fulfillment, min(1.0, ratio))
        
        return ratio
    
    def receive_order(
        self, 
        warehouse_id: str, 
        order: Dict[str, float], 
        day: int
    ) -> int:
        """
        Receive order from warehouse.
        
        Args:
            warehouse_id: Warehouse placing the order
            order: Dict mapping SKU -> quantity
            day: Current simulation day
            
        Returns:
            Expected delivery day
        """
        self.total_orders_received += 1
        
        # Track total units requested
        for qty in order.values():
            self.total_units_requested += qty
        
        # Calculate stochastic lead time
        actual_lead_time = self._calculate_stochastic_lead_time(self.lead_time)
        delivery_day = day + actual_lead_time
        
        # Calculate fulfillment ratio
        fulfillment_ratio = self._calculate_fulfillment_ratio()
        
        # For simplicity, always accept the order
        self.pending_orders.append({
            'delivery_day': delivery_day,
            'warehouse_id': warehouse_id,
            'order': order.copy(),
            'order_day': day,
            'fulfillment_ratio': fulfillment_ratio
        })
        
        return delivery_day
    
    def get_shipments_for_day(self, day: int) -> Dict[str, Dict[str, float]]:
        """
        Get all shipments scheduled for delivery on this day.
        
        Args:
            day: Current simulation day
            
        Returns:
            Dict mapping warehouse_id -> shipment (SKU -> quantity)
        """
        shipments = {}
        
        # Process orders due for delivery
        remaining_orders = deque()
        
        for order_info in self.pending_orders:
            if order_info['delivery_day'] <= day:
                # Deliver this order
                warehouse_id = order_info['warehouse_id']
                order = order_info['order']
                fulfillment_ratio = order_info.get('fulfillment_ratio', 1.0)
                
                # Apply reliability (simplified: all-or-nothing)
                if self.rng.random() <= self.reliability:
                    # Fulfill order (possibly partial)
                    if warehouse_id not in shipments:
                        shipments[warehouse_id] = {}
                    
                    for sku, qty in order.items():
                        # Apply partial fulfillment
                        fulfilled_qty = qty * fulfillment_ratio
                        
                        shipments[warehouse_id][sku] = shipments[warehouse_id].get(sku, 0.0) + fulfilled_qty
                        self.total_units_supplied += fulfilled_qty
                    
                    self.total_orders_fulfilled += 1
                # else: order fails (dropped)
            else:
                # Keep for future delivery
                remaining_orders.append(order_info)
        
        self.pending_orders = remaining_orders
        
        return shipments
    
    def get_state(self) -> dict:
        """Get current supplier state."""
        return {
            'supplier_id': self.supplier_id,
            'name': self.name,
            'lead_time': self.lead_time,
            'reliability': self.reliability,
            'pending_orders': list(self.pending_orders),
            'total_orders_received': self.total_orders_received,
            'total_orders_fulfilled': self.total_orders_fulfilled
        }
    
    def get_metrics(self) -> dict:
        """Get cumulative metrics."""
        fulfillment_rate = (
            self.total_orders_fulfilled / self.total_orders_received
            if self.total_orders_received > 0
            else 0.0
        )
        
        fill_rate = (
            self.total_units_supplied / self.total_units_requested
            if self.total_units_requested > 0
            else 0.0
        )
        
        return {
            'supplier_id': self.supplier_id,
            'total_orders_received': self.total_orders_received,
            'total_orders_fulfilled': self.total_orders_fulfilled,
            'total_units_supplied': self.total_units_supplied,
            'total_units_requested': self.total_units_requested,
            'fulfillment_rate': fulfillment_rate,
            'fill_rate': fill_rate
        }
    
    def reset(self):
        """Reset supplier to initial state."""
        self.pending_orders = deque()
        self.total_orders_received = 0
        self.total_orders_fulfilled = 0
        self.total_units_supplied = 0
        self.total_units_requested = 0
