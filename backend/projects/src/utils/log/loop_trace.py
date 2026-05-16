# Compatibility shim for coze_coding_utils internal imports
from coze_coding_utils.log.loop_trace import init_run_config, init_agent_config

__all__ = ["init_run_config", "init_agent_config"]
