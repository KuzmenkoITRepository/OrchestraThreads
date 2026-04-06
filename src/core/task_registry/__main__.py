from importlib import import_module

main = import_module("core.task_registry.mcp_server").main


if __name__ == "__main__":
    main()
