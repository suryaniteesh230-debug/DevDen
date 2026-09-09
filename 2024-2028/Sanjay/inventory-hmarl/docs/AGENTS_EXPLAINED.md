# Agents Folder - Detailed Explanation

## Overview

The `agents/` folder contains **9 files** that implement the multi-agent reinforcement learning system. These files handle agent behavior, PPO training, and the learning infrastructure.

---

## 1. **`base_agent.py`** - Abstract Base Class

### Purpose
Defines the **interface** that all agents must follow, ensuring consistency across Store, Warehouse, and Supplier agents.

### Key Components

**Abstract Methods** (must be implemented by subclasses):
- `observe(state)` → Extract agent-specific observation from global state
- `act(observation)` → Select action based on observation
- `receive_feedback(reconciliation_report)` → Compute reward from reconciliation

**Concrete Methods**:
- `reset()` - Reset agent for new episode
- `get_observation_space()` - Return observation dimensionality
- `get_action_space()` - Return number of actions
- `get_stats()` - Get performance metrics

### Why It Exists
- **Polymorphism**: Allows swapping agents without changing environment code
- **Consistency**: All agents follow same interface
- **Flexibility**: Supports both rule-based and learning-based agents

---

## 2. **`store_agent.py`** - Store Inventory Agent

### Purpose
Manages **store-level inventory decisions** - when and how much to order from the warehouse.

### Observation Space (7D)
1. **current_inventory** - Current stock level (normalized)
2. **forecasted_demand** - Predicted demand (moving average)
3. **demand_uncertainty** - Demand variability (std dev)
4. **days_of_inventory_cover** - How many days current inventory will last
5. **last_day_stockout** - Binary flag for stockout yesterday
6. **warehouse_inventory_ratio** - Warehouse stock availability
7. **recent_service_level** - Recent service performance

### Action Space (4 discrete actions)
- **0**: `no_order` - Don't order anything
- **1**: `order_0.5x` - Order 0.5× forecasted demand
- **2**: `order_1.0x` - Order 1.0× forecasted demand  
- **3**: `order_1.5x` - Order 1.5× forecasted demand

### Reward Function
```python
reward = (
    +10.0 × service_level        # Maximize service
    - 0.1 × holding_cost          # Minimize inventory
    - 5.0 × stockout_penalty      # Avoid stockouts
    - 0.05 × excess_inventory     # Avoid over-ordering
)
```

### Default Behavior
Uses **(s, S) policy**: Order up to target level when inventory falls below reorder point.

### Why It Exists
- **Core learning agent**: This is what PPO trains!
- **Parameter sharing**: Multiple stores share same policy
- **Realistic**: Balances service vs cost tradeoff

---

## 3. **`warehouse_agent.py`** - Warehouse Replenishment Agent

### Purpose
Manages **warehouse-level inventory** - ordering from supplier to support downstream stores.

### Observation Space (6D)
1. **aggregate_store_demand** - Total demand from all stores
2. **current_warehouse_inventory** - Current warehouse stock
3. **inbound_supplier_pipeline** - In-transit orders from supplier
4. **store_1_inventory** - Store 1 stock level
5. **store_2_inventory** - Store 2 stock level
6. **avg_store_service_level** - Average service across stores

### Action Space (4 discrete actions)
- **0**: `no_order` - Don't order
- **1**: `order_low` - Order 500 units (conservative)
- **2**: `order_medium` - Order 1000 units (standard)
- **3**: `order_high` - Order 1500 units (aggressive)

### Reward Function
```python
reward = (
    +5.0 × avg_store_service_level    # Support downstream
    - 0.05 × warehouse_holding_cost    # Minimize inventory
    - 3.0 × store_stockout_count       # Prevent store stockouts
)
```

### Default Behavior
Uses **(s, S) policy** with service level consideration.

### Why It Exists
- **Hierarchical coordination**: Supports multiple stores
- **Future learning**: Designed for PPO upgrade
- **Realistic**: Balances inventory vs service

---

## 4. **`supplier_agent.py`** - Supplier Fulfillment Agent

### Purpose
Manages **supplier operations** - fulfilling warehouse orders with lead time constraints.

### Observation Space (3D)
1. **warehouse_order_quantity** - Size of warehouse order
2. **current_production_capacity** - Supplier capacity
3. **days_until_delivery** - Lead time

### Action Space (3 discrete actions)
- **0**: `fulfill_full` - Ship full order (100%)
- **1**: `fulfill_partial` - Ship 80% of order
- **2**: `delay` - Delay shipment by 1 day

### Reward Function
```python
reward = (
    +2.0 × fulfillment_rate    # Reward fulfilling orders
    - 1.0 × delay_penalty       # Penalize delays
)
```

### Default Behavior
Always fulfills full order unless capacity constrained.

### Why It Exists
- **Completeness**: Models entire supply chain
- **Extensibility**: Can add supplier learning later
- **Realism**: Captures lead times and capacity

---

## 5. **`ppo_trainer.py`** ⭐ - PPO Algorithm Implementation

### Purpose
Implements **Proximal Policy Optimization** (PPO) algorithm for training agents.

### Key Components

**1. PolicyNetwork** (Actor)
- Maps observations → action probabilities
- 2-layer MLP: `obs_dim → 64 → 64 → action_dim`
- Outputs: Categorical distribution over actions

**2. ValueNetwork** (Critic)
- Maps observations → state values
- 2-layer MLP: `obs_dim → 64 → 64 → 1`
- Outputs: Scalar value estimate

**3. PPOTrainer** (Main Class)
- Combines actor + critic
- Implements PPO update algorithm
- Supports parameter sharing across agents

### PPO Algorithm Features

**Clipped Surrogate Objective**:
```python
ratio = π_new(a|s) / π_old(a|s)
clipped_ratio = clip(ratio, 1-ε, 1+ε)
L_CLIP = min(ratio × A, clipped_ratio × A)
```

**Generalized Advantage Estimation (GAE)**:
```python
A_t = δ_t + (γλ)δ_{t+1} + (γλ)²δ_{t+2} + ...
where δ_t = r_t + γV(s_{t+1}) - V(s_t)
```

**Loss Function**:
```python
L = L_CLIP - value_coef × L_value + entropy_coef × H(π)
```

### Hyperparameters
- **lr**: 3e-4 (learning rate)
- **gamma**: 0.99 (discount factor)
- **gae_lambda**: 0.95 (GAE parameter)
- **clip_epsilon**: 0.2 (PPO clipping)
- **value_coef**: 0.5 (value loss weight)
- **entropy_coef**: 0.01 (exploration bonus)

### Key Methods
- `select_action(obs)` - Sample action from policy
- `compute_gae(rewards, values, dones)` - Calculate advantages
- `update(experiences)` - PPO update step
- `save_checkpoint(path)` - Save model weights
- `load_checkpoint(path)` - Load model weights

### Why It Exists
- **Core RL algorithm**: This is the brain!
- **State-of-the-art**: PPO is proven effective
- **Stable**: Clipping prevents destructive updates

---

## 6. **`learning_wrapper.py`** - RL Wrapper for Agents

### Purpose
**Wraps any BaseAgent** to enable learning-based behavior while preserving rule-based fallback.

### Key Features

**1. Seamless Mode Switching**
```python
if learning_enabled and learner:
    action = learner.select_action(obs)  # Use PPO
else:
    action = agent.act(obs)  # Use rule-based
```

**2. Experience Collection**
Stores `(observation, action, reward, done)` tuples for training.

**3. Centralized Training Support**
- Pools experiences from multiple agents
- Supports parameter sharing
- Enables CTDE (Centralized Training, Decentralized Execution)

### Key Methods
- `observe(state)` - Delegates to wrapped agent
- `act(observation)` - Uses learner or rule-based
- `receive_feedback(report)` - Stores experience
- `mark_episode_end()` - Marks terminal state
- `update_learner()` - Triggers PPO update
- `get_experiences()` - Returns experience buffer
- `enable_learning()` / `disable_learning()` - Toggle modes

### Why It Exists
- **Flexibility**: Switch between learning/rule-based
- **Modularity**: Wraps any agent without modification
- **Training infrastructure**: Handles experience collection

---

## 7. **`train_hmarl.py`** - Original HMARL Training Script

### Purpose
Original training script for **hierarchical multi-agent RL**.

### Features
- Multi-agent training setup
- Hierarchical coordination
- Episode management
- Checkpoint saving

### Status
- **Legacy**: Replaced by `train_with_gym_env.py`
- **Kept for reference**: Shows original approach

---

## 8. **`train_with_gym_env.py`** ⭐ - Main Training Script

### Purpose
**Primary training script** that trains PPO on store agents using Gymnasium environment.

### What It Does

**1. Environment Setup**
```python
env = HMARLEnvironment(
    num_stores=3,
    num_warehouses=1,
    num_suppliers=1,
    episode_length=30
)
```

**2. PPO Initialization**
```python
ppo_trainer = PPOTrainer(
    obs_dim=7,  # Store observation space
    action_dim=4,  # Store action space
    lr=3e-4,
    gamma=0.99
)
```

**3. Training Loop**
```python
for episode in range(num_episodes):
    obs, info = env.reset()
    for step in range(episode_length):
        actions = {agent_id: ppo.select_action(obs[agent_id]) 
                   for agent_id in store_agents}
        obs, rewards, done, truncated, info = env.step(actions)
        # Collect experiences
    # Update PPO
    ppo.update(all_experiences)
```

**4. Checkpoint Saving**
Saves trained model to `checkpoints/ppo_store_agents_gym.pt`

### Why It Exists
- **Main training**: This is what trained the model!
- **Gymnasium compatible**: Modern RL interface
- **Production-ready**: Clean, well-tested code

---

## 9. **`coordinator_agent.py`** - Placeholder

### Purpose
Placeholder for future **hierarchical coordination** agent.

### Current Status
- **Empty**: Only 20 bytes
- **Future work**: Could coordinate warehouse + stores

---

## File Relationships

```
┌─────────────────────────────────────────────────────────────┐
│                    Training Workflow                         │
└─────────────────────────────────────────────────────────────┘

train_with_gym_env.py
    ↓ creates
PPOTrainer (ppo_trainer.py)
    ↓ wraps agents with
LearningWrapper (learning_wrapper.py)
    ↓ wraps
StoreAgent (store_agent.py) ← inherits from BaseAgent
    ↓ trains on
HMARLEnvironment (env/hmarl_env.py)
    ↓ saves to
checkpoints/ppo_store_agents_gym.pt
```

---

## Summary Table

| File | Purpose | Key Feature | Status |
|------|---------|-------------|--------|
| `base_agent.py` | Abstract interface | Polymorphism | ✅ Core |
| `store_agent.py` | Store inventory | 7D obs, 4 actions | ✅ Trained with PPO |
| `warehouse_agent.py` | Warehouse replenishment | 6D obs, 4 actions | ✅ Rule-based |
| `supplier_agent.py` | Supplier fulfillment | 3D obs, 3 actions | ✅ Rule-based |
| `ppo_trainer.py` | PPO algorithm | Actor-Critic + GAE | ✅ Core RL |
| `learning_wrapper.py` | RL wrapper | Mode switching | ✅ Infrastructure |
| `train_hmarl.py` | Original training | Legacy | 📦 Archived |
| `train_with_gym_env.py` | Main training | Gymnasium | ⭐ **Primary** |
| `coordinator_agent.py` | Coordination | Future work | 🚧 Placeholder |

---

## Quick Reference

### To Train a New Model
```bash
python agents/train_with_gym_env.py
```

### To Use Trained Model
```python
from agents.ppo_trainer import PPOTrainer
import torch

ppo = PPOTrainer(obs_dim=7, action_dim=4)
ppo.actor_critic.load_state_dict(
    torch.load('checkpoints/ppo_store_agents_gym.pt')
)

action = ppo.select_action(observation, deterministic=True)
```

### To Create Custom Agent
```python
from agents.base_agent import BaseAgent

class MyAgent(BaseAgent):
    def observe(self, state):
        # Extract observation
        return observation
    
    def act(self, observation):
        # Select action
        return action
    
    def receive_feedback(self, report):
        # Compute reward
        return reward
```

---

**Total Lines of Code**: ~1,900 lines  
**Core Files**: 6 (base, store, warehouse, supplier, ppo, wrapper)  
**Training Files**: 2 (train_hmarl, train_with_gym_env)  
**Status**: Production-ready, fully tested
