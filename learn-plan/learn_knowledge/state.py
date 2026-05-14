from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from learn_core.io import read_json_if_exists, write_json, write_text
from learn_core.text_utils import normalize_int, normalize_string_list

KNOWLEDGE_STATE_FILENAME = "knowledge-state.json"
KNOWLEDGE_MAP_FILENAME = "knowledge-map.md"
CONTRACT_VERSION = "learn-plan.knowledge-state.v1"
SCHEMA_VERSION = "1.1"
SUPPORTED_SCHEMA_VERSIONS = {"1.0", SCHEMA_VERSION}
DEFAULT_DIAGNOSTIC_MAX_ROUNDS = 3
DEFAULT_DIAGNOSTIC_QUESTIONS_PER_ROUND = 5
KNOWLEDGE_LEVELS = ["domain", "module", "concept_cluster", "concept", "atomic_knowledge_point"]
LEGACY_KNOWLEDGE_LEVELS = {"topic", "knowledge_point"}
LEAF_LEVELS = {"knowledge_point", "atomic_knowledge_point"}
STRUCTURAL_LEVELS = {"domain", "module", "concept_cluster", "concept", "topic"}
SUPPORTED_KNOWLEDGE_LEVELS = set(KNOWLEDGE_LEVELS) | LEGACY_KNOWLEDGE_LEVELS
DEFAULT_CONSERVATIVE_MASTERY_DELTA = 20
MAX_MASTERY_DELTA = DEFAULT_CONSERVATIVE_MASTERY_DELTA
DEFAULT_EVIDENCE_TYPES = {
    "recognition",
    "explanation",
    "calculation",
    "implementation",
    "transfer",
    "retention",
    "debugging",
}


class KnowledgeStateError(ValueError):
    pass


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def resolve_knowledge_paths(plan_path: Path) -> dict[str, Path]:
    root = plan_path.expanduser().resolve().parent
    return {
        "knowledge_state": root / KNOWLEDGE_STATE_FILENAME,
        "knowledge_map": root / KNOWLEDGE_MAP_FILENAME,
    }


def _slug(value: Any, fallback: str) -> str:
    text = str(value or "").strip().lower()
    chars = []
    for char in text:
        if char.isalnum():
            chars.append(char)
        elif chars and chars[-1] != "-":
            chars.append("-")
    slug = "".join(chars).strip("-")
    return slug or fallback


def derive_status_label(mastery: Any) -> str:
    try:
        score = int(float(mastery))
    except (TypeError, ValueError):
        score = 0
    if score >= 100:
        return "已熟练掌握"
    if score >= 80:
        return "已熟悉"
    if score >= 60:
        return "已了解"
    if score > 0:
        return "不熟悉"
    return "未学习"


def _node_title(node: dict[str, Any]) -> str:
    return str(node.get("title") or node.get("id") or "未命名知识点").strip()


def _unique(items: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for item in items:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, dict) else str(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _extract_candidate_stages(planning: dict[str, Any] | None) -> list[dict[str, Any]]:
    planning = planning if isinstance(planning, dict) else {}
    candidates: list[Any] = []
    for key in ("stage_plan", "stages", "daily_roadmap"):
        value = planning.get(key)
        if isinstance(value, list) and value:
            candidates = value
            break
    return [item for item in candidates if isinstance(item, dict)]


def _extract_research_capabilities(research: dict[str, Any] | None) -> list[str]:
    research = research if isinstance(research, dict) else {}
    report = research.get("research_report") if isinstance(research.get("research_report"), dict) else research
    values: list[str] = []
    for key in ("must_master_core", "must_master_capabilities", "mainline_capabilities", "supporting_capabilities"):
        values.extend(normalize_string_list(report.get(key)))
    metrics = report.get("capability_metrics") if isinstance(report.get("capability_metrics"), list) else []
    for metric in metrics:
        if isinstance(metric, dict):
            values.append(str(metric.get("name") or metric.get("title") or metric.get("capability") or "").strip())
    return [item for item in _unique([item for item in values if item])]


def _default_required_evidence(title: str, goal: str) -> list[str]:
    text = f"{title} {goal}".lower()
    evidence = ["explanation"]
    if any(token in text for token in ("代码", "编程", "python", "pandas", "api", "实现", "项目", "脚本")):
        evidence.append("implementation")
    if any(token in text for token in ("计算", "公式", "数学", "统计", "窗口", "聚合")):
        evidence.append("calculation")
    if any(token in text for token in ("debug", "调试", "错误", "异常", "排障")):
        evidence.append("debugging")
    if any(token in text for token in ("迁移", "综合", "项目", "应用", "真实")):
        evidence.append("transfer")
    return [item for item in _unique(evidence) if item in DEFAULT_EVIDENCE_TYPES]


def _default_atomic_titles(concept_title: str, topic: str, goal: str) -> list[str]:
    concept_text = str(concept_title or "").lower()
    text = f"{concept_title} {topic} {goal}".lower()
    pandas_api_by_concept = {
        "窗口": ["DataFrame.rolling", "Rolling.mean", "DataFrame.resample", "DataFrame.groupby", "DataFrame.agg"],
        "时间": ["pd.to_datetime", "Timestamp", "Timedelta", "DatetimeIndex", "Series.dt"],
        "缺失": ["DataFrame.isna", "DataFrame.fillna", "DataFrame.dropna"],
        "读取": ["pd.read_csv", "DataFrame.head", "DataFrame.info"],
        "筛选": ["DataFrame.loc", "DataFrame.iloc", "Series.between"],
        "合并": ["pd.merge", "DataFrame.join", "pd.concat"],
    }
    if "pandas" in text:
        for marker, apis in pandas_api_by_concept.items():
            if marker.lower() in concept_text:
                return apis[:4]
        for marker, apis in pandas_api_by_concept.items():
            if marker.lower() in text:
                return apis[:4]
        return ["pd.DataFrame", "Series", "DataFrame.loc", "DataFrame.groupby"]
    if any(token in text for token in ("python", "代码", "编程")):
        return [f"{concept_title}：语义识别", f"{concept_title}：最小代码实现", f"{concept_title}：边界条件", f"{concept_title}：常见错误调试"]
    return [f"{concept_title}：概念定义", f"{concept_title}：最小例子", f"{concept_title}：常见误区", f"{concept_title}：迁移应用"]


def _infer_api_signature(title: str, topic: str) -> str | None:
    text = f"{title} {topic}"
    api_markers = ("pd.", "DataFrame.", "Series.", "Rolling.", "Timestamp", "Timedelta", "DatetimeIndex")
    return title if any(marker in text for marker in api_markers) else None


def _infer_operation_signature(title: str) -> str:
    if "：" in title:
        return title.split("：", 1)[1]
    if "(" in title and ")" in title:
        return "api_call"
    return "explain_then_apply"


def _default_common_misconceptions(title: str) -> list[str]:
    if any(token in title for token in ("to_datetime", "Timestamp", "Timedelta", "DatetimeIndex", "Series.dt")):
        return ["把字符串日期当成已解析时间类型", "混淆时间点 Timestamp 与时间间隔 Timedelta"]
    if any(token in title for token in ("rolling", "resample", "groupby", "agg")):
        return ["混淆按行数滚动窗口与按时间窗口聚合", "忽略窗口边界和索引类型对结果的影响"]
    return ["只记术语但不能解释边界", "能照抄例子但不能迁移到新任务"]


def _default_diagnostic_tasks(title: str) -> list[str]:
    tasks = [f"解释“{title}”解决什么问题", f"给出“{title}”的最小可运行例子"]
    if _infer_api_signature(title, ""):
        tasks.append(f"说明 {title} 的关键参数或返回对象")
    tasks.append(f"指出“{title}”的一个常见误区")
    return tasks[:4]


def _is_leaf_node(node: dict[str, Any]) -> bool:
    return node.get("level") in LEAF_LEVELS


def build_default_knowledge_state(
    *,
    topic: str,
    goal: str,
    level: str,
    schedule: str,
    preference: str,
    planning: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stages = _extract_candidate_stages(planning)
    capabilities = _extract_research_capabilities(research)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    domain_id = f"domain-{_slug(topic, 'main')}"
    nodes.append(
        {
            "id": domain_id,
            "title": topic or "学习主线",
            "level": "domain",
            "parent_id": None,
            "description": goal,
            "source": "learn-plan:goal",
            "relevance": 1.0,
            "derived_mastery": 0,
            "child_ids": [],
            "notes": ["顶层节点只展示 derived_mastery，不维护真实 mastery。"],
            "expandable_subpoints": [],
        }
    )

    if not stages:
        stages = [
            {"name": "核心主线", "focus": item, "goal": item}
            for item in (capabilities[:4] or [goal or topic or "核心能力"])
        ]

    previous_module_id: str | None = None
    for stage_index, stage in enumerate(stages[:8], start=1):
        title = str(stage.get("name") or stage.get("title") or stage.get("focus") or f"模块 {stage_index}").strip()
        module_id = f"module-{stage_index:02d}-{_slug(title, 'module')}"
        focus_values = normalize_string_list(stage.get("focus")) or normalize_string_list(stage.get("stage_goal")) or normalize_string_list(stage.get("goal")) or [title]
        nodes.append(
            {
                "id": module_id,
                "title": title,
                "level": "module",
                "parent_id": domain_id,
                "description": str(stage.get("goal") or stage.get("stage_goal") or stage.get("focus") or title),
                "source": "learn-plan:stage",
                "relevance": 1.0 if stage_index <= 3 else 0.7,
                "derived_mastery": 0,
                "child_ids": [],
                "notes": [],
                "expandable_subpoints": normalize_string_list(stage.get("expandable_subpoints")),
            }
        )
        nodes[0]["child_ids"].append(module_id)
        if previous_module_id:
            edges.append(
                {
                    "from": previous_module_id,
                    "to": module_id,
                    "type": "recommended",
                    "reason": "阶段路线推荐顺序",
                    "source": "learn-plan:stage_order",
                    "confidence": "medium",
                }
            )
        previous_module_id = module_id

        cluster_title = title
        cluster_id = f"cluster-{stage_index:02d}-{_slug(cluster_title, 'cluster')}"
        nodes.append(
            {
                "id": cluster_id,
                "title": cluster_title,
                "level": "concept_cluster",
                "parent_id": module_id,
                "description": f"围绕“{cluster_title}”组织核心概念与原子知识点。",
                "source": "learn-plan:concept_cluster",
                "relevance": 1.0 if stage_index <= 3 else 0.7,
                "derived_mastery": 0,
                "child_ids": [],
                "notes": [],
                "expandable_subpoints": normalize_string_list(stage.get("expandable_subpoints")),
            }
        )
        nodes[-2]["child_ids"].append(cluster_id)
        edges.append(
            {
                "from": module_id,
                "to": cluster_id,
                "type": "recommended",
                "reason": "模块包含该概念簇",
                "source": "learn-plan:concept_cluster",
                "confidence": "medium",
            }
        )

        concept_candidates = focus_values[:3]
        if len(concept_candidates) == 1 and title not in concept_candidates:
            concept_candidates.append(title)
        previous_atomic_id: str | None = None
        for concept_index, concept_title_raw in enumerate(concept_candidates[:4], start=1):
            concept_title = str(concept_title_raw or title).strip()
            concept_id = f"concept-{stage_index:02d}-{concept_index:02d}-{_slug(concept_title, 'concept')}"
            nodes.append(
                {
                    "id": concept_id,
                    "title": concept_title,
                    "level": "concept",
                    "parent_id": cluster_id,
                    "description": f"理解“{concept_title}”的语义、边界和常见误区。",
                    "source": "learn-plan:concept",
                    "relevance": 1.0 if stage_index <= 3 else 0.7,
                    "derived_mastery": 0,
                    "child_ids": [],
                    "notes": [],
                    "expandable_subpoints": [],
                }
            )
            cluster_node = next(item for item in nodes if item["id"] == cluster_id)
            cluster_node["child_ids"].append(concept_id)
            edges.append(
                {
                    "from": cluster_id,
                    "to": concept_id,
                    "type": "recommended",
                    "reason": "概念簇包含该概念",
                    "source": "learn-plan:concept",
                    "confidence": "medium",
                }
            )

            atomic_titles = _default_atomic_titles(concept_title, topic, goal)
            for atomic_index, atomic_title in enumerate(atomic_titles, start=1):
                point_id = f"akp-{stage_index:02d}-{concept_index:02d}-{atomic_index:02d}-{_slug(atomic_title, 'point')}"
                nodes.append(
                    {
                        "id": point_id,
                        "title": atomic_title,
                        "level": "atomic_knowledge_point",
                        "parent_id": concept_id,
                        "description": f"能围绕“{atomic_title}”完成解释、练习和应用验证。",
                        "source": "learn-plan:atomic_leaf",
                        "relevance": 1.0 if stage_index <= 3 else 0.7,
                        "mastery": 0,
                        "confidence": "low",
                        "target_mastery": 80 if stage_index <= 3 else 70,
                        "prerequisite_ids": [previous_atomic_id] if previous_atomic_id else [],
                        "api_signature": _infer_api_signature(atomic_title, topic),
                        "operation_signature": _infer_operation_signature(atomic_title),
                        "common_misconceptions": _default_common_misconceptions(atomic_title),
                        "diagnostic_tasks": _default_diagnostic_tasks(atomic_title),
                        "required_evidence_types": _default_required_evidence(atomic_title, goal),
                        "status_label": "未学习",
                        "last_studied": None,
                        "last_tested": None,
                        "evidence_refs": [],
                        "next_action": "learn",
                        "notes": [],
                        "expandable_subpoints": [],
                    }
                )
                concept_node = next(item for item in nodes if item["id"] == concept_id)
                concept_node["child_ids"].append(point_id)
                edges.append(
                    {
                        "from": concept_id,
                        "to": point_id,
                        "type": "recommended",
                        "reason": "概念包含该原子知识点",
                        "source": "learn-plan:atomic_leaf",
                        "confidence": "medium",
                    }
                )
                if previous_atomic_id:
                    edges.append(
                        {
                            "from": previous_atomic_id,
                            "to": point_id,
                            "type": "hard",
                            "reason": "同一概念下按基础到应用顺序形成前置依赖",
                            "source": "learn-plan:atomic_prerequisite",
                            "confidence": "low",
                        }
                    )
                previous_atomic_id = point_id

    state = {
        "contract_version": CONTRACT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "goal": {
            "topic": topic,
            "goal": goal,
            "level": level,
            "schedule": schedule,
            "preference": preference,
        },
        "status": "draft",
        "nodes": nodes,
        "edges": edges,
        "coverage_report": {},
        "dag_validation": {},
        "diagnostic_blueprint": {
            "owner": "/learn-test",
            "default_mode": "standard",
            "requires_user_confirmation": True,
            "budget": {
                "rounds": (diagnostic or {}).get("max_rounds") or DEFAULT_DIAGNOSTIC_MAX_ROUNDS,
                "questions_per_round": (diagnostic or {}).get("questions_per_round") or DEFAULT_DIAGNOSTIC_QUESTIONS_PER_ROUND,
            },
            "selection_policy": "优先覆盖主流、高前置依赖、高诊断价值的原子知识点；信息足够时允许提前停止。",
        },
        "evidence_log": [],
        "history": [
            {
                "event": "created",
                "timestamp": now_iso(),
                "source": "/learn-plan",
                "summary": "生成初始核心叶子知识图谱。",
            }
        ],
    }
    validate_knowledge_state(state)
    return recalculate_state(state)


def _leaf_nodes(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [node for node in state.get("nodes", []) if isinstance(node, dict) and _is_leaf_node(node)]


def _node_map(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(node.get("id")): node
        for node in state.get("nodes", [])
        if isinstance(node, dict) and str(node.get("id") or "").strip()
    }


def _child_ids(state: dict[str, Any], parent_id: str) -> list[str]:
    return [str(node.get("id")) for node in state.get("nodes", []) if isinstance(node, dict) and node.get("parent_id") == parent_id]


def _descendant_leaf_ids(state: dict[str, Any], node_id: str) -> list[str]:
    mapping = _node_map(state)
    result: list[str] = []
    stack = _child_ids(state, node_id)
    while stack:
        current_id = stack.pop()
        current = mapping.get(current_id)
        if not current:
            continue
        if _is_leaf_node(current):
            result.append(current_id)
        else:
            stack.extend(_child_ids(state, current_id))
    return result


def _detect_cycle(edges: list[dict[str, Any]], node_ids: set[str]) -> bool:
    graph: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        if source in graph and target in node_ids:
            graph[source].append(target)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        for target in graph.get(node_id, []):
            if visit(target):
                return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    return any(visit(node_id) for node_id in node_ids)


def validate_knowledge_state(state: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    if state.get("contract_version") != CONTRACT_VERSION:
        issues.append("knowledge.contract_version.unsupported")
    if state.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        issues.append("knowledge.schema_version.unsupported")
    nodes = state.get("nodes") if isinstance(state.get("nodes"), list) else []
    edges = state.get("edges") if isinstance(state.get("edges"), list) else []
    ids: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            issues.append("knowledge.node.invalid")
            continue
        node_id = str(node.get("id") or "").strip()
        level = str(node.get("level") or "").strip()
        if not node_id:
            issues.append("knowledge.node.id_missing")
        ids.append(node_id)
        if level not in SUPPORTED_KNOWLEDGE_LEVELS:
            issues.append(f"knowledge.node.level_invalid:{node_id}")
        if level != "domain" and node.get("parent_id") not in ids and not any(isinstance(item, dict) and item.get("id") == node.get("parent_id") for item in nodes):
            issues.append(f"knowledge.node.parent_missing:{node_id}")
        if level not in LEAF_LEVELS and "mastery" in node:
            issues.append(f"knowledge.node.upper_mastery_forbidden:{node_id}")
        if level in LEAF_LEVELS:
            if not isinstance(node.get("required_evidence_types"), list) or not node.get("required_evidence_types"):
                issues.append(f"knowledge.node.required_evidence_missing:{node_id}")
            unknown = [item for item in node.get("required_evidence_types") or [] if item not in DEFAULT_EVIDENCE_TYPES]
            if unknown:
                issues.append(f"knowledge.node.required_evidence_unknown:{node_id}")
            try:
                mastery = int(float(node.get("mastery", 0)))
                target = int(float(node.get("target_mastery", 0)))
            except (TypeError, ValueError):
                issues.append(f"knowledge.node.mastery_invalid:{node_id}")
                mastery = target = 0
            if not 0 <= mastery <= 100:
                issues.append(f"knowledge.node.mastery_range:{node_id}")
            if not 0 <= target <= 100:
                issues.append(f"knowledge.node.target_mastery_range:{node_id}")
            if level == "atomic_knowledge_point":
                if not isinstance(node.get("diagnostic_tasks"), list) or not node.get("diagnostic_tasks"):
                    issues.append(f"knowledge.node.diagnostic_tasks_missing:{node_id}")
                if not isinstance(node.get("common_misconceptions"), list):
                    issues.append(f"knowledge.node.common_misconceptions_invalid:{node_id}")
    if len(ids) != len(set(ids)):
        issues.append("knowledge.node.duplicate_id")
    node_ids = set(ids)
    for edge in edges:
        if not isinstance(edge, dict):
            issues.append("knowledge.edge.invalid")
            continue
        if edge.get("from") not in node_ids:
            issues.append(f"knowledge.edge.from_missing:{edge.get('from')}")
        if edge.get("to") not in node_ids:
            issues.append(f"knowledge.edge.to_missing:{edge.get('to')}")
        if edge.get("type") not in {"hard", "soft", "recommended", "diagnostic"}:
            issues.append(f"knowledge.edge.type_invalid:{edge.get('from')}->{edge.get('to')}")
    if _detect_cycle(edges, node_ids):
        issues.append("knowledge.dag.cycle")
    if issues:
        raise KnowledgeStateError("; ".join(issues))
    return {"valid": True, "issues": [], "checked_at": now_iso()}


def recalculate_state(state: dict[str, Any]) -> dict[str, Any]:
    updated = json.loads(json.dumps(state, ensure_ascii=False))
    mapping = _node_map(updated)
    for node in updated.get("nodes", []):
        if not isinstance(node, dict):
            continue
        if _is_leaf_node(node):
            node["status_label"] = derive_status_label(node.get("mastery", 0))
            continue
        leaf_ids = _descendant_leaf_ids(updated, str(node.get("id")))
        leaves = [mapping[leaf_id] for leaf_id in leaf_ids if leaf_id in mapping]
        total_weight = 0.0
        weighted = 0.0
        for leaf in leaves:
            try:
                weight = float(leaf.get("relevance", 1.0) or 1.0)
                mastery = float(leaf.get("mastery", 0) or 0)
            except (TypeError, ValueError):
                continue
            total_weight += weight
            weighted += mastery * weight
        node["derived_mastery"] = round(weighted / total_weight, 1) if total_weight else 0
        node["child_ids"] = _child_ids(updated, str(node.get("id")))
    leaf_count = len(_leaf_nodes(updated))
    source_counts: dict[str, int] = {}
    for node in updated.get("nodes", []):
        source = str((node or {}).get("source") or "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1
    low_confidence_edges = [edge for edge in updated.get("edges", []) if edge.get("confidence") == "low"]
    updated["coverage_report"] = {
        "leaf_count": leaf_count,
        "source_counts": source_counts,
        "low_confidence_edge_count": len(low_confidence_edges),
        "core_leaf_policy": "默认采用五层原子知识点图谱；旧 knowledge_point 叶子保持兼容。",
        "knowledge_levels": KNOWLEDGE_LEVELS,
        "updated_at": now_iso(),
    }
    updated["dag_validation"] = {"valid": True, "issues": [], "checked_at": now_iso()}
    return updated


def load_knowledge_state(plan_path: Path) -> dict[str, Any] | None:
    path = resolve_knowledge_paths(plan_path)["knowledge_state"]
    data = read_json_if_exists(path)
    if not data:
        return None
    validate_knowledge_state(data)
    return recalculate_state(data)


def save_knowledge_state(plan_path: Path, state: dict[str, Any], *, write_map: bool = True) -> dict[str, Path]:
    paths = resolve_knowledge_paths(plan_path)
    updated = recalculate_state(state)
    validate_knowledge_state(updated)
    write_json(paths["knowledge_state"], updated)
    if write_map:
        write_text(paths["knowledge_map"], render_knowledge_map(updated))
    return paths


def render_knowledge_map(state: dict[str, Any]) -> str:
    updated = recalculate_state(state)
    mapping = _node_map(updated)
    lines = [
        "# Knowledge Map",
        "",
        "## 状态摘要",
        "",
        f"- contract_version：{updated.get('contract_version')}",
        f"- schema_version：{updated.get('schema_version')}",
        f"- 图谱状态：{updated.get('status')}",
        f"- 底层知识点数量：{updated.get('coverage_report', {}).get('leaf_count', 0)}",
        "- 粒度策略：默认采用 domain / module / concept_cluster / concept / atomic_knowledge_point 五层图谱；旧 knowledge_point 状态保持兼容。",
        "",
        "## 层级知识图谱",
        "",
    ]
    roots = [node for node in updated.get("nodes", []) if isinstance(node, dict) and node.get("level") == "domain"]

    def emit(node_id: str, depth: int) -> None:
        node = mapping[node_id]
        indent = "  " * depth
        if _is_leaf_node(node):
            lines.append(
                f"{indent}- {node.get('title')}（{node.get('mastery', 0)}%，{node.get('status_label')}，confidence={node.get('confidence')}，target={node.get('target_mastery')}）"
            )
            evidence = ", ".join(node.get("required_evidence_types") or [])
            if evidence:
                lines.append(f"{indent}  - required evidence：{evidence}")
            if node.get("api_signature"):
                lines.append(f"{indent}  - api_signature：{node.get('api_signature')}")
            if node.get("operation_signature"):
                lines.append(f"{indent}  - operation_signature：{node.get('operation_signature')}")
            if node.get("diagnostic_tasks"):
                lines.append(f"{indent}  - diagnostic tasks：{'；'.join(normalize_string_list(node.get('diagnostic_tasks'))[:3])}")
            if node.get("expandable_subpoints"):
                lines.append(f"{indent}  - 可展开子项：{'；'.join(normalize_string_list(node.get('expandable_subpoints')))}")
            return
        lines.append(f"{indent}- {node.get('title')}（derived_mastery={node.get('derived_mastery', 0)}）")
        for child_id in node.get("child_ids") or _child_ids(updated, node_id):
            if child_id in mapping:
                emit(child_id, depth + 1)

    for root in roots:
        emit(str(root.get("id")), 0)
    lines.extend(["", "## 关键依赖", ""])
    for edge in updated.get("edges", [])[:80]:
        source = mapping.get(str(edge.get("from")))
        target = mapping.get(str(edge.get("to")))
        if not source or not target:
            continue
        lines.append(f"- {source.get('title')} → {target.get('title')}（{edge.get('type')}）：{edge.get('reason')}")
    lines.extend(["", "## Coverage Report", ""])
    report = updated.get("coverage_report") or {}
    lines.append(f"- 底层知识点数量：{report.get('leaf_count', 0)}")
    lines.append(f"- 低置信依赖数量：{report.get('low_confidence_edge_count', 0)}")
    lines.append(f"- 来源分布：{json.dumps(report.get('source_counts') or {}, ensure_ascii=False, sort_keys=True)}")
    lines.extend(["", "## DAG 校验", ""])
    validation = updated.get("dag_validation") or {}
    lines.append(f"- valid：{validation.get('valid')}")
    lines.append(f"- checked_at：{validation.get('checked_at')}")
    lines.extend(["", "## Diagnostic Blueprint", ""])
    blueprint = updated.get("diagnostic_blueprint") or {}
    lines.append("- 初始测试题生成由 /learn-test 负责。")
    lines.append(f"- 默认模式：{blueprint.get('default_mode', 'standard')}")
    lines.append(f"- 需要用户确认图谱：{blueprint.get('requires_user_confirmation', True)}")
    return "\n".join(lines).rstrip() + "\n"


def _hard_prerequisite_ids(state: dict[str, Any], point_id: str) -> list[str]:
    return [
        str(edge.get("from"))
        for edge in state.get("edges", [])
        if edge.get("to") == point_id and edge.get("type") == "hard"
    ]


def readiness_for_points(state: dict[str, Any], point_ids: list[str], *, min_mastery: int = 60) -> dict[str, Any]:
    mapping = _node_map(state)
    blocked: list[dict[str, Any]] = []
    ready: list[str] = []
    for point_id in point_ids:
        prerequisites = _hard_prerequisite_ids(state, point_id)
        missing = []
        for prereq_id in prerequisites:
            prereq = mapping.get(prereq_id)
            if not prereq:
                missing.append({"id": prereq_id, "reason": "missing"})
                continue
            mastery = int(float(prereq.get("mastery", 0) or 0))
            confidence = str(prereq.get("confidence") or "low")
            if mastery < min_mastery or confidence == "low":
                missing.append({"id": prereq_id, "title": prereq.get("title"), "mastery": mastery, "confidence": confidence})
        if missing:
            blocked.append({"id": point_id, "title": (mapping.get(point_id) or {}).get("title"), "missing_prerequisites": missing})
        else:
            ready.append(point_id)
    return {"ready_point_ids": ready, "blocked_points": blocked, "ready": not blocked}


def _topic_leaf_ids(state: dict[str, Any], topic_hint: str | None) -> list[str]:
    hint = str(topic_hint or "").strip().lower()
    mapping = _node_map(state)
    selected: list[str] = []
    for node in state.get("nodes", []):
        if not isinstance(node, dict) or _is_leaf_node(node):
            continue
        title = str(node.get("title") or "").lower()
        description = str(node.get("description") or "").lower()
        if not hint or hint in title or hint in description or title in hint:
            selected.extend(_descendant_leaf_ids(state, str(node.get("id"))))
    if not selected:
        selected = [str(node.get("id")) for node in _leaf_nodes(state)]
    return [item for item in _unique(selected) if item in mapping]


def build_lesson_target_slice(state: dict[str, Any], *, stage: str | None = None, topic: str | None = None, time_budget: str | None = None) -> dict[str, Any]:
    updated = recalculate_state(state)
    mapping = _node_map(updated)
    candidates = _topic_leaf_ids(updated, topic)
    leaves = [mapping[item] for item in candidates if item in mapping]
    leaves.sort(key=lambda node: (float(node.get("mastery", 0) or 0) - float(node.get("target_mastery", 80) or 80), -float(node.get("relevance", 1) or 1)))
    primary = [str(node.get("id")) for node in leaves[:3]]
    prerequisite_ids = _unique([prereq for point_id in primary for prereq in _hard_prerequisite_ids(updated, point_id)])
    review = [
        str(node.get("id"))
        for node in _leaf_nodes(updated)
        if str(node.get("confidence") or "") == "low" or int(float(node.get("mastery", 0) or 0)) < 60
    ][:3]
    readiness = readiness_for_points(updated, primary)
    return {
        "session_goal": f"推进 {topic or stage or '当前主题'} 的核心知识点",
        "plan_pointer": {"stage": stage, "topic": topic, "time_budget": time_budget},
        "primary_points": primary,
        "prerequisite_points": prerequisite_ids,
        "review_points": review,
        "bridge_points": prerequisite_ids[:2] if not readiness.get("ready") else [],
        "blocked_points": readiness.get("blocked_points", []),
        "evidence_targets": _unique([e for point_id in primary for e in (mapping.get(point_id, {}).get("required_evidence_types") or [])]),
        "material_segments": [],
        "readiness": readiness,
    }


def _diagnostic_node_score(state: dict[str, Any], node: dict[str, Any]) -> float:
    mastery_gap = max(0, 100 - normalize_int(node.get("mastery"))) / 100
    confidence_bonus = 0.35 if str(node.get("confidence") or "low") == "low" else 0.0
    relevance = float(node.get("relevance", 1) or 1)
    prerequisite_count = len(_hard_prerequisite_ids(state, str(node.get("id")))) + len(normalize_string_list(node.get("prerequisite_ids")))
    diagnostic_task_count = len(node.get("diagnostic_tasks") or []) if isinstance(node.get("diagnostic_tasks"), list) else 0
    misconception_count = len(node.get("common_misconceptions") or []) if isinstance(node.get("common_misconceptions"), list) else 0
    api_bonus = 0.4 if node.get("api_signature") else 0.0
    return round(relevance * 2 + mastery_gap + confidence_bonus + prerequisite_count * 0.5 + diagnostic_task_count * 0.25 + misconception_count * 0.2 + api_bonus, 4)


def _early_stop_policy(selected_count: int, leaf_count: int, rounds: int, questions_per_round: int) -> dict[str, Any]:
    budget = max(1, rounds) * max(1, questions_per_round)
    coverage_ratio = round(selected_count / leaf_count, 3) if leaf_count else 0
    return {
        "enabled": True,
        "min_rounds_before_stop": 1,
        "stop_when": [
            "推荐起点稳定且主要薄弱链稳定",
            "已覆盖高诊断价值原子点且继续出题边际收益低",
            "用户期望轮次内已能确定下一阶段路线",
        ],
        "sufficiency_threshold": {
            "min_high_value_points": min(selected_count, max(3, questions_per_round)),
            "coverage_ratio": min(0.8, max(0.25, coverage_ratio)),
            "budget": budget,
        },
    }


def build_test_coverage_slice(
    state: dict[str, Any],
    *,
    test_goal: str = "阶段测试",
    rounds: int = DEFAULT_DIAGNOSTIC_MAX_ROUNDS,
    questions_per_round: int = DEFAULT_DIAGNOSTIC_QUESTIONS_PER_ROUND,
) -> dict[str, Any]:
    updated = recalculate_state(state)
    leaves = _leaf_nodes(updated)
    scored_leaves = [(_diagnostic_node_score(updated, node), node) for node in leaves]
    scored_leaves.sort(key=lambda item: (-item[0], str(item[1].get("id") or "")))
    budget = max(1, rounds) * max(1, questions_per_round)
    selected_nodes = [node for _, node in scored_leaves[: max(3, min(len(scored_leaves), budget * 2))]]
    selected = [str(node.get("id")) for node in selected_nodes]
    excluded = [str(node.get("id")) for _, node in scored_leaves if str(node.get("id")) not in selected]
    diagnostic_values = [
        {
            "knowledge_point_id": str(node.get("id")),
            "title": node.get("title"),
            "score": score,
            "prerequisite_ids": _unique(_hard_prerequisite_ids(updated, str(node.get("id"))) + normalize_string_list(node.get("prerequisite_ids"))),
            "diagnostic_tasks": normalize_string_list(node.get("diagnostic_tasks"))[:4],
            "reason": "高诊断价值：综合考虑 relevance、低掌握/低置信、前置依赖、误区和 API/操作粒度。",
        }
        for score, node in scored_leaves
        if str(node.get("id")) in selected
    ]
    return {
        "test_goal": test_goal,
        "coverage_budget": {"rounds": rounds, "questions_per_round": questions_per_round},
        "selection_strategy": "information_gain_hub_prerequisite_first",
        "selected_points": selected,
        "excluded_points": excluded,
        "question_mapping": [],
        "diagnostic_values": diagnostic_values,
        "early_stop_policy": _early_stop_policy(len(selected), len(leaves), rounds, questions_per_round),
        "evidence_types": _unique([e for node in selected_nodes for e in (node.get("required_evidence_types") or [])]),
        "expected_confidence_update": {
            "covered_leaf_count": len(selected),
            "total_leaf_count": len(leaves),
            "coverage_ratio": round(len(selected) / len(leaves), 3) if leaves else 0,
        },
    }


def _clamp_delta(delta: Any, limit: int = MAX_MASTERY_DELTA) -> int:
    try:
        value = int(float(delta))
    except (TypeError, ValueError):
        return 0
    return max(-limit, min(limit, value))


def _has_high_quality_diagnostic_evidence(item: dict[str, Any]) -> bool:
    diagnostic = item.get("diagnostic_evidence") if isinstance(item.get("diagnostic_evidence"), dict) else {}
    if not diagnostic:
        return False
    try:
        confidence = float(diagnostic.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    return (
        str(diagnostic.get("source") or "").strip() == "reflection.diagnoses"
        and str(diagnostic.get("severity") or "").strip() == "high"
        and str(diagnostic.get("question_quality_guard") or "passed").strip() == "passed"
        and normalize_int(diagnostic.get("round_count")) >= 2
        and confidence >= 0.75
    )


def _evidence_mastery_delta(item: dict[str, Any]) -> int:
    try:
        value = int(float(item.get("mastery_delta", 0)))
    except (TypeError, ValueError):
        return 0
    if _has_high_quality_diagnostic_evidence(item):
        return max(-100, min(100, value))
    return _clamp_delta(value, DEFAULT_CONSERVATIVE_MASTERY_DELTA)


def build_review_before_progress_gate(nodes: list[dict[str, Any]], *, drop_threshold: int = 30) -> dict[str, Any]:
    review_targets: list[str] = []
    for node in nodes:
        if not isinstance(node, dict) or not _is_leaf_node(node):
            continue
        current = normalize_int(node.get("mastery"))
        baselines = [normalize_int(node.get(key)) for key in ("baseline_mastery", "previous_stage_mastery", "weekly_mastery") if node.get(key) is not None]
        if not baselines:
            continue
        previous = max(baselines)
        if previous - current >= drop_threshold or str(node.get("stability") or "").strip() in {"declining", "fragile"}:
            target = str(node.get("id") or node.get("title") or "").strip()
            if target and target not in review_targets:
                review_targets.append(target)
    if review_targets:
        return {
            "recommended_action": "review_first",
            "blocks_advance": False,
            "requires_user_confirmation": True,
            "review_targets": review_targets[:4],
            "rationale": "近期掌握度出现明显退化，建议先复习再推进新内容。",
            "user_decision": None,
        }
    return {
        "recommended_action": "proceed",
        "blocks_advance": False,
        "requires_user_confirmation": False,
        "review_targets": [],
        "rationale": "未发现需要阻断推进的明显退化信号。",
        "user_decision": None,
    }


def _question_knowledge_point_ids(question: dict[str, Any]) -> list[str]:
    source_trace = question.get("source_trace") if isinstance(question.get("source_trace"), dict) else {}
    rubric = question.get("rubric_by_knowledge_point") if isinstance(question.get("rubric_by_knowledge_point"), dict) else {}
    return normalize_string_list(
        question.get("knowledge_point_ids")
        or question.get("knowledge_points")
        or source_trace.get("knowledge_point_ids")
        or source_trace.get("knowledge_points")
        or list(rubric.keys())
    )


def _question_evidence_types(question: dict[str, Any]) -> list[str]:
    source_trace = question.get("source_trace") if isinstance(question.get("source_trace"), dict) else {}
    values = normalize_string_list(question.get("evidence_types") or source_trace.get("evidence_types"))
    return [item for item in values if item in DEFAULT_EVIDENCE_TYPES]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_interaction_knowledge_evidence_items(session_facts: dict[str, Any], *, session_type: str) -> list[dict[str, Any]]:
    completion = session_facts.get("completion_signal_facts") if isinstance(session_facts.get("completion_signal_facts"), dict) else {}
    reflection = session_facts.get("reflection_facts") if isinstance(session_facts.get("reflection_facts"), dict) else {}
    judgement = session_facts.get("mastery_judgement_facts") if isinstance(session_facts.get("mastery_judgement_facts"), dict) else {}
    completion_received = completion.get("status") in {"received", "completed"}
    reflection_completed = reflection.get("status") == "completed"
    if not completion_received or not reflection_completed:
        return []

    evidence_items: list[dict[str, Any]] = []
    for event in session_facts.get("interaction_event_facts") or []:
        if not isinstance(event, dict):
            continue
        point_ids = normalize_string_list(event.get("knowledge_points"))
        if not point_ids:
            continue
        severity = str(event.get("severity") or "").strip()
        follow_up_status = str(event.get("follow_up_status") or "").strip()
        prompting_level = str(event.get("prompting_level") or "unknown").strip()
        if severity not in {"high", "medium"} and follow_up_status not in {"partial", "blocked", "needs_review"}:
            continue
        delta = -6 if severity == "high" or follow_up_status in {"blocked", "needs_review"} else -3
        evidence_items.append(
            {
                "knowledge_point_ids": point_ids,
                "evidence_types": ["explanation"],
                "mastery_delta": delta,
                "confidence_after": "low",
                "summary": event.get("summary") or f"交互暴露知识点不稳：{'、'.join(point_ids)}",
                "source": f"/learn-{session_type}:interaction",
                "diagnostic_evidence": {
                    "source": "interaction_events",
                    "severity": severity or "medium",
                    "follow_up_status": follow_up_status or "unknown",
                    "prompting_level": prompting_level,
                },
            }
        )

    for diagnosis in reflection.get("diagnoses") or []:
        if not isinstance(diagnosis, dict):
            continue
        point_id = str(diagnosis.get("knowledge_point_id") or "").strip()
        if not point_id:
            continue
        severity = str(diagnosis.get("severity") or "").strip()
        quality_guard = str(diagnosis.get("question_quality_guard") or "passed").strip()
        if severity not in {"high", "medium"} or quality_guard in {"failed", "low_question_quality", "question_quality_issue"}:
            continue
        delta = -12 if severity == "high" else -6
        evidence_items.append(
            {
                "knowledge_point_ids": [point_id],
                "evidence_types": ["explanation", "transfer"],
                "mastery_delta": delta,
                "confidence_after": "low",
                "summary": diagnosis.get("rationale") or diagnosis.get("diagnosis") or f"复盘诊断确认薄弱点：{point_id}",
                "source": f"/learn-{session_type}:reflection-diagnosis",
                "diagnostic_evidence": {
                    "source": "reflection.diagnoses",
                    "severity": severity,
                    "confidence": _safe_float(diagnosis.get("confidence")),
                    "question_quality_guard": quality_guard,
                    "round_count": reflection.get("round_count"),
                },
            }
        )

    mastery_status = str(judgement.get("status") or "").strip()
    prompting_level = str(judgement.get("prompting_level") or "unknown").strip()
    judgement_confidence = _safe_float(judgement.get("confidence"))
    if mastery_status == "mastered" and prompting_level in {"none", "unprompted", "unknown"} and judgement_confidence >= 0.75:
        point_ids: list[str] = []
        for round_item in reflection.get("rounds") or []:
            if isinstance(round_item, dict) and str(round_item.get("result") or "").strip() in {"mastered", "correct", "passed", "unprompted_correct"}:
                point_ids.extend(normalize_string_list(round_item.get("knowledge_points")))
        point_ids = normalize_string_list(point_ids)
        if point_ids:
            evidence_items.append(
                {
                    "knowledge_point_ids": point_ids,
                    "evidence_types": ["explanation", "transfer"],
                    "mastery_delta": 5,
                    "confidence_after": "medium",
                    "summary": "复盘中无提示解释稳定，允许小幅正向掌握度更新。",
                    "source": f"/learn-{session_type}:reflection-mastery",
                    "diagnostic_evidence": {
                        "source": "reflection.mastery_judgement",
                        "status": mastery_status,
                        "confidence": judgement_confidence,
                        "prompting_level": prompting_level,
                    },
                }
            )
    return evidence_items


def build_session_knowledge_evidence_items(
    progress: dict[str, Any],
    questions_map: dict[str, dict[str, Any]],
    *,
    session_type: str,
    gate: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if gate is not None and not (gate.get("completion_received") and gate.get("reflection_completed")):
        return []
    question_progress = progress.get("questions") if isinstance(progress.get("questions"), dict) else {}
    evidence_items: list[dict[str, Any]] = []
    for qid, item in question_progress.items():
        item = item if isinstance(item, dict) else {}
        stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
        attempts = normalize_int(stats.get("attempts"))
        if attempts <= 0:
            continue
        question = questions_map.get(qid) or questions_map.get(str(qid)) or {}
        if not isinstance(question, dict) or question.get("category") == "open":
            continue
        point_ids = _question_knowledge_point_ids(question)
        if not point_ids:
            continue
        category = str(question.get("category") or "unknown").strip().lower()
        success_count = normalize_int(stats.get("pass_count")) if category == "code" else normalize_int(stats.get("correct_count"))
        if not success_count:
            last_status = str(stats.get("last_status") or "").strip().lower()
            success_count = 1 if last_status in {"passed", "correct"} else 0
        success = success_count > 0
        evidence_types = _question_evidence_types(question)
        if not evidence_types:
            continue
        delta = 8 if success else -4
        if session_type == "test" and success:
            delta = 10
        confidence_after = "medium" if success else "low"
        title = str(question.get("title") or question.get("question") or qid).strip()
        evidence_items.append(
            {
                "knowledge_point_ids": point_ids,
                "evidence_types": evidence_types,
                "mastery_delta": delta,
                "confidence_after": confidence_after,
                "summary": f"{title}: {'答对/通过' if success else '未通过'}，尝试 {attempts} 次",
                "source": f"/learn-{session_type}:question:{qid}",
            }
        )
    return evidence_items


def count_applicable_session_evidence(state: dict[str, Any], evidence_items: list[dict[str, Any]]) -> int:
    mapping = _node_map(state)
    count = 0
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        evidence_types = [e for e in normalize_string_list(item.get("evidence_types") or item.get("evidence_type")) if e in DEFAULT_EVIDENCE_TYPES]
        if not evidence_types:
            continue
        point_ids = normalize_string_list(item.get("knowledge_point_ids") or item.get("knowledge_points") or item.get("point_id"))
        for point_id in point_ids:
            node = mapping.get(point_id)
            if node and _is_leaf_node(node):
                count += 1
    return count


def update_state_from_session_evidence(
    state: dict[str, Any],
    *,
    session_dir: Path,
    session_type: str,
    evidence_items: list[dict[str, Any]],
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    updated = json.loads(json.dumps(state, ensure_ascii=False))
    mapping = _node_map(updated)
    log = updated.get("evidence_log") if isinstance(updated.get("evidence_log"), list) else []
    timestamp = now_iso()
    applied_count = 0
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        point_ids = normalize_string_list(item.get("knowledge_point_ids") or item.get("knowledge_points") or item.get("point_id"))
        evidence_types = [e for e in normalize_string_list(item.get("evidence_types") or item.get("evidence_type")) if e in DEFAULT_EVIDENCE_TYPES]
        if not evidence_types:
            continue
        delta = _evidence_mastery_delta(item)
        confidence = item.get("confidence_after") or item.get("confidence")
        for point_id in point_ids:
            node = mapping.get(point_id)
            if not node or not _is_leaf_node(node):
                continue
            mastery = int(float(node.get("mastery", 0) or 0))
            node["mastery"] = max(0, min(100, mastery + delta))
            if confidence in {"low", "medium", "high"}:
                node["confidence"] = confidence
            if session_type == "test":
                node["last_tested"] = timestamp
            else:
                node["last_studied"] = timestamp
            evidence_id = f"ev-{len(log) + 1:05d}"
            node.setdefault("evidence_refs", [])
            if evidence_id not in node["evidence_refs"]:
                node["evidence_refs"].append(evidence_id)
            log.append(
                {
                    "id": evidence_id,
                    "timestamp": timestamp,
                    "session_dir": str(session_dir),
                    "session_type": session_type,
                    "knowledge_point_ids": [point_id],
                    "evidence_types": evidence_types,
                    "mastery_delta": delta,
                    "summary": item.get("summary") or item.get("rationale") or (summary or {}).get("overall"),
                    "source": item.get("source") or f"/learn-{session_type}",
                    **({"diagnostic_evidence": item.get("diagnostic_evidence")} if isinstance(item.get("diagnostic_evidence"), dict) else {}),
                }
            )
            applied_count += 1
    if not applied_count:
        return recalculate_state(updated)
    updated["evidence_log"] = log[-500:]
    history = updated.get("history") if isinstance(updated.get("history"), list) else []
    history.append(
        {
            "event": "session_evidence_update",
            "timestamp": timestamp,
            "source": f"/learn-{session_type}",
            "session_dir": str(session_dir),
            "summary": (summary or {}).get("overall") or f"{session_type} session 更新知识状态",
            "applied_evidence_count": applied_count,
        }
    )
    updated["history"] = history[-100:]
    return recalculate_state(updated)
