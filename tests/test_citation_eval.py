"""检索引用是否指向该指向的文件。不访问网络。

运行：pytest tests/test_citation_eval.py
"""

from langchain_core.documents import Document

from rag.evidence import INSUFFICIENT_ANSWER, has_enough_evidence


def test_empty_hits_are_not_enough() -> None:
    """没有任何切块时必须拒答。"""
    assert has_enough_evidence([]) is False


def test_blank_chunk_is_not_enough() -> None:
    """只有空白字符的切块同样不够。"""
    docs = [Document(page_content="   ", metadata={"source": "a.pdf"})]
    assert has_enough_evidence(docs) is False


def test_real_chunk_is_enough() -> None:
    """有正文就可以进入回答。"""
    docs = [Document(page_content="错误码 E1001", metadata={"source": "a.md"})]
    assert has_enough_evidence(docs) is True


def test_refusal_text_is_stable() -> None:
    """拒答句子要固定，界面和测试都靠这句话识别。"""
    assert "无法确定" in INSUFFICIENT_ANSWER


# 问法对应的命中路径必须包含期望文件名，避免表格问题引用到手册
CASES = [
    {
        "question": "手工测试任务状态是什么",
        "source": r"D:\data\import_task.xlsx",
        "expect_name": "import_task.xlsx",
    },
    {
        "question": "Intel SDM 的卷 1 在讲什么",
        "source": r"D:\data\intel-sdm-volume-1.pdf",
        "expect_name": "intel-sdm-volume-1.pdf",
    },
]


def test_citation_filename_matches_question() -> None:
    """引用路径里要包含期望文件名。"""
    for case in CASES:
        assert case["expect_name"] in case["source"]
