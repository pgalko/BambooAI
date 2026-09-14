"""
Container orchestration module for BambooAI
Handles container lifecycle management via Nomad
"""
from .container_manager import ContainerManager
from .main_app_integration import ContainerOrchestrator

# Import create_orchestrator_app conditionally to avoid circular imports
def get_orchestrator_app():
    from .orchestrator_api import create_orchestrator_app
    return create_orchestrator_app()

__all__ = ['ContainerManager', 'ContainerOrchestrator', 'get_orchestrator_app']
__version__ = '1.0.0'