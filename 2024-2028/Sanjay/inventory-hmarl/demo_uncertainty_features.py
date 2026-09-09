"""
demo_uncertainty_features.py

Simple demonstration of uncertainty features without requiring full dependencies.
Shows demand regime switching, fat-tailed noise, and stochastic lead times in action.
"""

import sys
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from demand.demand_generator import DemandGenerator
from demand.uncertainty_config import get_uncertainty_config
from entities.supplier import Supplier


def demo_demand_regimes():
    """Demonstrate demand regime switching."""
    print("\n" + "="*70)
    print("DEMO 1: Demand Regime Switching")
    print("="*70)
    
    # Create generator with HIGH uncertainty
    uncertainty_config = get_uncertainty_config('HIGH')
    generator = DemandGenerator(
        base_demand=50.0,
        demand_std=10.0,
        seed=42,
        uncertainty_config=uncertainty_config
    )
    
    # Generate 90 days of demand
    days = 90
    demands = []
    regimes = []
    
    for day in range(days):
        demand = generator.generate(day)
        regime = generator.get_current_regime()
        demands.append(demand)
        regimes.append(regime.name if regime else 'NORMAL')
    
    # Plot results
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8))
    
    # Plot demand
    ax1.plot(range(days), demands, linewidth=1.5, color='#2ca02c')
    ax1.axhline(y=50, color='r', linestyle='--', alpha=0.5, label='Base Demand')
    ax1.set_xlabel('Day', fontsize=12)
    ax1.set_ylabel('Demand', fontsize=12)
    ax1.set_title('Demand with Regime Switching (HIGH Uncertainty)', fontsize=14, fontweight='bold')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot regimes as colored background
    regime_colors = {'LOW': '#ff7f0e', 'NORMAL': '#2ca02c', 'HIGH': '#d62728', 'SPIKE': '#9467bd'}
    for i in range(days):
        ax2.axvspan(i, i+1, alpha=0.3, color=regime_colors.get(regimes[i], '#gray'))
    
    ax2.set_xlabel('Day', fontsize=12)
    ax2.set_ylabel('Regime', fontsize=12)
    ax2.set_title('Demand Regimes Over Time', fontsize=14, fontweight='bold')
    ax2.set_yticks([0, 1, 2, 3])
    ax2.set_yticklabels(['LOW', 'NORMAL', 'HIGH', 'SPIKE'])
    ax2.grid(True, alpha=0.3, axis='x')
    
    plt.tight_layout()
    output_file = 'demo_regime_switching.png'
    plt.savefig(output_file, dpi=300)
    plt.close()
    
    print(f"\n✓ Generated demand for {days} days")
    print(f"  Mean demand: {np.mean(demands):.2f}")
    print(f"  Std demand: {np.std(demands):.2f}")
    print(f"  Min demand: {np.min(demands):.2f}")
    print(f"  Max demand: {np.max(demands):.2f}")
    print(f"\n  Regime distribution:")
    for regime in ['LOW', 'NORMAL', 'HIGH', 'SPIKE']:
        count = regimes.count(regime)
        print(f"    {regime}: {count} days ({count/days*100:.1f}%)")
    print(f"\n✓ Saved plot to: {output_file}")


def demo_uncertainty_comparison():
    """Compare demand across uncertainty levels."""
    print("\n" + "="*70)
    print("DEMO 2: Uncertainty Level Comparison")
    print("="*70)
    
    levels = ['NONE', 'MILD', 'HIGH', 'EXTREME']
    days = 90
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    axes = axes.flatten()
    
    for idx, level in enumerate(levels):
        uncertainty_config = get_uncertainty_config(level)
        generator = DemandGenerator(
            base_demand=50.0,
            demand_std=10.0,
            seed=42,
            uncertainty_config=uncertainty_config
        )
        
        demands = [generator.generate(day) for day in range(days)]
        
        ax = axes[idx]
        ax.plot(range(days), demands, linewidth=1.5, alpha=0.8)
        ax.axhline(y=50, color='r', linestyle='--', alpha=0.5, label='Base Demand')
        ax.set_xlabel('Day', fontsize=11)
        ax.set_ylabel('Demand', fontsize=11)
        ax.set_title(f'{level} Uncertainty', fontsize=13, fontweight='bold')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Add stats
        mean_d = np.mean(demands)
        std_d = np.std(demands)
        ax.text(0.02, 0.98, f'μ={mean_d:.1f}, σ={std_d:.1f}',
                transform=ax.transAxes, fontsize=10,
                verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.suptitle('Demand Patterns Across Uncertainty Levels', fontsize=16, fontweight='bold')
    plt.tight_layout()
    
    output_file = 'demo_uncertainty_comparison.png'
    plt.savefig(output_file, dpi=300)
    plt.close()
    
    print(f"\n✓ Compared {len(levels)} uncertainty levels")
    print(f"✓ Saved plot to: {output_file}")


def demo_stochastic_lead_times():
    """Demonstrate stochastic lead times."""
    print("\n" + "="*70)
    print("DEMO 3: Stochastic Lead Times")
    print("="*70)
    
    levels = ['NONE', 'MILD', 'HIGH', 'EXTREME']
    num_orders = 100
    
    fig, ax = plt.subplots(figsize=(14, 6))
    
    for level in levels:
        uncertainty_config = get_uncertainty_config(level)
        supplier = Supplier(
            supplier_id='demo_supplier',
            name='Demo Supplier',
            lead_time=7,
            reliability=1.0,
            uncertainty_config=uncertainty_config,
            seed=42
        )
        
        lead_times = []
        for i in range(num_orders):
            order = {'SKU_001': 100.0}
            delivery_day = supplier.receive_order('warehouse_1', order, day=i)
            actual_lead_time = delivery_day - i
            lead_times.append(actual_lead_time)
        
        # Plot histogram
        ax.hist(lead_times, bins=20, alpha=0.5, label=level, edgecolor='black')
        
        mean_lt = np.mean(lead_times)
        print(f"\n  {level}:")
        print(f"    Mean lead time: {mean_lt:.2f} days")
        print(f"    Std: {np.std(lead_times):.2f} days")
        print(f"    Range: [{min(lead_times)}, {max(lead_times)}] days")
    
    ax.axvline(x=7, color='r', linestyle='--', linewidth=2, label='Base Lead Time')
    ax.set_xlabel('Lead Time (days)', fontsize=12)
    ax.set_ylabel('Frequency', fontsize=12)
    ax.set_title('Lead Time Distribution Across Uncertainty Levels', fontsize=14, fontweight='bold')
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    output_file = 'demo_lead_times.png'
    plt.savefig(output_file, dpi=300)
    plt.close()
    
    print(f"\n✓ Saved plot to: {output_file}")


def main():
    """Run all demonstrations."""
    print("\n" + "="*70)
    print("HMARL UNCERTAINTY FEATURES DEMONSTRATION")
    print("="*70)
    print("\nThis demo shows the uncertainty features in action:")
    print("  1. Demand regime switching")
    print("  2. Uncertainty level comparison")
    print("  3. Stochastic lead times")
    print("\nAll plots will be saved as PNG files in the current directory.")
    
    try:
        demo_demand_regimes()
        demo_uncertainty_comparison()
        demo_stochastic_lead_times()
        
        print("\n" + "="*70)
        print("✓ DEMONSTRATION COMPLETE!")
        print("="*70)
        print("\nGenerated files:")
        print("  - demo_regime_switching.png")
        print("  - demo_uncertainty_comparison.png")
        print("  - demo_lead_times.png")
        print("\nThese visualizations demonstrate that the uncertainty features")
        print("are working correctly and producing realistic variability.")
        print("="*70 + "\n")
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
