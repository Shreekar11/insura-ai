from typing import Dict, Callable

class ActivityRegistry:
    """Central registry for all activities."""
    
    _activities: Dict[str, Callable] = {}
    
    @classmethod
    def register(cls, category: str, name: str = None):
        """Decorator to register an activity."""
        def decorator(activity_func):
            activity_name = name or activity_func.__name__
            cls._activities[f"{category}:{activity_name}"] = activity_func
            return activity_func
        return decorator
    
    @classmethod
    def get_all_activities(cls) -> Dict[str, Callable]:
        """Get all registered activities."""
        return cls._activities
