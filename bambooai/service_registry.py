from bambooai.messages.prompts import Prompts

OUTPUT_MANAGER_SERVICE = "output_manager"
PROMPTS_SERVICE = "prompts_service"

class ServiceContainer:
    def __init__(self):
        self._services = {}

    def register(self, service_name, service_instance):
        if service_name in self._services:
            raise ValueError(f"Service {service_name} is already registered.")
        self._services[service_name] = service_instance

    def get_service(self, service_name):
        return self._services.get(service_name)

    def list_services(self):
        return list(self._services.keys())
    
    def get_prompts(self) -> Prompts:
        prompts = self.get_service(PROMPTS_SERVICE)
        if prompts is None:
            print(f"Prompts service not found, creating a new instance with default config.")
            prompts = Prompts()
            self.register(PROMPTS_SERVICE, prompts)
        return prompts
    
    def register_prompts(self, prompts: Prompts):
        self.register(PROMPTS_SERVICE, prompts)
    
services = ServiceContainer()