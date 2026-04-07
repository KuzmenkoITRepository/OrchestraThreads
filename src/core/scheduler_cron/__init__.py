from importlib import import_module

_config_module = import_module("core.scheduler_cron.config")

SchedulerCronConfig = _config_module.SchedulerCronConfig
load_config = _config_module.load_config
