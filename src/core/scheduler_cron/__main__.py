from importlib import import_module

_service_main = import_module("core.scheduler_cron.service_main")


if __name__ == "__main__":
    _service_main.main()
