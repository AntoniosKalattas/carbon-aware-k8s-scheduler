"""Write scheduler configuration using a private local kubeconfig."""
import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
profiles = []
for mode, name in [('energy', 'energy-scheduler'), ('carbon', 'green-scheduler')]:
    profiles.append({
        'schedulerName': name,
        'plugins': {'score': {'disabled': [{'name': '*'}],
                              'enabled': [{'name': 'GreenScore', 'weight': 1}]}},
        'pluginConfig': [{'name': 'GreenScore', 'args': {
            'mode': mode, 'seconds': 10.5,
            'regions': {'cyprus': {'watts': 40, 'carbon': 700},
                        'greece': {'watts': 60, 'carbon': 350},
                        'italy': {'watts': 80, 'carbon': 100}}
        }}]})
config = {'apiVersion': 'kubescheduler.config.k8s.io/v1',
          'kind': 'KubeSchedulerConfiguration',
          'clientConnection': {'kubeconfig': str(root/'.runtime/kubeconfig')},
          'leaderElection': {'leaderElect': False},
          'profiles': profiles}
(root/'.runtime').mkdir(exist_ok=True)
(root/'.runtime/scheduler.json').write_text(json.dumps(config, indent=2))
