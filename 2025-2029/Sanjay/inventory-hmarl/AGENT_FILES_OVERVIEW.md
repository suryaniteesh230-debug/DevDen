# HMARL Agent & Training Files Overview

## Directory Structure

```
inventory-hmarl/
├── agents/              # Agent implementations & PPO training
├── env/                 # HMARL environment
├── training/            # Training scripts & pipelines
├── evaluation/          # Model evaluation
├── baseline_policies/   # Baseline comparison policies
└── checkpoints/         # Trained model weights
```

---

## 1. Agents Directory (`agents/`)

### Core Agent Files

**`base_agent.py`** (4.5 KB)
- Base class for all agents
- Defines common agent interface
- Observation/action handling

**`store_agent.py`** (8.1 KB)
- Store-level agent implementation
- Manages store inventory decisions
- Implements ordering logic

**`warehouse_agent.py`** (7.5 KB)
- Warehouse-level agent implementation
- Manages warehouse replenishment
- Handles store order fulfillment

**`supplier_agent.py`** (5.6 KB)
- Supplier-level agent implementation
- Manages supplier operations
- Handles order processing

**`coordinator_agent.py`** (20 bytes)
- Placeholder for hierarchical coordination
- Future: Multi-level decision coordination

### PPO Training Files

**`ppo_trainer.py`** (11.8 KB) ⭐ **KEY FILE**
- PPO algorithm implementation
- Actor-Critic neural network
- Training loop logic
- Advantage estimation (GAE)
- Policy gradient updates

**`learning_wrapper.py`** (7.4 KB)
- Wraps agents for RL training
- Handles experience collection
- Manages training/inference modes

### Training Scripts

**`train_hmarl.py`** (9.9 KB)
- Original HMARL training script
- Multi-agent training setup
- Hierarchical coordination

**`train_with_gym_env.py`** (10.0 KB) ⭐ **MAIN TRAINING SCRIPT**
- Gymnasium-compatible training
- PPO training for store agents
- Episode management
- Checkpoint saving
- **This is what was used to train the model!**

---

## 2. Environment Directory (`env/`)

**`hmarl_env.py`** (17.8 KB) ⭐ **CORE ENVIRONMENT**
- HMARL environment implementation
- Gymnasium interface
- Multi-agent coordination
- Observation/action spaces
- Reward calculation
- **Supports uncertainty features!**

**`digital_twin.py`** (13.2 KB)
- Digital twin simulation
- Supply chain entities
- State management
- Metrics tracking

---

## 3. Training Directory (`training/`)

### Training Scripts

**`train_ppo_phase1.py`** (16.9 KB)
- Phase 1 PPO training
- Detailed training pipeline
- Hyperparameter configuration
- Progress tracking

**`run_complete_pipeline.py`** (3.6 KB)
- End-to-end training pipeline
- Orchestrates full training process
- Validation and evaluation

**`compare_baseline_vs_ppo.py`** (15.4 KB)
- Compares PPO vs baseline policies
- Performance benchmarking
- Generates comparison plots

**`validate_environment.py`** (15.9 KB)
- Environment validation
- Sanity checks
- Debugging utilities

### Documentation

**`TRAINING_GUIDE.md`** (16.1 KB)
- Complete training guide
- Hyperparameter explanations
- Best practices

**`PPO_TRAINING_SUMMARY.md`** (20.0 KB)
- Training results summary
- Performance metrics
- Lessons learned

---

## 4. Evaluation Directory (`evaluation/`)

**`evaluate_trained_model.py`**
- Loads trained PPO model
- Runs evaluation episodes
- Generates performance reports

**`stress_test_evaluator.py`** (NEW - from our work!)
- Stress testing under uncertainty
- Compares PPO vs baseline
- Generates comprehensive reports

---

## 5. Baseline Policies (`baseline_policies/`)

Comparison policies for benchmarking:
- `base_stock_policy.py` - (s, S) inventory policy
- `constant_order_policy.py` - Fixed order quantities
- `random_policy.py` - Random actions
- And more...

---

## 6. Checkpoints Directory (`checkpoints/`)

**`ppo_store_agents_gym.pt`** (131 KB) ⭐ **TRAINED MODEL**
- Trained PPO model weights
- Ready for evaluation
- Used by stress test evaluator

---

## Key Workflow

### Training Flow
```
1. agents/train_with_gym_env.py
   ↓ uses
2. agents/ppo_trainer.py (PPO algorithm)
   ↓ trains on
3. env/hmarl_env.py (environment)
   ↓ saves to
4. checkpoints/ppo_store_agents_gym.pt
```

### Evaluation Flow
```
1. evaluation/stress_test_evaluator.py
   ↓ loads
2. checkpoints/ppo_store_agents_gym.pt
   ↓ runs on
3. env/hmarl_env.py (with uncertainty!)
   ↓ generates
4. Results & plots
```

---

## Most Important Files

### For Understanding the System
1. **`env/hmarl_env.py`** - Core environment
2. **`agents/ppo_trainer.py`** - PPO algorithm
3. **`agents/train_with_gym_env.py`** - Training script

### For Running/Testing
1. **`checkpoints/ppo_store_agents_gym.pt`** - Trained model
2. **`evaluation/stress_test_evaluator.py`** - Stress testing
3. **`demo_uncertainty_features.py`** - Quick demo

### For Training
1. **`agents/train_with_gym_env.py`** - Main training
2. **`training/train_ppo_phase1.py`** - Alternative training
3. **`training/TRAINING_GUIDE.md`** - Documentation

---

## Quick Commands

### Train a new model
```bash
source venv/bin/activate
python agents/train_with_gym_env.py
```

### Evaluate trained model
```bash
source venv/bin/activate
python evaluation/evaluate_trained_model.py
```

### Run stress test
```bash
source venv/bin/activate
python evaluation/stress_test_evaluator.py --level mild
```

### Demo uncertainty features
```bash
python3 demo_uncertainty_features.py
```

---

## File Count Summary

- **Agents**: 9 files (agents/)
- **Environment**: 2 files (env/)
- **Training**: 7 files (training/)
- **Evaluation**: 10 files (evaluation/)
- **Baseline Policies**: 7 files (baseline_policies/)
- **Checkpoints**: 1 trained model

**Total**: ~36 files related to agents, HMARL, PPO, and training!
