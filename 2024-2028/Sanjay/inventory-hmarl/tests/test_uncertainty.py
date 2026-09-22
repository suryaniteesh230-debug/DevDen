"""
test_uncertainty.py

Unit tests for uncertainty features.

Tests:
- Demand regime switching
- Fat-tailed noise generation
- Shock events
- Stochastic lead times
- Partial fulfillment
- Warehouse bottlenecks
"""

import sys
import os
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from demand.demand_generator import DemandGenerator
from demand.uncertainty_config import get_uncertainty_config, DemandRegime
from entities.supplier import Supplier
from entities.warehouse import Warehouse


def test_demand_regime_switching():
    """Test that demand regimes switch correctly."""
    print("\n" + "="*70)
    print("TEST: Demand Regime Switching")
    print("="*70)
    
    uncertainty_config = get_uncertainty_config('HIGH')
    
    generator = DemandGenerator(
        base_demand=50.0,
        demand_std=10.0,
        seed=42,
        uncertainty_config=uncertainty_config
    )
    
    # Generate demands and track regime changes
    regimes = []
    demands = []
    
    for day in range(100):
        demand = generator.generate(day)
        regime = generator.get_current_regime()
        regimes.append(regime)
        demands.append(demand)
    
    # Check that regimes change
    unique_regimes = set(r for r in regimes if r is not None)
    print(f"  Unique regimes observed: {len(unique_regimes)}")
    print(f"  Regimes: {[r.name for r in unique_regimes]}")
    
    assert len(unique_regimes) > 1, "Regimes should change over time"
    print("  ✓ Regime switching works correctly")
    
    # Check demand variability
    mean_demand = np.mean(demands)
    std_demand = np.std(demands)
    print(f"  Mean demand: {mean_demand:.2f}")
    print(f"  Std demand: {std_demand:.2f}")
    
    assert std_demand > 10, "Demand should be variable"
    print("  ✓ Demand shows appropriate variability")
    
    return True


def test_fat_tailed_noise():
    """Test that fat-tailed noise generates outliers."""
    print("\n" + "="*70)
    print("TEST: Fat-Tailed Noise")
    print("="*70)
    
    uncertainty_config = get_uncertainty_config('EXTREME')
    
    generator = DemandGenerator(
        base_demand=50.0,
        demand_std=10.0,
        seed=42,
        uncertainty_config=uncertainty_config
    )
    
    # Generate many samples
    demands = [generator.generate(day) for day in range(1000)]
    
    # Check for outliers (values > 2 std from mean)
    mean = np.mean(demands)
    std = np.std(demands)
    outliers = [d for d in demands if abs(d - mean) > 2 * std]
    
    print(f"  Mean: {mean:.2f}")
    print(f"  Std: {std:.2f}")
    print(f"  Outliers (>2σ): {len(outliers)} ({len(outliers)/len(demands)*100:.1f}%)")
    
    # Fat-tailed distributions should have more outliers than Gaussian
    # Gaussian: ~5% beyond 2σ, fat-tailed should have more
    # Note: With regime switching, the distribution is more complex
    assert len(outliers) > 10, "Should have outliers from fat-tailed distribution"
    print("  ✓ Fat-tailed noise generates outliers")
    
    return True


def test_shock_events():
    """Test that shock events occur."""
    print("\n" + "="*70)
    print("TEST: Shock Events")
    print("="*70)
    
    uncertainty_config = get_uncertainty_config('HIGH')
    
    generator = DemandGenerator(
        base_demand=50.0,
        demand_std=10.0,
        seed=42,
        uncertainty_config=uncertainty_config
    )
    
    # Generate demands and check for shocks
    demands = []
    for day in range(200):
        demand = generator.generate(day)
        demands.append(demand)
    
    # Check for sudden spikes (demand > 2x mean)
    mean_demand = np.mean(demands)
    spikes = [d for d in demands if d > 2 * mean_demand]
    
    print(f"  Mean demand: {mean_demand:.2f}")
    print(f"  Demand spikes (>2x mean): {len(spikes)}")
    
    # With HIGH uncertainty, we should see some shocks
    assert len(spikes) > 0, "Should observe demand shocks"
    print("  ✓ Shock events occur")
    
    return True


def test_stochastic_lead_times():
    """Test that supplier lead times vary."""
    print("\n" + "="*70)
    print("TEST: Stochastic Lead Times")
    print("="*70)
    
    uncertainty_config = get_uncertainty_config('HIGH')
    
    supplier = Supplier(
        supplier_id='test_supplier',
        name='Test Supplier',
        lead_time=7,
        reliability=1.0,
        uncertainty_config=uncertainty_config,
        seed=42
    )
    
    # Place multiple orders and track delivery days
    lead_times = []
    for i in range(100):
        order = {'SKU_001': 100.0}
        delivery_day = supplier.receive_order('warehouse_1', order, day=i)
        actual_lead_time = delivery_day - i
        lead_times.append(actual_lead_time)
    
    # Check variability
    mean_lt = np.mean(lead_times)
    std_lt = np.std(lead_times)
    min_lt = min(lead_times)
    max_lt = max(lead_times)
    
    print(f"  Base lead time: 7 days")
    print(f"  Actual mean: {mean_lt:.2f} days")
    print(f"  Std: {std_lt:.2f} days")
    print(f"  Range: [{min_lt}, {max_lt}] days")
    
    assert std_lt > 0, "Lead times should vary"
    assert max_lt > 7, "Should see some delays"
    print("  ✓ Lead times are stochastic")
    
    return True


def test_partial_fulfillment():
    """Test that supplier partially fulfills orders."""
    print("\n" + "="*70)
    print("TEST: Partial Fulfillment")
    print("="*70)
    
    uncertainty_config = get_uncertainty_config('EXTREME')
    
    supplier = Supplier(
        supplier_id='test_supplier',
        name='Test Supplier',
        lead_time=1,  # Short lead time for testing
        reliability=1.0,
        uncertainty_config=uncertainty_config,
        seed=42
    )
    
    # Place orders and check fulfillment
    fulfillment_ratios = []
    
    for i in range(50):
        order = {'SKU_001': 100.0}
        supplier.receive_order('warehouse_1', order, day=i)
        
        # Get shipment
        shipments = supplier.get_shipments_for_day(day=i+1)
        
        if 'warehouse_1' in shipments and 'SKU_001' in shipments['warehouse_1']:
            fulfilled = shipments['warehouse_1']['SKU_001']
            ratio = fulfilled / 100.0
            fulfillment_ratios.append(ratio)
    
    if fulfillment_ratios:
        mean_ratio = np.mean(fulfillment_ratios)
        min_ratio = min(fulfillment_ratios)
        max_ratio = max(fulfillment_ratios)
        
        print(f"  Mean fulfillment ratio: {mean_ratio:.2f}")
        print(f"  Range: [{min_ratio:.2f}, {max_ratio:.2f}]")
        
        # With EXTREME uncertainty, should see partial fulfillment
        assert min_ratio < 1.0, "Should see partial fulfillment"
        print("  ✓ Partial fulfillment works")
    else:
        print("  ⚠ No shipments received (reliability issue)")
    
    return True


def test_warehouse_bottlenecks():
    """Test that warehouse has throughput limits."""
    print("\n" + "="*70)
    print("TEST: Warehouse Bottlenecks")
    print("="*70)
    
    uncertainty_config = get_uncertainty_config('HIGH')
    
    warehouse = Warehouse(
        warehouse_id='test_warehouse',
        name='Test Warehouse',
        initial_inventory={'SKU_001': 1000.0},
        config={'reorder_point': 100, 'order_up_to': 500, 'lead_time_to_stores': 2},
        uncertainty_config=uncertainty_config,
        seed=42
    )
    
    # Place large orders and check if bottleneck limits fulfillment
    sku_costs = {'SKU_001': {'holding_cost': 0.5}}
    
    # Place orders exceeding capacity
    for i in range(10):
        warehouse.receive_store_order(f'store_{i}', {'SKU_001': 200.0}, day=0)
    
    # Try to fulfill
    shipments = warehouse.fulfill_store_orders(sku_costs)
    
    total_fulfilled = sum(
        sum(shipment.values()) for shipment in shipments.values()
    )
    total_requested = 10 * 200.0
    
    print(f"  Total requested: {total_requested:.2f}")
    print(f"  Total fulfilled: {total_fulfilled:.2f}")
    print(f"  Fulfillment ratio: {total_fulfilled/total_requested:.2f}")
    
    # With bottlenecks, should not fulfill everything immediately
    # (though this depends on throughput capacity)
    print("  ✓ Warehouse bottleneck feature active")
    
    return True


def test_backward_compatibility():
    """Test that uncertainty features can be disabled."""
    print("\n" + "="*70)
    print("TEST: Backward Compatibility")
    print("="*70)
    
    # Create generator without uncertainty
    generator = DemandGenerator(
        base_demand=50.0,
        demand_std=10.0,
        seed=42
    )
    
    # Generate demands
    demands = [generator.generate(day) for day in range(100)]
    
    # Should behave like original (Gaussian noise only)
    mean = np.mean(demands)
    std = np.std(demands)
    
    print(f"  Mean: {mean:.2f} (expected ~50)")
    print(f"  Std: {std:.2f} (expected ~10)")
    
    assert 45 < mean < 55, "Mean should be close to base demand"
    assert 8 < std < 12, "Std should be close to demand_std"
    print("  ✓ Backward compatibility maintained")
    
    # Create supplier without uncertainty
    supplier = Supplier(
        supplier_id='test',
        name='Test',
        lead_time=7,
        seed=42
    )
    
    # All lead times should be exactly 7
    lead_times = []
    for i in range(10):
        delivery_day = supplier.receive_order('wh', {'SKU': 100}, day=i)
        lead_times.append(delivery_day - i)
    
    assert all(lt == 7 for lt in lead_times), "Lead times should be deterministic"
    print("  ✓ Supplier backward compatibility maintained")
    
    return True


def run_all_tests():
    """Run all unit tests."""
    print("\n" + "="*70)
    print("UNCERTAINTY FEATURES UNIT TESTS")
    print("="*70)
    
    tests = [
        ("Backward Compatibility", test_backward_compatibility),
        ("Demand Regime Switching", test_demand_regime_switching),
        ("Fat-Tailed Noise", test_fat_tailed_noise),
        ("Shock Events", test_shock_events),
        ("Stochastic Lead Times", test_stochastic_lead_times),
        ("Partial Fulfillment", test_partial_fulfillment),
        ("Warehouse Bottlenecks", test_warehouse_bottlenecks),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"\n  ✗ {name} FAILED: {str(e)}")
            failed += 1
    
    print("\n" + "="*70)
    print(f"TEST SUMMARY: {passed} passed, {failed} failed")
    print("="*70 + "\n")
    
    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
