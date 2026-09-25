"""
warehouse.py

Enhanced warehouse entity with realistic bottlenecks.

Features:
- Throughput variability (daily capacity fluctuations)
- Congestion effects (slowdown at high inventory)
- Delayed replenishment processing
- Backward compatible (uncertainty disabled by default)
"""

from typing import Dict, List, Optional
from collections import deque
import numpy as np


class Warehouse:
    """
    Represents a warehouse/distribution center.
    
    Attributes:
        warehouse_id: Unique identifier
        name: Human-readable name
        inventory: Current inventory per SKU
        config: Warehouse configuration
    """
    
    def __init__(
        self,
        warehouse_id: str,
        name: str,
        initial_inventory: Dict[str, float],
        config: dict,
        uncertainty_config: Optional[Dict] = None,
        seed: Optional[int] = None
    ):
        """
        Initialize warehouse.
        
        Args:
            warehouse_id: Unique identifier
            name: Warehouse name
            initial_inventory: Initial inventory per SKU
            config: Configuration with reorder_point, order_up_to, lead_time, etc.
            uncertainty_config: Optional uncertainty configuration
            seed: Random seed for reproducibility
        """
        self.warehouse_id = warehouse_id
        self.name = name
        self.config = config
        
        # Random number generator
        self.rng = np.random.RandomState(seed)
        
        # Inventory state
        self.inventory = initial_inventory.copy()
        self.max_inventory = sum(initial_inventory.values()) * 2  # Estimate max capacity
        
        # Store orders (backlog)
        self.store_orders = []  # List of {store_id, sku, quantity, order_day}
        self.backorders = {}    # SKU -> total backordered quantity
        
        # Supplier orders
        self.pending_supplier_orders = []  # Orders sent to supplier
        
        # In-transit shipments (from supplier)
        # Queue of (delivery_day, {sku: quantity})
        self.in_transit = deque()
        
        # Lead time to stores
        self.lead_time_to_stores = config.get('lead_time_to_stores', 2)
        
        # Daily tracking
        self.daily_fulfilled = {}
        self.daily_backordered = {}
        self.daily_holding_cost = 0.0
        self.daily_ordering_cost = 0.0
        
        # History
        self.history = {
            'inventory': [],
            'fulfilled': [],
            'backordered': [],
            'holding_cost': [],
            'ordering_cost': []
        }
        
        # Uncertainty features (disabled by default)
        self.uncertainty_config = uncertainty_config or {}
        self._init_uncertainty_features()
    
    def receive_store_order(self, store_id: str, order: Dict[str, float], day: int):
        """
        Receive order from a store.
        
        Args:
            store_id: Store placing the order
            order: Dict mapping SKU -> quantity
            day: Current simulation day
        """
        for sku, qty in order.items():
            if qty > 0:
                self.store_orders.append({
                    'store_id': store_id,
                    'sku': sku,
                    'quantity': qty,
                    'order_day': day
                })
    
    def _init_uncertainty_features(self):
        """Initialize uncertainty features from config."""
        # Warehouse bottlenecks
        self.enable_bottlenecks = self.uncertainty_config.get('enable_warehouse_bottlenecks', False)
        if self.enable_bottlenecks:
            self.bottleneck_config = self.uncertainty_config.get('bottleneck_config', {})
    
    def _calculate_throughput_capacity(self) -> float:
        """
        Calculate daily throughput capacity with variability.
        
        Returns:
            Throughput multiplier (0-1+)
        """
        if not self.enable_bottlenecks:
            return 1.0  # No bottleneck
        
        config = self.bottleneck_config
        
        # Base throughput with random variability
        variability = config.get('throughput_variability', 0.10)
        throughput = 1.0 + self.rng.normal(0, variability)
        
        # Apply congestion penalty if inventory is high
        current_inv = sum(self.inventory.values())
        utilization = current_inv / self.max_inventory if self.max_inventory > 0 else 0
        
        congestion_threshold = config.get('congestion_threshold', 0.90)
        if utilization > congestion_threshold:
            congestion_penalty = config.get('congestion_penalty', 0.20)
            # Linear penalty above threshold
            excess = (utilization - congestion_threshold) / (1.0 - congestion_threshold)
            throughput *= (1.0 - congestion_penalty * excess)
        
        # Ensure positive throughput
        return max(0.1, throughput)
    
    def fulfill_store_orders(self, sku_costs: Dict[str, dict]) -> Dict[str, Dict[str, float]]:
        """
        Process pending store orders, fulfill what we can.
        
        Args:
            sku_costs: SKU cost configuration
            
        Returns:
            Dict mapping store_id -> shipment dict (SKU -> quantity)
        """
        shipments = {}  # store_id -> {sku: quantity}
        self.daily_fulfilled = {}
        self.daily_backordered = {}
        
        # Calculate throughput capacity for today
        throughput_capacity = self._calculate_throughput_capacity()
        total_capacity = sum(self.inventory.values()) * throughput_capacity
        total_processed = 0.0
        
        # Process each order
        remaining_orders = []
        
        for order in self.store_orders:
            store_id = order['store_id']
            sku = order['sku']
            qty = order['quantity']
            
            available = self.inventory.get(sku, 0.0)
            
            # Check throughput capacity
            if self.enable_bottlenecks and total_processed >= total_capacity:
                # Hit capacity limit, backorder everything
                fulfilled = 0.0
            else:
                # Fulfill what we can (limited by inventory and capacity)
                max_fulfillable = min(qty, available)
                if self.enable_bottlenecks:
                    remaining_capacity = total_capacity - total_processed
                    fulfilled = min(max_fulfillable, remaining_capacity)
                else:
                    fulfilled = max_fulfillable
            
            total_processed += fulfilled
            backordered = qty - fulfilled
            
            if fulfilled > 0:
                # Ship to store
                if store_id not in shipments:
                    shipments[store_id] = {}
                shipments[store_id][sku] = shipments[store_id].get(sku, 0.0) + fulfilled
                
                # Reduce inventory
                self.inventory[sku] = available - fulfilled
                
                # Track fulfillment
                self.daily_fulfilled[sku] = self.daily_fulfilled.get(sku, 0.0) + fulfilled
            
            if backordered > 0:
                # Keep in backlog
                remaining_orders.append({
                    'store_id': store_id,
                    'sku': sku,
                    'quantity': backordered,
                    'order_day': order['order_day']
                })
                
                # Track backorder
                self.daily_backordered[sku] = self.daily_backordered.get(sku, 0.0) + backordered
                self.backorders[sku] = self.backorders.get(sku, 0.0) + backordered
        
        self.store_orders = remaining_orders
        
        return shipments
    
    def check_replenishment(self) -> Dict[str, float]:
        """
        Check if replenishment from supplier is needed.
        Uses (s, S) policy.
        
        Returns:
            Dict mapping SKU -> order quantity
        """
        orders = {}
        
        for sku in self.inventory.keys():
            current_inv = self.inventory[sku]
            in_transit_qty = sum(
                shipment.get(sku, 0.0) 
                for _, shipment in self.in_transit
            )
            
            # Inventory position = on_hand + in_transit - backorders
            inventory_position = (
                current_inv 
                + in_transit_qty 
                - self.backorders.get(sku, 0.0)
            )
            
            reorder_point = self.config.get('reorder_point', 0)
            order_up_to = self.config.get('order_up_to', 5000)
            
            # (s, S) policy
            if inventory_position <= reorder_point:
                order_qty = order_up_to - inventory_position
                orders[sku] = max(0, order_qty)
            else:
                orders[sku] = 0
        
        return orders
    
    def place_supplier_order(self, orders: Dict[str, float], day: int, supplier_lead_time: int):
        """
        Place order to supplier.
        
        Args:
            orders: Dict mapping SKU -> quantity
            day: Current day
            supplier_lead_time: Days until delivery
        """
        total_order_qty = sum(orders.values())
        
        if total_order_qty > 0:
            delivery_day = day + supplier_lead_time
            self.in_transit.append((delivery_day, orders.copy()))
            
            self.pending_supplier_orders.append({
                'order_day': day,
                'delivery_day': delivery_day,
                'order': orders.copy()
            })
    
    def receive_supplier_shipment(self, day: int) -> Dict[str, float]:
        """
        Receive shipments from supplier that arrive today.
        
        Args:
            day: Current simulation day
            
        Returns:
            Dict of received quantities per SKU
        """
        received = {}
        
        while self.in_transit and self.in_transit[0][0] <= day:
            delivery_day, shipment = self.in_transit.popleft()
            
            for sku, qty in shipment.items():
                self.inventory[sku] = self.inventory.get(sku, 0.0) + qty
                received[sku] = received.get(sku, 0.0) + qty
        
        return received
    
    def calculate_holding_cost(self, sku_costs: Dict[str, dict]) -> float:
        """
        Calculate holding cost for current inventory.
        
        Args:
            sku_costs: SKU cost configuration
            
        Returns:
            Total holding cost
        """
        self.daily_holding_cost = 0.0
        
        for sku, quantity in self.inventory.items():
            if sku in sku_costs:
                cost_per_unit = sku_costs[sku].get('holding_cost', 0.0)
                self.daily_holding_cost += quantity * cost_per_unit
        
        return self.daily_holding_cost
    
    def record_day(self):
        """Record daily metrics."""
        self.history['inventory'].append(sum(self.inventory.values()))
        self.history['fulfilled'].append(sum(self.daily_fulfilled.values()))
        self.history['backordered'].append(sum(self.daily_backordered.values()))
        self.history['holding_cost'].append(self.daily_holding_cost)
        self.history['ordering_cost'].append(self.daily_ordering_cost)
    
    def get_state(self) -> dict:
        """Get current warehouse state."""
        return {
            'warehouse_id': self.warehouse_id,
            'name': self.name,
            'inventory': self.inventory.copy(),
            'backorders': self.backorders.copy(),
            'pending_store_orders': len(self.store_orders),
            'in_transit_shipments': len(self.in_transit),
            'holding_cost': self.daily_holding_cost
        }
    
    def get_metrics(self) -> dict:
        """Get cumulative metrics."""
        import numpy as np
        
        return {
            'warehouse_id': self.warehouse_id,
            'total_fulfilled': sum(self.history['fulfilled']),
            'total_backordered': sum(self.history['backordered']),
            'total_holding_cost': sum(self.history['holding_cost']),
            'total_ordering_cost': sum(self.history['ordering_cost']),
            'avg_inventory': np.mean(self.history['inventory']) if self.history['inventory'] else 0.0,
            'current_backorders': sum(self.backorders.values())
        }
    
    def reset(self, initial_inventory: Dict[str, float]):
        """Reset warehouse to initial state."""
        self.inventory = initial_inventory.copy()
        self.store_orders = []
        self.backorders = {}
        self.pending_supplier_orders = []
        self.in_transit = deque()
        self.daily_fulfilled = {}
        self.daily_backordered = {}
        self.daily_holding_cost = 0.0
        self.daily_ordering_cost = 0.0
        
        self.history = {
            'inventory': [],
            'fulfilled': [],
            'backordered': [],
            'holding_cost': [],
            'ordering_cost': []
        }
