"""FR-T5 Judging modes: LLM-only multi-judge majority vote, human-only, hybrid routing."""

from e2eai.eval_lab import judge_items, majority_vote


def test_majority_vote_unanimous_pass_is_high_confidence():
    vote = majority_vote([1.0, 1.0, 0.9])
    assert vote["verdict"] == 1
    assert vote["confidence"] > 0.9
    assert vote["disagreement"] is False


def test_majority_vote_split_is_low_confidence_and_disagreement():
    vote = majority_vote([1.0, 0.0, 1.0])
    assert vote["verdict"] == 1
    assert vote["confidence"] == 0.6667  # 2 of 3 judges
    assert vote["disagreement"] is True


def test_llm_only_mode_accepts_all_with_no_human_queue():
    result = judge_items(
        [
            {"item_id": "q1", "judge_scores": [1.0, 1.0, 1.0]},
            {"item_id": "q2", "judge_scores": [0.0, 0.0, 1.0]},
        ],
        mode="llm",
    )
    assert result["mode"] == "llm"
    assert result["human_queue"] == []
    assert [a["item_id"] for a in result["accepted"]] == ["q1", "q2"]
    assert result["accepted"][0]["verdict"] == 1
    assert result["accepted"][1]["verdict"] == 0


def test_human_only_mode_routes_all_without_scores_and_no_sensitive_text():
    result = judge_items(
        [
            {
                "item_id": "q1",
                "judge_scores": [1.0, 1.0],
                "answer": "secret revenue-share is 30 percent",
                "question": "what is the revenue share?",
                "persona": "andi",
                "kind": "qa",
            }
        ],
        mode="human",
    )
    assert result["mode"] == "human"
    assert result["accepted"] == []
    assert len(result["human_queue"]) == 1
    entry = result["human_queue"][0]
    assert entry["item_id"] == "q1"
    assert entry["reason"] == "human_only"
    # metadata is whitelisted; no raw answers/snippets leak into the queue
    serialized = str(entry)
    assert "30 percent" not in serialized
    assert "revenue share" not in serialized
    assert entry["metadata"]["persona"] == "andi"


def test_hybrid_routes_on_disagreement_else_accepts():
    result = judge_items(
        [
            {"item_id": "agree", "judge_scores": [1.0, 1.0, 1.0]},
            {"item_id": "split", "judge_scores": [1.0, 0.0, 1.0]},
        ],
        mode="hybrid",
        confidence_threshold=0.75,
    )
    assert result["mode"] == "hybrid"
    assert [a["item_id"] for a in result["accepted"]] == ["agree"]
    queued = {e["item_id"]: e["reason"] for e in result["human_queue"]}
    assert queued == {"split": "judge_disagreement"}


def test_hybrid_routes_low_confidence_even_when_judges_unanimously_pass_near_threshold():
    result = judge_items(
        [{"item_id": "uncertain", "judge_scores": [0.51, 0.52, 0.53]}],
        mode="hybrid",
        confidence_threshold=0.75,
    )
    assert result["accepted"] == []
    assert result["human_queue"][0]["item_id"] == "uncertain"
    assert result["human_queue"][0]["reason"] == "low_confidence"
    assert result["human_queue"][0]["metadata"]["confidence"] < 0.75


def test_hybrid_audit_sampling_is_deterministic():
    items = [{"item_id": f"q{i}", "judge_scores": [1.0, 1.0, 1.0]} for i in range(20)]
    a = judge_items(items, mode="hybrid", audit_sample_rate=0.5, audit_seed=7)
    b = judge_items(items, mode="hybrid", audit_sample_rate=0.5, audit_seed=7)
    audited_a = sorted(e["item_id"] for e in a["human_queue"] if e["reason"] == "random_audit")
    audited_b = sorted(e["item_id"] for e in b["human_queue"] if e["reason"] == "random_audit")
    assert audited_a == audited_b
    assert 0 < len(audited_a) < 20  # some but not all sampled
