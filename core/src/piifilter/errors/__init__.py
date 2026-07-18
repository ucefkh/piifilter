"""PIIFilter error types — clean, typed errors."""

from __future__ import annotations


class PIIFilterError(Exception):
    """Base error for all PIIFilter exceptions."""
    def __init__(self, message: str, code: str = "UNKNOWN"):
        self.code = code
        super().__init__(message)


class PluginError(PIIFilterError):
    """Plugin loading, registration, or lifecycle error."""
    def __init__(self, message: str, plugin_name: str = "", code: str = "PLUGIN_ERROR"):
        self.plugin_name = plugin_name
        super().__init__(f"[{plugin_name}] {message}" if plugin_name else message, code)


class DetectorError(PIIFilterError):
    """Detection failed."""
    def __init__(self, message: str, detector: str = ""):
        super().__init__(message, "DETECTOR_ERROR")


class ProviderError(PIIFilterError):
    """Provider communication failed."""
    def __init__(self, message: str, provider: str = ""):
        super().__init__(f"[{provider}] {message}" if provider else message, "PROVIDER_ERROR")


class PolicyError(PIIFilterError):
    """Policy evaluation error."""
    def __init__(self, message: str):
        super().__init__(message, "POLICY_ERROR")


class ConfigurationError(PIIFilterError):
    """Configuration validation error."""
    def __init__(self, message: str):
        super().__init__(message, "CONFIG_ERROR")


class PipelineError(PIIFilterError):
    """Pipeline execution error."""
    def __init__(self, message: str, stage: str = ""):
        super().__init__(f"[{stage}] {message}" if stage else message, "PIPELINE_ERROR")


class SessionError(PIIFilterError):
    """Session validation error."""
    def __init__(self, message: str):
        super().__init__(message, "SESSION_ERROR")