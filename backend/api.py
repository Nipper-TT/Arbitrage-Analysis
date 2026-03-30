"""API 路由定义"""

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from backend.akshare_client import fetch_contract_data, fetch_contract_name
from backend.analysis_engine import run_full_analysis
from backend.models import (
    AnalysisError,
    AnalysisRequest,
    AnalysisResponse,
    DataFetchError,
    ErrorResponse,
)

router = APIRouter()


@router.post(
    "/api/analyze",
    response_model=AnalysisResponse,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def analyze(request: AnalysisRequest) -> AnalysisResponse:
    """主分析接口：接收两个合约参数，返回全维度对比分析结果。"""

    # ── 业务校验：相同合约 ──────────────────────────────────
    if (
        request.contract_a.code == request.contract_b.code
        and request.contract_a.contract_type == request.contract_b.contract_type
    ):
        raise HTTPException(
            status_code=400,
            detail="两个合约代码和类型不能完全相同，请输入不同的合约进行对比",
        )

    # ── 数据获取 ────────────────────────────────────────────
    try:
        df_a = await fetch_contract_data(
            code=request.contract_a.code,
            contract_type=request.contract_a.contract_type,
            years=request.years,
        )
        df_b = await fetch_contract_data(
            code=request.contract_b.code,
            contract_type=request.contract_b.contract_type,
            years=request.years,
        )
    except DataFetchError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )

    # ── 分析计算 ────────────────────────────────────────────
    try:
        name_a = fetch_contract_name(request.contract_a.code, request.contract_a.contract_type)
        name_b = fetch_contract_name(request.contract_b.code, request.contract_b.contract_type)
        result = run_full_analysis(
            df_a=df_a,
            df_b=df_b,
            contract_a=request.contract_a,
            contract_b=request.contract_b,
            name_a=name_a,
            name_b=name_b,
        )
    except AnalysisError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    return result
