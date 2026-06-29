from src.core.base_exception import AppError


class PipelineError(AppError):
    def __init__(self, message: str):
        super().__init__(message)


class PipelineChannelNotFoundError(PipelineError):
    def __init__(self, channel_id: int):
        super().__init__(f"Channel {channel_id} not found")
        self.channel_id = channel_id


class PipelineStateError(PipelineError):
    def __init__(self, message: str):
        super().__init__(message)


class PipelineNodeError(PipelineError):
    def __init__(self, node: str, message: str):
        super().__init__(f"Pipeline node '{node}' failed: {message}")
        self.node = node


class PipelinePublishError(PipelineError):
    def __init__(self, message: str):
        super().__init__(message)
