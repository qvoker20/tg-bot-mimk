from pydantic import BaseModel


class RequestCodePayload(BaseModel):
    phone: str


class VerifyCodePayload(BaseModel):
    phone: str
    code: str
