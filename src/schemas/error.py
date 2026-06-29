from pydantic import BaseModel, Field


class ErrorDetailSchema(BaseModel):
    code: str
    message: str


class ErrorResponseSchema(BaseModel):
    success: bool = Field(default=False)
    error: ErrorDetailSchema
