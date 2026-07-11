"""main.py の push 間隔判定ロジックのテスト。"""
from main import should_push


def test_should_push_true_when_no_previous_push():
    """まだ一度もpushしていない場合は常にTrue。"""
    assert should_push(None, now=100.0, min_interval_sec=30) is True


def test_should_push_false_within_interval():
    """最小間隔に満たない場合はFalse。"""
    assert should_push(last_push_at=90.0, now=100.0, min_interval_sec=30) is False


def test_should_push_true_after_interval():
    """最小間隔以上経過していればTrue。"""
    assert should_push(last_push_at=50.0, now=100.0, min_interval_sec=30) is True
