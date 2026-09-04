from mjlab_microduck import tasks

def register() -> dict:
    return {'package': 'microduck', 'tasks_registered': True, 'observation_dim': 61, 'action_dim': 14}
