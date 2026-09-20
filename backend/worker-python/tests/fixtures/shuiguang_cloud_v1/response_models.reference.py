"""Pydantic v2：三视图三项检测成功响应合同草稿。"""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

View = Literal["left", "front", "right"]
Region = Literal["forehead", "nose", "left_cheek", "right_cheek", "perioral", "chin"]
Severity = Literal["未见明显", "轻度", "中度", "较明显", "显著"]
Count = Annotated[int, Field(strict=True, ge=0)]

class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class ViewImages(ContractModel):
    left: str = Field(description="自动识别为左侧视图的输入图片ID。")
    front: str = Field(description="自动识别为正面视图的输入图片ID，也是评分主图。")
    right: str = Field(description="自动识别为右侧视图的输入图片ID。")

class ViewCounts(ContractModel):
    left: Count | None = Field(description="左侧照片的目标数量；0为已评估未检出，null为不可评估。")
    front: Count | None = Field(description="正面照片的目标数量；0为已评估未检出，null为不可评估。")
    right: Count | None = Field(description="右侧照片的目标数量；0为已评估未检出，null为不可评估。")

class RegionResult(ContractModel):
    region: Region = Field(description="区域ID；左右面颊以受检者本人为准。")
    name: str = Field(description="区域中文名称，用于展示。")
    left: Count | None = Field(description="左侧照片本区域的目标数量；null为未覆盖或不可评估。")
    front: Count | None = Field(description="正面照片本区域的目标数量；null为未覆盖或不可评估。")
    right: Count | None = Field(description="右侧照片本区域的目标数量；null为未覆盖或不可评估。")
    primary_view: View | None = Field(description="本区域主观察视图；无可用观察时为null。")
    primary_count: Count | None = Field(description="主观察视图对应数量，必须与同一行对应视图的数量一致；不是三图合计。")
    supplementary_views: list[View] = Field(description="包含额外发现的补充视图；无补充发现时为空数组。")

class DetectionResult(ContractModel):
    name: str = Field(description="检测项目中文名称。")
    score: float | None = Field(ge=0, le=100, description="正面主图评分，0至100；越高表示相关图像表现越明显，不可用时为null。")
    severity: Severity | None = Field(description="与本项评分口径对应的程度等级；评分不可用时为null。")
    score_view: Literal["front"] = Field(description="评分使用的视图，固定为正面front。")
    score_basis: Literal["v2_visible_pores", "v2_visible_spots_component", "v2_oiliness_tendency"] = Field(description="评分来源：V2毛孔评分、可见色斑独立子分、油脂分泌倾向评分；后者包含油光与卟啉证据。")
    total_count: ViewCounts = Field(description="三张照片各自的全部目标数，三个视图不相加。")
    regions: list[RegionResult] = Field(description="本项分区统计列表，对应网页统计表中的区域行。")
    unassigned_count: ViewCounts = Field(description="三张照片各自未单列位置或归属待定的数量；与已列分区数量之和等于同图总数。")

class DetectionResults(ContractModel):
    pores: DetectionResult = Field(description="毛孔评分、程度与三视图分区计数。")
    spots: DetectionResult = Field(description="可见色斑独立评分、程度与三视图分区计数。")
    surface_gloss: DetectionResult = Field(description="表面油光分区计数；评分和程度暂沿用V2油脂分泌倾向口径。")

class ShuiguangResponse(ContractModel):
    schema_version: Literal["shuiguang_cloud_v1"] = Field(description="响应JSON结构版本。")
    task_id: str = Field(description="检测任务唯一ID，关联请求、结果与日志。")
    status: Literal["success"] = Field(description="此模型限定成功响应，表示三视图识别和三项检测完成。")
    main_image_id: str = Field(description="正面主图输入图片ID，必须与views.front一致。")
    views: ViewImages = Field(description="识别后的左侧、正面、右侧视图与上传图片ID的映射。")
    results: DetectionResults = Field(description="毛孔、可见色斑、表面油光三项结果。")
