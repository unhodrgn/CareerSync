from pydantic import BaseModel, ConfigDict, Field


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    intro: str
    talent_profile: str = Field(description="인재상")


class CompanyUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    intro: str = Field("", max_length=1000)
    talent_profile: str = Field("", max_length=1000, description="인재상")
