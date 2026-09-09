"""
Quick Start: Stress Testing HMARL System
=========================================

This guide shows how to run stress tests on the trained HMARL system.

## Prerequisites

1. Trained PPO model exists at: `checkpoints/ppo_store_agents_gym.pt`
2. Virtual environment activated
3. All dependencies installed

## Running Stress Tests

### 1. MILD Uncertainty (Recommended First Test)
```bash
python evaluation/stress_test_evaluator.py --level mild
```

Expected results:
- Service level: 85-95%
- Slight performance degradation from perfect conditions
- PPO should outperform baseline by 5-15%

### 2. HIGH Uncertainty
```bash
python evaluation/stress_test_evaluator.py --level high
```

Expected results:
- Service level: 70-85%
- Noticeable performance degradation
- PPO should show better resilience than baseline

### 3. EXTREME Uncertainty (Stress Test)
```bash
python evaluation/stress_test_evaluator.py --level extreme
```

Expected results:
- Service level: 60-75%
- Significant performance degradation
- PPO should demonstrate superior robustness

## Output Files

Each stress test creates a directory: `evaluation/stress_results/{level}/`

Contents:
- `stress_test_report.txt` - Detailed text report
- `episode_metrics.csv` - Raw metrics data
- `service_level_comparison.png` - Service level plot
- `stockouts_comparison.png` - Stockouts plot
- `rewards_comparison.png` - Rewards plot
- `summary_comparison.png` - Summary bar charts

## Custom Options

```bash
# Custom number of episodes
python evaluation/stress_test_evaluator.py --level mild --episodes 100

# Custom episode length
python evaluation/stress_test_evaluator.py --level high --length 60

# Custom model path
python evaluation/stress_test_evaluator.py --level extreme --model path/to/model.pt

# Custom output directory
python evaluation/stress_test_evaluator.py --level mild --output my_results/
```

## Interpreting Results

### Key Metrics

1. **Service Level**: % of demand met from stock
   - Higher is better
   - Target: >90% under MILD, >70% under EXTREME

2. **Stockouts**: Number of stockout events
   - Lower is better
   - PPO should reduce stockouts vs baseline

3. **Holding Cost**: Inventory carrying costs
   - Lower is better (but not at expense of service level)

4. **Reward**: Overall performance metric
   - Higher is better
   - Combines service level, stockouts, and costs

5. **Recovery Time**: Steps to recover after demand shocks
   - Lower is better
   - Indicates resilience

### What to Look For

✅ **Good Results**:
- PPO outperforms baseline across all metrics
- Service level degrades gracefully under stress
- Recovery time is low after shocks
- Stockouts are minimized

❌ **Poor Results**:
- PPO performs worse than baseline
- Service level collapses under stress
- Long recovery times
- Excessive stockouts

## Troubleshooting

### Error: Model not found
```
Solution: Train the model first using:
python agents/train_with_gym_env.py
```

### Error: Module not found
```
Solution: Ensure you're in the project root and venv is activated:
cd /path/to/inventory-hmarl
source venv/bin/activate
```

### Low performance under all levels
```
Possible causes:
1. Model not fully trained (train for more episodes)
2. Uncertainty config too aggressive (try MILD first)
3. Environment parameters need tuning
```

## Next Steps

After running stress tests:

1. **Analyze Results**: Review plots and reports
2. **Compare Levels**: How does performance degrade?
3. **Identify Weaknesses**: Where does PPO struggle?
4. **Iterate**: Retrain with different hyperparameters if needed

## Advanced: Custom Uncertainty Config

To create custom uncertainty levels, edit:
`demand/uncertainty_config.py`

Add new preset:
```python
UNCERTAINTY_PRESETS['CUSTOM'] = {
    'enable_regime_switching': True,
    'regime_transition_probs': custom_matrix,
    # ... other settings
}
```

Then run:
```bash
python evaluation/stress_test_evaluator.py --level custom
```
"""
