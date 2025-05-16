from bambooai.messages.prompts import Prompts

OUTPUT_MANAGER_SERVICE = "output"
PROMPTS_SERVICE = "prompts"

class ServiceContainer:
    def __init__(self):
        self._services = {}

    def register(self, name, instance):
        self._services[name] = instance

    def get(self, name, default = None):
        return self._services.get(name, default)

    def register_prompts(self, prompts: Prompts):
        self.register(PROMPTS_SERVICE, prompts)
    
    def get_prompts(self) -> Prompts:
        return self.get(PROMPTS_SERVICE)

services = ServiceContainer()