from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any

class CBCData(BaseModel):
    Hb: float = Field(..., alias="Hb_g_dL")
    RBC: float = Field(..., alias="RBC_million_uL")
    HCT: float = Field(..., alias="HCT_percent")
    MCV: float = Field(..., alias="MCV_fL")
    MCH: float = Field(..., alias="MCH_pg")
    MCHC: float = Field(..., alias="MCHC_g_dL")
    RDW: float = Field(..., alias="RDW_percent")
    WBC: float = Field(..., alias="WBC_10_3_uL")
    Platelets: float = Field(..., alias="Platelets_10_3_uL")
    Neutrophils: Optional[float] = Field(None, alias="Neutrophils_percent")
    Lymphocytes: Optional[float] = Field(None, alias="Lymphocytes_percent")
    Age: int
    Sex: str

class ScreeningRequest(BaseModel):
    patientId: str
    cbc: CBCData

class ScreeningResponse(BaseModel):
    riskClass: int
    label: str
    probabilities: Dict[str, float]
    rulesFired: List[str]
    recommendation: str
    modelVersion: str
    indices: Dict[str, float]
