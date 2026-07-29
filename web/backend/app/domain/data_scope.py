from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DataScopeAsset(BaseModel):
    assetClass: str = "equity"
    market: str = "china"
    venue: str | None = None
    resolution: str = "daily"
    dataType: str = "trade"


class DataScopeSelection(BaseModel):
    type: Literal["symbols", "universe", "products", "all"] = "symbols"
    values: list[str] = Field(default_factory=list, max_length=500)


class DataScopeTime(BaseModel):
    startDate: str | None = None
    endDate: str | None = None
    asOfDate: str | None = None

    @model_validator(mode="after")
    def validate_window(self):
        if self.startDate and self.endDate and self.startDate > self.endDate:
            raise ValueError("startDate cannot be after endDate")
        return self


class DataScopePrice(BaseModel):
    adjust: str = "raw"


class DataScopeProvider(BaseModel):
    source: str = "tushare"
    mode: Literal["strict", "fallback"] = "strict"
    allowResearchSource: bool = False


class DataScope(BaseModel):
    asset: DataScopeAsset = Field(default_factory=DataScopeAsset)
    selection: DataScopeSelection = Field(default_factory=DataScopeSelection)
    time: DataScopeTime = Field(default_factory=DataScopeTime)
    price: DataScopePrice = Field(default_factory=DataScopePrice)
    provider: DataScopeProvider = Field(default_factory=DataScopeProvider)


class DataQueryRequest(BaseModel):
    scope: DataScope
    dataset: str = "bars"
    fields: list[str] = Field(default_factory=list, max_length=50)
    limit: int = Field(default=500, ge=1, le=1000)
