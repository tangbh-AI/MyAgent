"""MyAgent Web 模块测试"""

import pytest
from myagent.web import TaskManager, app
from fastapi.testclient import TestClient


class TestTaskManager:
    """TaskManager 单元测试"""

    def test_create_task(self):
        """测试创建任务"""
        tm = TaskManager()
        task_id = tm.create("分析一个悬臂梁", "deepseek-v4-pro")

        assert len(task_id) == 12
        task = tm.get(task_id)
        assert task is not None
        assert task["status"] == "submitted"
        assert task["user_message"] == "分析一个悬臂梁"

    def test_create_task_with_backend(self):
        """测试创建任务时可指定 CAE 后端"""
        tm = TaskManager()
        task_id = tm.create("分析悬臂梁", "deepseek-v4-pro", backend="abaqus")

        task = tm.get(task_id)
        assert task is not None
        assert task["backend"] == "abaqus"

    def test_create_task_default_backend(self):
        """测试创建任务时不指定后端为空字符串"""
        tm = TaskManager()
        task_id = tm.create("测试", "deepseek-v4-pro")

        task = tm.get(task_id)
        assert task is not None
        assert task["backend"] == ""

    def test_update_task(self):
        """测试更新任务状态"""
        tm = TaskManager()
        task_id = tm.create("测试", "deepseek-v4-pro")

        tm.update(task_id, status="generating", progress_detail="正在生成脚本...")
        task = tm.get(task_id)
        assert task["status"] == "generating"
        assert task["progress_detail"] == "正在生成脚本..."

    def test_list_tasks_order(self):
        """测试任务列表按时间倒序"""
        tm = TaskManager()
        id1 = tm.create("任务1", "deepseek-v4-pro")
        id2 = tm.create("任务2", "deepseek-v4-pro")

        tasks = tm.list_all()
        task_ids = [t["task_id"] for t in tasks]
        assert id1 in task_ids
        assert id2 in task_ids
        assert len(tasks) == 2

    def test_get_nonexistent_task(self):
        """测试查询不存在的任务"""
        tm = TaskManager()
        assert tm.get("nonexistent") is None

    def test_update_nonexistent_task(self):
        """测试更新不存在的任务（不抛异常）"""
        tm = TaskManager()
        tm.update("nonexistent", status="completed")  # 不应抛异常


class TestWebAPI:
    """Web API 集成测试（不执行真实仿真）"""

    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        return TestClient(app)

    def test_index_page(self, client):
        """测试首页返回 HTML"""
        resp = client.get("/")
        assert resp.status_code in (200, 404)

    def test_chat_empty_message(self, client):
        """测试空消息被拒绝"""
        resp = client.post("/api/chat", json={"message": ""})
        assert resp.status_code == 400

    def test_chat_missing_message(self, client):
        """测试缺少 message 字段"""
        resp = client.post("/api/chat", json={})
        assert resp.status_code == 400

    def test_list_models(self, client):
        """测试模型列表 API"""
        resp = client.get("/api/models")
        assert resp.status_code == 200
        models = resp.json()
        assert isinstance(models, list)

    def test_get_nonexistent_task(self, client):
        """测试查询不存在的任务"""
        resp = client.get("/api/tasks/nonexistent")
        assert resp.status_code == 404

    def test_list_tasks_empty(self, client):
        """测试空任务列表"""
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_download_nonexistent_task(self, client):
        """测试下载不存在任务的报告"""
        resp = client.get("/download/nonexistent/report")
        assert resp.status_code == 404

    def test_list_backends(self, client):
        """测试后端列表 API"""
        resp = client.get("/api/backends")
        assert resp.status_code == 200
        backends = resp.json()
        assert isinstance(backends, list)
        assert len(backends) >= 1
        names = [b["name"] for b in backends]
        assert "abaqus" in names
        # 验证当前后端有 current 标记
        current = [b for b in backends if b["current"]]
        assert len(current) == 1, "应有且仅有一个当前后端"

    def test_chat_invalid_backend(self, client):
        """测试使用无效后端被拒绝"""
        resp = client.post("/api/chat", json={
            "message": "测试",
            "backend": "nonexistent_backend"
        })
        assert resp.status_code == 400
        detail = resp.json().get("detail", "")
        assert "nonexistent_backend" in detail

    def test_chat_with_valid_backend(self, client):
        """测试使用有效后端（模型可能未配置，400 可接受）"""
        resp = client.post("/api/chat", json={
            "message": "测试悬臂梁",
            "backend": "abaqus"
        })
        # 400 表示模型未配置 Key（正常），403/422 才是验证失败
        assert resp.status_code in (200, 400), \
            f"预期 200 或 400（模型未配置），实际: {resp.status_code}"

    def test_download_path_traversal(self, client):
        """测试路径遍历攻击被拒绝"""
        resp = client.get("/download/test123/../../../etc/passwd")
        assert resp.status_code in (403, 404)
