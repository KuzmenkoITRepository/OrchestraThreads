from core.orchestra_thread.tests.test_e2e_agent_lifecycle import AgentLifecycleE2ETests
from core.orchestra_thread.tests.test_e2e_thread_flow import ThreadFlowE2ETests
from core.orchestra_thread.tests.test_e2e_ui import UiE2ETests

MVP_TEST_CASES = (AgentLifecycleE2ETests, ThreadFlowE2ETests, UiE2ETests)
