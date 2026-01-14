"""Discovery utility for Temporal workflows and activities."""

import os
import importlib
import pkgutil
from app.utils.logging import get_logger

logger = get_logger(__name__)

def discover_shared_components(package_name: str = "app.temporal.shared"):
    """
    Dynamically discover and import all shared workflows and activities.
    """
    try:
        module = importlib.import_module(package_name)
        # Handle cases where __file__ is None (namespace packages)
        module_path = getattr(module, "__file__", None)
        if module_path:
            module_path = os.path.dirname(module_path)
        elif hasattr(module, "__path__"):
            module_path = module.__path__[0]
        else:
            logger.warning(f"Could not determine path for package: {package_name}")
            return
            
        # logger.debug(f"Discovering shared components in: {module_path}")
        
        # We want to import everything in shared/activities and shared/workflows
        sub_packages = [
            f"{package_name}.activities",
            f"{package_name}.workflows",
        ]
        
        for sub_pkg in sub_packages:
            try:
                sub_module = importlib.import_module(sub_pkg)
                sub_module_path = getattr(sub_module, "__file__", None)
                if sub_module_path:
                    sub_module_path = os.path.dirname(sub_module_path)
                elif hasattr(sub_module, "__path__"):
                    sub_module_path = sub_module.__path__[0]
                else:
                    logger.debug(f"Could not determine path for sub-package: {sub_pkg}")
                    continue
                
                for _, mod_name, _ in pkgutil.walk_packages([sub_module_path], f"{sub_pkg}."):
                    importlib.import_module(mod_name)
                    logger.debug(f"Imported shared component module: {mod_name}")
            except ImportError as ie:
                logger.debug(f"Could not import sub-package {sub_pkg}: {ie}")
                continue
                
    except Exception as e:
        logger.error(f"Failed to discover shared components: {e}", exc_info=True)


def discover_business_workflows(package_name: str = "app.temporal.product"):
    """
    Dynamically discover and import all business workflows.
    """
    try:
        module = importlib.import_module(package_name)
        module_path = getattr(module, "__file__", None)
        if module_path:
            module_path = os.path.dirname(module_path)
        elif hasattr(module, "__path__"):
            module_path = module.__path__[0]
        else:
            # logger.debug(f"Could not determine path for package: {package_name}")
            return
            
        # logger.debug(f"Discovering business workflows in: {module_path}")
        
        for _, name, is_pkg in pkgutil.iter_modules([module_path]):
            if is_pkg:
                sub_packages = [
                    f"{package_name}.{name}.activities",
                    f"{package_name}.{name}.workflows",
                ]
                
                for sub_pkg in sub_packages:
                    try:
                        sub_module = importlib.import_module(sub_pkg)
                        sub_module_path = getattr(sub_module, "__file__", None)
                        if sub_module_path:
                            sub_module_path = os.path.dirname(sub_module_path)
                        elif hasattr(sub_module, "__path__"):
                            sub_module_path = sub_module.__path__[0]
                        else:
                            logger.debug(f"Could not determine path for sub-package: {sub_pkg}")
                            continue
                        
                        for _, mod_name, _ in pkgutil.walk_packages([sub_module_path], f"{sub_pkg}."):
                            importlib.import_module(mod_name)
                            logger.debug(f"Imported business workflow module: {mod_name}")
                            
                    except ImportError:
                        continue
                        
    except Exception as e:
        logger.error(f"Failed to discover business workflows: {e}", exc_info=True)


def discover_all():
    """Discover all Temporal components."""
    discover_shared_components()
    discover_business_workflows()
    logger.info("All Temporal workflows and activities discovered and registered successfully")
