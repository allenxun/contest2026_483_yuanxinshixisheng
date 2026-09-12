# -*- coding: utf-8 -*-
"""矩阵完整性自检（真实执行，selfcheck/matrix 都必须通过）。

用独立解析器从设计文档原文重新提取，与 matrix/*.json 逐项比对，防止生成脚本
单点出错：
- 场景恰 94 条、ID 唯一；分节计数、P0/P1 计数与文档声明一致；
- 每条字段齐全、status=dependency_pending、blocked_by=B/C/D 业务包（A 基线已交付，
  pending_reason 反映"业务实现未集成、端点 501 stub"）、
  pending_reason 非空、owner_package 符合 API 级归属（M1/M2/M5→B；M3→D；
  M4-A01/A02→D；M4-A03..A09→C，场景取并集）；
- API 恰 27 条；scenarios↔apis 双向一致，并与文档"覆盖汇总"表交叉核对
  （文档表未展开 SC-C-01 的"全部 27 个 API"，本矩阵按 27 个展开）。
"""
from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]          # backend/acceptance
DOC = ROOT.parent / "doc"                                    # backend/doc
SCEN_DOC = DOC / "测试场景清单-V1-五模块与双控制.md"
API_DOC = DOC / "后端API接口设计-V1-五模块与流程对应.md"

scenarios = json.loads((ROOT / "matrix" / "scenarios.json").read_text(encoding="utf-8"))
apis = json.loads((ROOT / "matrix" / "apis.json").read_text(encoding="utf-8"))
by_id = {s["id"]: s for s in scenarios}

EXPECTED_SECTION_COUNTS = {"SC-00": 4, "SC-01": 18, "SC-02": 11, "SC-03": 9,
                           "SC-04": 10, "SC-05": 7, "SC-06": 9, "SC-07": 7,
                           "SC-C": 5, "SC-R": 14}
ALL_API_IDS = [f"M{m}-A{i:02d}" for m, n in ((1, 3), (2, 8), (3, 6), (4, 9), (5, 1))
               for i in range(1, n + 1)]


def parse_doc_scenarios() -> dict[str, dict]:
    """独立解析场景表行。"""
    out: dict[str, dict] = {}
    for line in SCEN_DOC.read_text(encoding="utf-8").splitlines():
        if not re.match(r"^\|\s*SC-\d{2}-\d{2}\s*\||^\|\s*SC-[CR]-\d{2}\s*\|", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        assert len(cells) == 7, f"场景行字段数异常：{cells[0]}"
        sid = cells[0]
        assert sid not in out, f"文档场景 ID 重复：{sid}"
        out[sid] = {"priority": cells[1], "scope": cells[2], "title": cells[3],
                    "checkpoints": cells[4], "api_cell": cells[5], "dep_cell": cells[6]}
    return out


def parse_doc_api_table() -> dict[str, set[str]]:
    """解析"覆盖汇总"的 API→场景表。"""
    out: dict[str, set[str]] = {}
    for line in SCEN_DOC.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*(M\d-A\d{2})\s*\|\s*(SC-.*?)\s*\|$", line)
        if m:
            out[m.group(1)] = set(re.findall(r"SC-(?:0[0-7]|[CR])-\d{2}", m.group(2)))
    return out


# ---------- 数量与唯一性 ----------

def test_scenarios_exactly_94_and_unique():
    assert len(scenarios) == 94, f"scenarios.json 应恰 94 条，实际 {len(scenarios)}"
    assert len(by_id) == 94, "存在重复场景 ID"
    assert set(by_id) == set(parse_doc_scenarios()), "矩阵与文档场景 ID 集合不一致"


def test_priority_counts_match_document_claim():
    p0 = sum(1 for s in scenarios if s["priority"] == "P0")
    p1 = sum(1 for s in scenarios if s["priority"] == "P1")
    m = re.search(r"共 \*\*(\d+) 个测试场景\*\*（P0：(\d+)，P1：(\d+)）",
                  SCEN_DOC.read_text(encoding="utf-8"))
    assert m, "文档覆盖汇总声明未找到"
    doc_total, doc_p0, doc_p1 = (int(x) for x in m.groups())
    assert (p0 + p1, p0, p1) == (doc_total, doc_p0, doc_p1), (
        f"逐行提取 P0={p0}/P1={p1} 与文档声明 P0={doc_p0}/P1={doc_p1} 不一致，须如实记录差异")


def test_section_distribution():
    got: dict[str, int] = {}
    for s in scenarios:
        got[s["id"].rsplit("-", 1)[0]] = got.get(s["id"].rsplit("-", 1)[0], 0) + 1
    assert got == EXPECTED_SECTION_COUNTS, f"分节计数不一致：{got}"


# ---------- 与文档逐行一致 ----------

def test_each_scenario_matches_document_row():
    doc = parse_doc_scenarios()
    assert set(doc) == set(by_id)
    for sid, d in doc.items():
        s = by_id[sid]
        assert s["priority"] == d["priority"], sid
        assert s["scope"] == d["scope"], sid
        assert s["title"] == d["title"], sid
        assert s["checkpoints"] == d["checkpoints"], sid
        assert s["deps"] == (re.findall(r"D\d{2}", d["dep_cell"])), sid
        if d["api_cell"] == "全部 27 个 API":
            assert sorted(s["apis"]) == ALL_API_IDS, f"{sid} 应展开为全部 27 个 API"
        else:
            assert sorted(s["apis"]) == sorted(re.findall(r"M\d-A\d{2}", d["api_cell"])), sid


# ---------- 必备字段与门控状态 ----------

REQUIRED = ("id", "section", "priority", "scope", "title", "checkpoints", "apis",
            "deps", "owner_package", "blocked_by", "automation_tier", "status",
            "pending_reason")


def test_required_fields_and_pending_status():
    for s in scenarios:
        for k in REQUIRED:
            assert k in s, f"{s.get('id')} 缺字段 {k}"
        assert s["status"] == "dependency_pending", s["id"]
        # B/C/D 均已集成（approved f045433 / merge HEAD 08404f8）→ 无未集成包阻塞。
        assert s["blocked_by"] == [], s["id"]
        assert s["pending_reason"].strip(), s["id"]
        assert s["priority"] in ("P0", "P1") and s["scope"] in ("后端", "集成", "联调")
        assert s["automation_tier"] in ("现在可自动", "需替身", "需真实设备或APP")
        assert s["apis"], s["id"]
        # staged 三态：authored 与 staged_pending 互斥且齐全。
        assert isinstance(s["authored"], bool) and isinstance(s["staged_pending"], bool)
        assert s["authored"] != s["staged_pending"], s["id"]
        if s["staged_pending"]:
            assert s["staged_reason"] == "场景步骤编写中（集成轮 batch 1）", s["id"]
        else:
            assert s["staged_reason"] is None, s["id"]


def test_owner_package_mapping():
    """API 级归属（总协调 2026-09-10 权威澄清）：M1/M2/M5→B；M3→D；
    M4-A01/M4-A02→D（方案生成 Worker 相关）；M4-A03..A09→C（执行/记账 HTTP）。
    场景 owner_package = 关联 API 归属并集（升序）。"""
    def owner(aid: str) -> str:
        if aid in ("M4-A01", "M4-A02"):
            return "D"
        return {"M1": "B", "M2": "B", "M3": "D", "M4": "C", "M5": "B"}[aid[:2]]
    for s in scenarios:
        expect = sorted({owner(a) for a in s["apis"]})
        assert s["owner_package"] == expect, f"{s['id']} owner_package {s['owner_package']} != {expect}"


def test_blocked_by_excludes_integrated_packages():
    """blocked_by = owner_package − 已集成包（B/C/D 均已集成 @f045433）→ 全部 []。"""
    integrated = {"B", "C", "D"}
    for s in scenarios:
        assert s["blocked_by"] == sorted(set(s["owner_package"]) - integrated), s["id"]
        assert s["blocked_by"] == [], s["id"]


def test_blocked_by_distribution_all_empty():
    """B/C/D 集成后分布恰为 []×94（全量逐条，非抽查）。"""
    dist: dict[str, int] = {}
    for s in scenarios:
        key = "".join(s["blocked_by"])
        dist[key] = dist.get(key, 0) + 1
    assert dist == {"": 94}, dist


def test_staged_pending_three_state_and_authored_first_wave():
    """staged 三态：batch1 25 + lane A1（SC-02 11）+ lane A2（SC-03 9）+ lane B1（SC-04 10）=55。"""
    authored = [s for s in scenarios if s["authored"]]
    staged = [s for s in scenarios if s["staged_pending"]]
    assert len(authored) == 80, len(authored)
    assert len(staged) == 14, len(staged)
    batch1 = {
        "SC-01-01", "SC-01-02", "SC-01-03", "SC-01-04", "SC-01-05", "SC-01-06",
        "SC-01-07", "SC-01-08", "SC-01-09", "SC-01-10", "SC-01-11", "SC-01-12",
        "SC-01-13", "SC-01-14", "SC-01-15", "SC-01-16", "SC-01-17", "SC-01-18",
        "SC-05-01", "SC-05-02", "SC-05-03", "SC-05-04", "SC-05-05", "SC-05-06",
        "SC-05-07"}
    batch2 = {f"SC-02-{i:02d}" for i in range(1, 12)}
    batch3 = {f"SC-03-{i:02d}" for i in range(1, 10)}
    batch4 = {f"SC-04-{i:02d}" for i in range(1, 11)}
    batch5 = {f"SC-06-{i:02d}" for i in range(1, 10)} | {f"SC-07-{i:02d}" for i in range(1, 8)}
    batch6 = {f"SC-00-{i:02d}" for i in range(1,5)} | {f"SC-C-{i:02d}" for i in range(1,6)}
    assert {s["id"] for s in authored} == batch1 | batch2 | batch3 | batch4 | batch5 | batch6
    device = [s for s in authored if s["automation_tier"] == "需真实设备或APP"]
    assert len(device) == 27, len(device)
    for s in device:
        assert s["pending_reason"].startswith("真实设备/APP 联调待办"), s["id"]
    for s in authored:
        if s["automation_tier"] != "需真实设备或APP":
            assert s["pending_reason"].startswith("已编写步骤"), s["id"]


def test_business_semantics_invariant_hash():
    """剔除 blocked_by/pending_reason/staged_* 后，94 条业务语义哈希与变更前逐字节一致。"""
    import hashlib
    drop = {"blocked_by", "pending_reason", "staged_pending", "staged_reason", "authored"}
    canon = [{k: v for k, v in s.items() if k not in drop} for s in scenarios]
    got = hashlib.sha256(json.dumps(canon, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()[:16]
    assert got == "86bfa7b721b6f285", got


def test_automation_tier_matches_scope():
    m = {"后端": "现在可自动", "集成": "需替身", "联调": "需真实设备或APP"}
    for s in scenarios:
        assert s["automation_tier"] == m[s["scope"]], s["id"]


# ---------- API 侧 ----------

def test_apis_exactly_27():
    assert len(apis) == 27, f"apis.json 应恰 27 条，实际 {len(apis)}"
    assert sorted(a["id"] for a in apis) == ALL_API_IDS
    for a in apis:
        assert a["module"] == a["id"][:2]
        assert a["title"] and a["http"] and re.match(r"^(GET|POST|PUT|DELETE) /", a["http"])
        assert a["scenarios"], a["id"]


def test_bidirectional_consistency():
    api_index = {a["id"]: set(a["scenarios"]) for a in apis}
    assert set(api_index) == set(ALL_API_IDS)
    for s in scenarios:
        for aid in s["apis"]:
            assert s["id"] in api_index[aid], f"{s['id']} → {aid} 无反向引用"
    for aid, sids in api_index.items():
        for sid in sids:
            assert sid in by_id, f"{aid} 引用不存在场景 {sid}"
            assert aid in by_id[sid]["apis"], f"{aid} ← {sid} 正向缺失"


def test_cross_check_against_document_summary_table():
    doc_table = parse_doc_api_table()
    assert set(doc_table) == set(ALL_API_IDS), "文档覆盖汇总表 API 集合异常"
    api_index = {a["id"]: set(a["scenarios"]) for a in apis}
    for aid in ALL_API_IDS:
        # 文档表按行内编号汇总，SC-C-01（"全部 27 个 API"）未在其中展开；矩阵已展开。
        expected = doc_table[aid] | {"SC-C-01"}
        assert api_index[aid] == expected, (
            f"{aid}: 矩阵 {sorted(api_index[aid] ^ expected)} 与文档汇总表不一致")
