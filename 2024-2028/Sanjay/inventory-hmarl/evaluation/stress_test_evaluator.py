"""
stress_test_evaluator.py

Stress-test evaluation pipeline for HMARL system.

Evaluates trained PPO agents under realistic uncertainty without retraining.
Compares performance against baseline policies under different stress levels.

Usage:
    python evaluation/stress_test_evaluator.py --level mild
    python evaluation/stress_test_evaluator.py --level high
    python evaluation/stress_test_evaluator.py --level extreme
"""

import os
import sys
import argparse
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from typing import Dict, List, Tuple
import csv

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from env.hmarl_env import HMARLEnvironment
from agents.ppo_trainer import PPOTrainer
from demand.uncertainty_config import get_uncertainty_config


class StressTestEvaluator:
    """
    Stress-test evaluation pipeline.
    
    Runs trained PPO model under various uncertainty levels and compares
    against baseline policies.
    """
    
    def __init__(
        self,
        model_path: str,
        uncertainty_level: str = 'MILD',
        num_episodes: int = 50,
        episode_length: int = 30,
        output_dir: str = None
    ):
        """
        Initialize stress-test evaluator.
        
        Args:
            model_path: Path to trained PPO model
            uncertainty_level: 'NONE', 'MILD', 'HIGH', or 'EXTREME'
            num_episodes: Number of evaluation episodes
            episode_length: Steps per episode
            output_dir: Output directory for results
        """
        self.model_path = model_path
        self.uncertainty_level = uncertainty_level.upper()
        self.num_episodes = num_episodes
        self.episode_length = episode_length
        
        # Output directory
        if output_dir is None:
            output_dir = f'evaluation/stress_results/{self.uncertainty_level.lower()}'
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        
        print(f"\n{'='*70}")
        print(f"STRESS TEST EVALUATOR")
        print(f"{'='*70}")
        print(f"Uncertainty Level: {self.uncertainty_level}")
        print(f"Model Path: {self.model_path}")
        print(f"Episodes: {self.num_episodes}")
        print(f"Episode Length: {episode_length}")
        print(f"Output Directory: {self.output_dir}")
        print(f"{'='*70}\n")
    
    def _create_environment(self, use_uncertainty: bool = True) -> HMARLEnvironment:
        """
        Create HMARL environment with optional uncertainty.
        
        Args:
            use_uncertainty: Whether to enable uncertainty features
        
        Returns:
            HMARLEnvironment instance
        """
        # Get uncertainty configuration
        if use_uncertainty:
            uncertainty_config = get_uncertainty_config(self.uncertainty_level)
        else:
            uncertainty_config = get_uncertainty_config('NONE')
        
        # Create environment with uncertainty
        env = HMARLEnvironment(
            num_stores=3,
            num_warehouses=1,
            num_suppliers=1,
            episode_length=self.episode_length,
            uncertainty_config=uncertainty_config
        )
        
        return env
    
    def _load_ppo_model(self, env: HMARLEnvironment) -> PPOTrainer:
        """
        Load trained PPO model.
        
        Args:
            env: Environment instance
        
        Returns:
            PPOTrainer with loaded weights
        """
        # Get observation and action dimensions from a store agent
        store_agent_id = 'store_1'
        obs_dim = env.observation_space[store_agent_id].shape[0]
        action_dim = env.action_space[store_agent_id].n
        
        # Create PPO trainer
        ppo_trainer = PPOTrainer(
            obs_dim=obs_dim,
            action_dim=action_dim,
            lr=3e-4,
            gamma=0.99,
            clip_epsilon=0.2
        )
        
        # Load model weights
        import torch
        if os.path.exists(self.model_path):
            ppo_trainer.actor_critic.load_state_dict(torch.load(self.model_path))
            print(f"✓ Loaded PPO model from: {self.model_path}")
        else:
            raise FileNotFoundError(f"Model not found: {self.model_path}")
        
        return ppo_trainer
    
    def run_evaluation(
        self,
        env: HMARLEnvironment,
        ppo_trainer: PPOTrainer,
        use_ppo: bool,
        policy_name: str
    ) -> Dict:
        """
        Run evaluation for a given policy.
        
        Args:
            env: Environment instance
            ppo_trainer: PPO trainer (for PPO policy)
            use_ppo: Whether to use PPO policy (vs baseline)
            policy_name: Name of policy for logging
        
        Returns:
            Dictionary with metrics
        """
        print(f"\nEvaluating {policy_name} policy...")
        print(f"{'='*70}")
        
        # Store agent IDs
        store_agent_ids = [f'store_{i+1}' for i in range(env.num_stores)]
        
        # Metrics storage
        all_metrics = {
            'episode_rewards': [],
            'service_levels': [],
            'stockouts': [],
            'holding_costs': [],
            'shock_periods': [],  # Track when shocks occur
            'recovery_times': []  # Track recovery after shocks
        }
        
        for episode in range(self.num_episodes):
            observations, info = env.reset()
            episode_reward = 0.0
            episode_stockouts = 0
            episode_holding_cost = 0.0
            episode_demand_met = 0.0
            episode_total_demand = 0.0
            
            in_shock = False
            shock_start = -1
            
            for step in range(self.episode_length):
                # Select actions
                actions = {}
                for agent_id in env.agent_ids:
                    obs = observations[agent_id]
                    
                    if agent_id in store_agent_ids:
                        if use_ppo:
                            # Use trained PPO policy (deterministic)
                            action = ppo_trainer.select_action(obs, deterministic=True)
                        else:
                            # Use baseline rule-based policy
                            action = env.agents[agent_id].act(obs)
                    else:
                        # Warehouse and supplier always use rule-based
                        action = env.agents[agent_id].act(obs)
                    
                    actions[agent_id] = action
                
                # Step environment
                next_observations, rewards, terminated, truncated, info = env.step(actions)
                
                # Collect metrics
                episode_reward += sum(rewards.values())
                
                # Track stockouts and service level
                for agent_id in store_agent_ids:
                    agent = env.agents[agent_id]
                    if hasattr(agent, 'last_stockout'):
                        episode_stockouts += agent.last_stockout
                    if hasattr(agent, 'last_demand_met'):
                        episode_demand_met += agent.last_demand_met
                    if hasattr(agent, 'last_total_demand'):
                        episode_total_demand += agent.last_total_demand
                    if hasattr(agent, 'last_holding_cost'):
                        episode_holding_cost += agent.last_holding_cost
                
                # Detect shock periods (if demand generators have regime info)
                # This is a simplified shock detection
                if hasattr(env, 'digital_twin'):
                    # Check if any store is experiencing high demand
                    high_demand = False
                    for store_id in store_agent_ids:
                        if store_id in env.digital_twin.stores:
                            store = env.digital_twin.stores[store_id]
                            if hasattr(store, 'demand_generator'):
                                regime = store.demand_generator.get_current_regime()
                                if regime and regime.name in ['HIGH', 'SPIKE']:
                                    high_demand = True
                                    break
                    
                    if high_demand and not in_shock:
                        in_shock = True
                        shock_start = step
                    elif not high_demand and in_shock:
                        in_shock = False
                        recovery_time = step - shock_start
                        all_metrics['recovery_times'].append(recovery_time)
                
                observations = next_observations
                
                if terminated or truncated:
                    break
            
            # Calculate episode metrics
            service_level = (
                episode_demand_met / episode_total_demand
                if episode_total_demand > 0
                else 1.0
            )
            
            all_metrics['episode_rewards'].append(episode_reward)
            all_metrics['service_levels'].append(service_level)
            all_metrics['stockouts'].append(episode_stockouts)
            all_metrics['holding_costs'].append(episode_holding_cost)
            
            if (episode + 1) % 10 == 0:
                print(f"  Episode {episode+1}/{self.num_episodes} - "
                      f"Reward: {episode_reward:.2f}, "
                      f"Service Level: {service_level*100:.1f}%, "
                      f"Stockouts: {episode_stockouts}")
        
        # Compute summary statistics
        summary = {
            'policy_name': policy_name,
            'avg_reward': np.mean(all_metrics['episode_rewards']),
            'std_reward': np.std(all_metrics['episode_rewards']),
            'avg_service_level': np.mean(all_metrics['service_levels']),
            'std_service_level': np.std(all_metrics['service_levels']),
            'avg_stockouts': np.mean(all_metrics['stockouts']),
            'std_stockouts': np.std(all_metrics['stockouts']),
            'avg_holding_cost': np.mean(all_metrics['holding_costs']),
            'std_holding_cost': np.std(all_metrics['holding_costs']),
            'avg_recovery_time': np.mean(all_metrics['recovery_times']) if all_metrics['recovery_times'] else 0.0
        }
        
        print(f"\n{policy_name} Summary:")
        print(f"  Avg Reward: {summary['avg_reward']:.2f} ± {summary['std_reward']:.2f}")
        print(f"  Avg Service Level: {summary['avg_service_level']*100:.1f}% ± {summary['std_service_level']*100:.1f}%")
        print(f"  Avg Stockouts: {summary['avg_stockouts']:.1f} ± {summary['std_stockouts']:.1f}")
        print(f"  Avg Holding Cost: {summary['avg_holding_cost']:.2f} ± {summary['std_holding_cost']:.2f}")
        if all_metrics['recovery_times']:
            print(f"  Avg Recovery Time: {summary['avg_recovery_time']:.1f} steps")
        
        return {
            'metrics': all_metrics,
            'summary': summary
        }
    
    def generate_plots(self, baseline_results: Dict, ppo_results: Dict):
        """
        Generate comparison plots.
        
        Args:
            baseline_results: Results from baseline policy
            ppo_results: Results from PPO policy
        """
        print(f"\nGenerating comparison plots...")
        
        # Set style
        plt.style.use('seaborn-v0_8-darkgrid')
        
        # 1. Service Level Comparison
        fig, ax = plt.subplots(figsize=(12, 6))
        episodes = range(1, self.num_episodes + 1)
        
        ax.plot(episodes, baseline_results['metrics']['service_levels'], 
                label='Baseline', alpha=0.7, linewidth=1.5)
        ax.plot(episodes, ppo_results['metrics']['service_levels'], 
                label='PPO', alpha=0.7, linewidth=1.5)
        
        ax.set_xlabel('Episode', fontsize=12)
        ax.set_ylabel('Service Level', fontsize=12)
        ax.set_title(f'Service Level Comparison - {self.uncertainty_level} Uncertainty', fontsize=14, fontweight='bold')
        ax.legend(fontsize=11)
        ax.grid(True, alpha=0.3)
        
        service_plot = os.path.join(self.output_dir, 'service_level_comparison.png')
        plt.tight_layout()
        plt.savefig(service_plot, dpi=300)
        plt.close()
        print(f"  ✓ Saved: {service_plot}")
        
        # 2. Stockouts Comparison
        fig, ax = plt.subplots(figsize=(12, 6))
        
        ax.plot(episodes, baseline_results['metrics']['stockouts'], 
                label='Baseline', alpha=0.7, linewidth=1.5)
        ax.plot(episodes, ppo_results['metrics']['stockouts'], 
                label='PPO', alpha=0.7, linewidth=1.5)
        
        ax.set_xlabel('Episode', fontsize=12)
        ax.set_ylabel('Stockouts', fontsize=12)
        ax.set_title(f'Stockouts Comparison - {self.uncertainty_level} Uncertainty', fontsize=14, fontweight='bold')
        ax.legend(fontsize=11)
        ax.grid(True, alpha=0.3)
        
        stockouts_plot = os.path.join(self.output_dir, 'stockouts_comparison.png')
        plt.tight_layout()
        plt.savefig(stockouts_plot, dpi=300)
        plt.close()
        print(f"  ✓ Saved: {stockouts_plot}")
        
        # 3. Rewards Comparison
        fig, ax = plt.subplots(figsize=(12, 6))
        
        ax.plot(episodes, baseline_results['metrics']['episode_rewards'], 
                label='Baseline', alpha=0.7, linewidth=1.5)
        ax.plot(episodes, ppo_results['metrics']['episode_rewards'], 
                label='PPO', alpha=0.7, linewidth=1.5)
        
        ax.set_xlabel('Episode', fontsize=12)
        ax.set_ylabel('Episode Reward', fontsize=12)
        ax.set_title(f'Rewards Comparison - {self.uncertainty_level} Uncertainty', fontsize=14, fontweight='bold')
        ax.legend(fontsize=11)
        ax.grid(True, alpha=0.3)
        
        rewards_plot = os.path.join(self.output_dir, 'rewards_comparison.png')
        plt.tight_layout()
        plt.savefig(rewards_plot, dpi=300)
        plt.close()
        print(f"  ✓ Saved: {rewards_plot}")
        
        # 4. Summary Bar Chart
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        metrics = ['Service Level', 'Stockouts', 'Holding Cost', 'Reward']
        baseline_vals = [
            baseline_results['summary']['avg_service_level'] * 100,
            baseline_results['summary']['avg_stockouts'],
            baseline_results['summary']['avg_holding_cost'],
            baseline_results['summary']['avg_reward']
        ]
        ppo_vals = [
            ppo_results['summary']['avg_service_level'] * 100,
            ppo_results['summary']['avg_stockouts'],
            ppo_results['summary']['avg_holding_cost'],
            ppo_results['summary']['avg_reward']
        ]
        
        for idx, (ax, metric, baseline_val, ppo_val) in enumerate(zip(axes.flat, metrics, baseline_vals, ppo_vals)):
            x = ['Baseline', 'PPO']
            y = [baseline_val, ppo_val]
            colors = ['#ff7f0e', '#2ca02c']
            
            ax.bar(x, y, color=colors, alpha=0.7)
            ax.set_ylabel(metric, fontsize=11)
            ax.set_title(f'Avg {metric}', fontsize=12, fontweight='bold')
            ax.grid(True, alpha=0.3, axis='y')
            
            # Add value labels
            for i, v in enumerate(y):
                ax.text(i, v, f'{v:.2f}', ha='center', va='bottom', fontsize=10)
        
        plt.suptitle(f'Performance Summary - {self.uncertainty_level} Uncertainty', 
                     fontsize=16, fontweight='bold')
        plt.tight_layout()
        
        summary_plot = os.path.join(self.output_dir, 'summary_comparison.png')
        plt.savefig(summary_plot, dpi=300)
        plt.close()
        print(f"  ✓ Saved: {summary_plot}")
    
    def generate_report(self, baseline_results: Dict, ppo_results: Dict):
        """
        Generate text report.
        
        Args:
            baseline_results: Results from baseline policy
            ppo_results: Results from PPO policy
        """
        report_path = os.path.join(self.output_dir, 'stress_test_report.txt')
        
        with open(report_path, 'w') as f:
            f.write("="*70 + "\n")
            f.write("STRESS TEST EVALUATION REPORT\n")
            f.write("="*70 + "\n\n")
            
            f.write(f"Uncertainty Level: {self.uncertainty_level}\n")
            f.write(f"Model Path: {self.model_path}\n")
            f.write(f"Episodes: {self.num_episodes}\n")
            f.write(f"Episode Length: {self.episode_length}\n")
            f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            f.write("="*70 + "\n")
            f.write("BASELINE POLICY RESULTS\n")
            f.write("="*70 + "\n\n")
            
            baseline_summary = baseline_results['summary']
            f.write(f"Average Reward: {baseline_summary['avg_reward']:.2f} ± {baseline_summary['std_reward']:.2f}\n")
            f.write(f"Average Service Level: {baseline_summary['avg_service_level']*100:.2f}% ± {baseline_summary['std_service_level']*100:.2f}%\n")
            f.write(f"Average Stockouts: {baseline_summary['avg_stockouts']:.2f} ± {baseline_summary['std_stockouts']:.2f}\n")
            f.write(f"Average Holding Cost: {baseline_summary['avg_holding_cost']:.2f} ± {baseline_summary['std_holding_cost']:.2f}\n")
            if baseline_summary['avg_recovery_time'] > 0:
                f.write(f"Average Recovery Time: {baseline_summary['avg_recovery_time']:.2f} steps\n")
            
            f.write("\n" + "="*70 + "\n")
            f.write("PPO POLICY RESULTS\n")
            f.write("="*70 + "\n\n")
            
            ppo_summary = ppo_results['summary']
            f.write(f"Average Reward: {ppo_summary['avg_reward']:.2f} ± {ppo_summary['std_reward']:.2f}\n")
            f.write(f"Average Service Level: {ppo_summary['avg_service_level']*100:.2f}% ± {ppo_summary['std_service_level']*100:.2f}%\n")
            f.write(f"Average Stockouts: {ppo_summary['avg_stockouts']:.2f} ± {ppo_summary['std_stockouts']:.2f}\n")
            f.write(f"Average Holding Cost: {ppo_summary['avg_holding_cost']:.2f} ± {ppo_summary['std_holding_cost']:.2f}\n")
            if ppo_summary['avg_recovery_time'] > 0:
                f.write(f"Average Recovery Time: {ppo_summary['avg_recovery_time']:.2f} steps\n")
            
            f.write("\n" + "="*70 + "\n")
            f.write("COMPARISON & IMPROVEMENT\n")
            f.write("="*70 + "\n\n")
            
            reward_improvement = ((ppo_summary['avg_reward'] - baseline_summary['avg_reward']) / 
                                 abs(baseline_summary['avg_reward']) * 100)
            service_improvement = ((ppo_summary['avg_service_level'] - baseline_summary['avg_service_level']) / 
                                  baseline_summary['avg_service_level'] * 100)
            stockout_reduction = ((baseline_summary['avg_stockouts'] - ppo_summary['avg_stockouts']) / 
                                 baseline_summary['avg_stockouts'] * 100)
            
            f.write(f"Reward Improvement: {reward_improvement:+.2f}%\n")
            f.write(f"Service Level Improvement: {service_improvement:+.2f}%\n")
            f.write(f"Stockout Reduction: {stockout_reduction:+.2f}%\n\n")
            
            f.write("="*70 + "\n")
            f.write("ANALYSIS\n")
            f.write("="*70 + "\n\n")
            
            if self.uncertainty_level == 'MILD':
                f.write("Under MILD uncertainty, both policies should perform reasonably well.\n")
                f.write("PPO should show modest improvements in handling demand variability.\n")
            elif self.uncertainty_level == 'HIGH':
                f.write("Under HIGH uncertainty, performance degradation is expected.\n")
                f.write("PPO's learned policy should demonstrate better resilience than baseline.\n")
            elif self.uncertainty_level == 'EXTREME':
                f.write("Under EXTREME uncertainty, significant performance degradation is expected.\n")
                f.write("PPO should show superior robustness in handling severe shocks and disruptions.\n")
            
            f.write(f"\nThe PPO policy shows {reward_improvement:+.2f}% reward improvement over baseline.\n")
            f.write(f"Service level is {service_improvement:+.2f}% {'better' if service_improvement > 0 else 'worse'}.\n")
            f.write(f"Stockouts are reduced by {stockout_reduction:.2f}%.\n")
            
            f.write("\n" + "="*70 + "\n")
        
        print(f"  ✓ Saved: {report_path}")
        
        # Also print to console
        with open(report_path, 'r') as f:
            print("\n" + f.read())
    
    def save_metrics_csv(self, baseline_results: Dict, ppo_results: Dict):
        """Save metrics to CSV files."""
        # Episode-level metrics
        csv_path = os.path.join(self.output_dir, 'episode_metrics.csv')
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Episode', 'Baseline_Reward', 'PPO_Reward', 
                           'Baseline_ServiceLevel', 'PPO_ServiceLevel',
                           'Baseline_Stockouts', 'PPO_Stockouts'])
            
            for i in range(self.num_episodes):
                writer.writerow([
                    i + 1,
                    baseline_results['metrics']['episode_rewards'][i],
                    ppo_results['metrics']['episode_rewards'][i],
                    baseline_results['metrics']['service_levels'][i],
                    ppo_results['metrics']['service_levels'][i],
                    baseline_results['metrics']['stockouts'][i],
                    ppo_results['metrics']['stockouts'][i]
                ])
        
        print(f"  ✓ Saved: {csv_path}")
    
    def run(self):
        """Run complete stress-test evaluation."""
        print(f"\nStarting stress-test evaluation...")
        
        # Create environment with uncertainty
        env = self._create_environment(use_uncertainty=True)
        
        # Load PPO model
        ppo_trainer = self._load_ppo_model(env)
        
        # Run baseline evaluation
        baseline_results = self.run_evaluation(
            env=env,
            ppo_trainer=ppo_trainer,
            use_ppo=False,
            policy_name="Baseline"
        )
        
        # Run PPO evaluation
        ppo_results = self.run_evaluation(
            env=env,
            ppo_trainer=ppo_trainer,
            use_ppo=True,
            policy_name="PPO"
        )
        
        # Generate outputs
        print(f"\nGenerating outputs...")
        self.generate_plots(baseline_results, ppo_results)
        self.save_metrics_csv(baseline_results, ppo_results)
        self.generate_report(baseline_results, ppo_results)
        
        print(f"\n{'='*70}")
        print(f"✓ Stress-test evaluation complete!")
        print(f"  Results saved to: {self.output_dir}")
        print(f"{'='*70}\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Stress-test HMARL system under uncertainty')
    parser.add_argument('--level', type=str, default='MILD',
                       choices=['NONE', 'MILD', 'HIGH', 'EXTREME'],
                       help='Uncertainty level')
    parser.add_argument('--model', type=str, default='checkpoints/ppo_store_agents_gym.pt',
                       help='Path to trained PPO model')
    parser.add_argument('--episodes', type=int, default=50,
                       help='Number of evaluation episodes')
    parser.add_argument('--length', type=int, default=30,
                       help='Episode length')
    parser.add_argument('--output', type=str, default=None,
                       help='Output directory')
    
    args = parser.parse_args()
    
    # Create evaluator
    evaluator = StressTestEvaluator(
        model_path=args.model,
        uncertainty_level=args.level,
        num_episodes=args.episodes,
        episode_length=args.length,
        output_dir=args.output
    )
    
    # Run evaluation
    evaluator.run()


if __name__ == '__main__':
    main()
